#!/usr/bin/env python3
"""Hermes wake preflight pack — disk truth inject before the LLM runs.

Principal-approved automation (2026-07-17): each Hermes wake gets a short,
deterministic inject block so the model does not re-litigate closed disk work.

Rules:
- No network.
- No secrets paths (anything named secrets, .env, rocketchat.env, tokens).
- Path allowlist under project_cwd, ~/IdeaProjects, ~/.grok/agency.
- Hard size cap so the pack cannot blow the wake prompt.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# Cap inject body (chars). Keep small — this is a delta aid, not a dump.
MAX_INJECT_CHARS = 4000
MAX_PATHS = 12
MAX_PRIOR_REPLIES = 2
MAX_HEADING_LEN = 120
MAX_REPLY_PREVIEW = 280

# Path-like tokens in RC messages (relative or absolute).
_PATH_TOKEN_RE = re.compile(
    r"(?:"
    r"(?:~|/Users/[\w.-]+|\$HOME)/[^\s`'\"<>|]+"  # abs / tilde
    r"|"
    r"(?:[\w.-]+/)+[\w.-]+\.[a-zA-Z0-9]{1,8}"  # rel with slash + ext
    r"|"
    r"revenue-[\w.-]+\.md"  # agency revenue short names
    r"|"
    r"ops/[\w./-]+"  # ops tree
    r"|"
    r"experiments/[\w./-]+"  # PGS experiments
    r")"
)

_SECRET_MARKERS = (
    "secrets",
    ".env",
    "rocketchat.env",
    "mcp-tokens",
    "auth.json",
    "token",
    "password",
    "credential",
)


def _home() -> Path:
    return Path.home().expanduser()


def allowlist_roots(project_cwd: str = "") -> list[Path]:
    roots: list[Path] = []
    home = _home()
    for raw in (
        project_cwd,
        str(home / "IdeaProjects"),
        str(home / ".grok" / "agency"),
        str(home / "logs" / "rocketchat-hermes-wake"),
    ):
        if not raw:
            continue
        try:
            p = Path(raw).expanduser().resolve()
        except Exception:
            continue
        if p.is_dir() and p not in roots:
            roots.append(p)
    return roots


def is_secret_path(path: Path) -> bool:
    s = str(path).lower()
    name = path.name.lower()
    for m in _SECRET_MARKERS:
        if m in name or f"/{m}" in s or s.endswith(m):
            # allow "token" only as segment, not e.g. "tokenizer"
            if m == "token" and "token" not in name and "/token" not in s:
                continue
            if m == "token" and "tokenizer" in s:
                continue
            return True
    return False


def path_under_allowlist(path: Path, roots: list[Path]) -> bool:
    try:
        resolved = path.resolve()
    except Exception:
        return False
    for root in roots:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def extract_path_tokens(text: str) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for m in _PATH_TOKEN_RE.finditer(text):
        tok = m.group(0).rstrip(".,);:]}\"')")
        if tok in seen:
            continue
        seen.add(tok)
        found.append(tok)
    return found


def resolve_candidate(token: str, project_cwd: str, roots: list[Path]) -> Path | None:
    raw = token.strip()
    if not raw:
        return None
    candidates: list[Path] = []
    if raw.startswith("~/") or raw.startswith("$HOME/"):
        candidates.append(Path(raw.replace("$HOME", str(_home()), 1)).expanduser())
    elif raw.startswith("/"):
        candidates.append(Path(raw))
    else:
        if project_cwd:
            candidates.append(Path(project_cwd) / raw)
        candidates.append(_home() / "IdeaProjects" / "agency" / raw)
        candidates.append(_home() / ".grok" / "agency" / raw)
        # bare revenue-*.md under IdeaProjects/agency
        if raw.startswith("revenue-"):
            candidates.append(_home() / "IdeaProjects" / "agency" / raw)

    for c in candidates:
        try:
            p = c.expanduser()
            if not p.exists():
                continue
            if is_secret_path(p):
                continue
            if not path_under_allowlist(p, roots):
                continue
            return p.resolve()
        except Exception:
            continue
    return None


def first_heading(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i > 40:
                    break
                s = line.strip()
                if s.startswith("#"):
                    return s[:MAX_HEADING_LEN]
    except Exception:
        pass
    return ""


def file_stat_line(path: Path) -> str:
    try:
        st = path.stat()
        mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%MZ"
        )
        size = st.st_size
        head = first_heading(path)
        head_bit = f" · {head}" if head else ""
        return f"- `{path}` · exists · mtime={mtime} · size={size}{head_bit}"
    except Exception as e:
        return f"- `{path}` · error: {e}"


def last_reply_previews(log_dir: Path | None = None) -> list[str]:
    d = log_dir or (_home() / "logs" / "rocketchat-hermes-wake")
    if not d.is_dir():
        return []
    try:
        files = sorted(
            d.glob("wake-reply-*.txt"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        return []
    out: list[str] = []
    for p in files[:MAX_PRIOR_REPLIES]:
        if is_secret_path(p):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace").strip()
            preview = text[:MAX_REPLY_PREVIEW].replace("\n", " ")
            if len(text) > MAX_REPLY_PREVIEW:
                preview += "…"
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%MZ"
            )
            out.append(f"- `{p.name}` · {mtime} · {preview}")
        except Exception:
            continue
    return out


def agency_open_gates_line(project_cwd: str) -> str:
    """One-line residual open-gates if countdown residual is present."""
    candidates = []
    if project_cwd:
        candidates.append(Path(project_cwd) / "revenue-aug1-countdown-residual.md")
    candidates.append(
        _home() / "IdeaProjects" / "agency" / "revenue-aug1-countdown-residual.md"
    )
    for path in candidates:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        # Pull G5b future note + "Still open" header presence
        g5b = "G5b" in text
        stripe = "2026-08-01" in text
        bits = []
        if stripe:
            bits.append("Stripe target 2026-08-01")
        if g5b:
            bits.append("G5b heat still gated (~T−3d)")
        if "G1" in text and "Still open" in text:
            bits.append("open gates table present (G1+)")
        if bits:
            return "Agency residual: " + "; ".join(bits) + f" · `{path.name}`"
    return ""


def spotcheck_mentions(path: Path, project_cwd: str) -> str:
    """If a hermes spotcheck mentions this file, return a short hit line."""
    roots = []
    if project_cwd:
        roots.append(Path(project_cwd))
    roots.append(_home() / "IdeaProjects" / "agency")
    needle = path.name
    for root in roots:
        if not root.is_dir():
            continue
        for sc in root.glob("revenue-hermes-*spotcheck*.md"):
            try:
                t = sc.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if needle not in t and str(path) not in t:
                continue
            # last PASS/FAIL-ish line
            hit = ""
            for line in reversed(t.splitlines()):
                if "PASS" in line or "FAIL" in line or "Verdict" in line:
                    hit = line.strip()[:160]
                    break
            mtime = datetime.fromtimestamp(sc.stat().st_mtime, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%MZ"
            )
            return f"  spotcheck `{sc.name}` · {mtime}" + (f" · {hit}" if hit else "")
    return ""


def build_preflight_block(
    message_text: str,
    *,
    project_cwd: str = "",
    room_id: str = "",
    room_name: str = "",
    log_dir: str | Path | None = None,
    enabled: bool | None = None,
) -> str:
    """Return markdown inject body (without outer header), or empty string."""
    if enabled is None:
        enabled = os.environ.get("RC_HERMES_PREFLIGHT", "1").strip() not in (
            "0",
            "false",
            "no",
            "off",
        )
    if not enabled:
        return ""

    roots = allowlist_roots(project_cwd)
    tokens = extract_path_tokens(message_text)
    lines: list[str] = [
        "## Hermes preflight pack (disk truth — not a task list)",
        "",
        "Deterministic local snapshot for this wake. Prefer delta work when mtimes "
        "and prior claims already cover the ask. Do not treat this as proof of remote "
        "state (e.g. Reddit heat).",
        "",
    ]
    if room_id or room_name:
        lines.append(f"Room: {room_name or room_id} (`{room_id}`)")
    if project_cwd:
        lines.append(f"cwd: `{project_cwd}`")
    lines.append("")

    # Files named in the message
    lines.append("### Paths named in new messages")
    path_lines = 0
    missing: list[str] = []
    for tok in tokens:
        if path_lines >= MAX_PATHS:
            lines.append(f"- … truncated after {MAX_PATHS} paths")
            break
        resolved = resolve_candidate(tok, project_cwd, roots)
        if resolved is None:
            # only report missing for revenue-/ops- style tokens
            if tok.startswith("revenue-") or tok.startswith("ops/") or "/" in tok:
                missing.append(tok)
            continue
        lines.append(file_stat_line(resolved))
        sc = spotcheck_mentions(resolved, project_cwd)
        if sc:
            lines.append(sc)
        path_lines += 1
    if path_lines == 0 and not missing:
        lines.append("- (no allowlisted path tokens found)")
    for m in missing[:6]:
        lines.append(f"- `{m}` · not found under allowlist")
    lines.append("")

    # Prior hermes replies
    lines.append("### Recent Hermes reply files (local log)")
    previews = last_reply_previews(
        Path(log_dir) if log_dir else (_home() / "logs" / "rocketchat-hermes-wake")
    )
    if previews:
        lines.extend(previews)
    else:
        lines.append("- (none)")
    lines.append("")

    # Agency residual one-liner
    gates = agency_open_gates_line(project_cwd)
    if gates:
        lines.append("### Agency residual (one line)")
        lines.append(gates)
        lines.append("")

    body = "\n".join(lines).strip() + "\n"
    if len(body) > MAX_INJECT_CHARS:
        body = body[: MAX_INJECT_CHARS - 20] + "\n\n(truncated)\n"
    return body


def write_preflight_audit(
    body: str,
    *,
    wake_id: str = "",
    log_dir: str | Path | None = None,
) -> Path | None:
    """Optional audit file under hermes wake logs."""
    if not body.strip():
        return None
    d = Path(log_dir) if log_dir else (_home() / "logs" / "rocketchat-hermes-wake")
    try:
        d.mkdir(parents=True, exist_ok=True)
        stamp = wake_id or datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = d / f"preflight-{stamp}.txt"
        path.write_text(body, encoding="utf-8")
        return path
    except Exception:
        return None


def hermes_preflight_enabled_for_process(
    *,
    operator: str = "",
    profile: str = "",
    prompt_template: str = "",
    wake_backend: str = "",
) -> bool:
    """True when this operator process is Hermes (not grok/agy/nie/feynman)."""
    op = (operator or os.environ.get("RC_OPERATOR_USERNAME") or "").strip().lower()
    prof = (profile or os.environ.get("RC_HERMES_PROFILE") or "").strip().lower()
    backend = (wake_backend or os.environ.get("RC_WAKE_BACKEND") or "").strip().lower()
    prompt = (prompt_template or "").lower()
    if op == "hermes" or backend == "hermes":
        return True
    if "hermes_reply_prompt" in prompt:
        return True
    # idea profile is Hermes production profile, but nie/feynman also use hermes bin —
    # only treat as hermes when operator name or prompt matches.
    if prof == "idea" and op in ("", "hermes"):
        # ambiguous; require backend or prompt
        return backend == "hermes" or "hermes_reply_prompt" in prompt
    return False
