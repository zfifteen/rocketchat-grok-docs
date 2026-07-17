#!/usr/bin/env python3
"""Grok lead preflight pack — orientation inject before the lead LLM runs.

Principal-approved automation (2026-07-17 DM): each Grok wake gets a short,
deterministic inject so the lead does not re-discover agency spine, collab
epochs, disk deltas, and blocked peer seats from scratch.

Rules:
- No network.
- No secrets paths (secrets, .env, rocketchat.env, tokens).
- Path allowlist under project_cwd, ~/IdeaProjects, ~/.grok/agency, grok logs.
- Hard size cap so the pack cannot blow the wake prompt.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

# Cap inject body (chars). Keep small — orientation aid, not a dump.
MAX_INJECT_CHARS = 4500
MAX_CROSS_ROOMS = 5
MAX_DELTA_PATHS = 10
MAX_PATHS_FROM_MSG = 8
MAX_HEADING_LEN = 100
MAX_REPLY_PREVIEW = 200
MAX_PRIOR_REPLIES = 2
STALE_DELIVERED_HOURS = 36
RETIRED_ASSIGNEES = frozenset({"claude"})

_PATH_TOKEN_RE = re.compile(
    r"(?:"
    r"(?:~|/Users/[\w.-]+|\$HOME)/[^\s`'\"<>|]+"
    r"|"
    r"(?:[\w.-]+/)+[\w.-]+\.[a-zA-Z0-9]{1,8}"
    r"|"
    r"revenue-[\w.-]+\.md"
    r"|"
    r"ops/[\w./-]+"
    r"|"
    r"experiments/[\w./-]+"
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

# Files watched for "changed since last wake" (relative to known roots).
_DELTA_REL_PATHS = (
    ("agency_home", "STATE.md"),
    ("wake", "multi_round_collab_state.json"),
    ("idea_agency", "revenue-aug1-countdown-residual.md"),
    ("idea_agency", "revenue-aug1-golive-runbook.md"),
    ("idea_agency", "revenue-first-order-playbook.md"),
    ("idea_agency", "revenue-day1-thread-watch.md"),
    ("idea_agency", "HEARTBEAT_LOG.md"),
)


def _home() -> Path:
    return Path.home().expanduser()


def agency_home() -> Path:
    return _home() / ".grok" / "agency"


def wake_dir() -> Path:
    return agency_home() / "ops" / "rocketchat" / "wake"


def idea_agency() -> Path:
    return _home() / "IdeaProjects" / "agency"


def grok_log_dir() -> Path:
    return _home() / "logs" / "rocketchat-dm-wake"


def allowlist_roots(project_cwd: str = "") -> list[Path]:
    roots: list[Path] = []
    for raw in (
        project_cwd,
        str(_home() / "IdeaProjects"),
        str(agency_home()),
        str(grok_log_dir()),
        str(_home() / "logs" / "agency-heartbeat"),
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
            if m == "token" and "tokenizer" in s:
                continue
            if m == "token" and "token" not in name and "/token" not in s:
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
        candidates.append(idea_agency() / raw)
        candidates.append(agency_home() / raw)
        if raw.startswith("revenue-"):
            candidates.append(idea_agency() / raw)

    for c in candidates:
        try:
            p = c.expanduser()
            if not p.exists() or is_secret_path(p):
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


def _fmt_mtime(path: Path) -> str:
    try:
        st = path.stat()
        return datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%MZ"
        )
    except Exception:
        return "?"


def file_stat_line(path: Path) -> str:
    try:
        st = path.stat()
        mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%MZ"
        )
        head = first_heading(path)
        head_bit = f" · {head}" if head else ""
        return f"- `{path.name}` · mtime={mtime} · size={st.st_size}{head_bit}"
    except Exception as e:
        return f"- `{path}` · error: {e}"


def _read_text(path: Path, limit: int = 80_000) -> str:
    try:
        data = path.read_bytes()
        if len(data) > limit:
            data = data[:limit]
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def parse_iso(ts: str | None) -> datetime | None:
    if not ts or not isinstance(ts, str):
        return None
    raw = ts.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def spine_slice_lines(state_path: Path | None = None) -> list[str]:
    """Compact STATE.md header + next-action one-liner."""
    path = state_path or (agency_home() / "STATE.md")
    text = _read_text(path)
    if not text:
        return ["- STATE.md: missing or unreadable"]

    lines_out: list[str] = []
    for line in text.splitlines()[:25]:
        s = line.strip()
        # Drop markdown bold markers so the inject stays plain.
        plain = s.replace("**", "").strip()
        if plain.startswith("Last updated:"):
            lines_out.append(f"- {plain[:200]}")
        elif plain.startswith("Active milestone:"):
            lines_out.append(f"- {plain[:200]}")
        elif "Stripe" in s and "2026-08-01" in s and "Hold" in s:
            lines_out.append("- Money: HOLD until Stripe 2026-08-01")
        elif plain.startswith("Phase A dual-track:") and "Hold" in s:
            if "HOLD" not in " ".join(lines_out).upper():
                lines_out.append("- Money: HOLD until Stripe 2026-08-01 (Phase A dual-track)")

    # Section 4 next action — first substantive bullet under the section
    next_action = ""
    in_s4 = False
    for line in text.splitlines():
        if line.startswith("## 4."):
            in_s4 = True
            continue
        if in_s4 and line.startswith("## "):
            break
        if in_s4:
            t = line.strip().replace("**", "")
            if t.startswith("Immediate") or t.startswith("Standing"):
                next_action = t[:220]
                break
            if t.startswith("Hold public") or t.startswith("Hold"):
                next_action = t[:220]
                break
    if next_action:
        lines_out.append(f"- Next: {next_action}")
    elif not any("Money" in x for x in lines_out):
        lines_out.append("- Next: see STATE.md §4 (parse miss)")

    # Hermes seat note if present
    if "hermes seat BLOCKED" in text or "invalid_grant" in text:
        lines_out.append(
            "- Peer seat: hermes re-auth needed (invalid_grant / BLOCKED in STATE)"
        )

    return lines_out[:8] if lines_out else ["- STATE.md: no header fields parsed"]


def agency_residual_line(project_cwd: str = "") -> str:
    candidates = []
    if project_cwd:
        candidates.append(Path(project_cwd) / "revenue-aug1-countdown-residual.md")
    candidates.append(idea_agency() / "revenue-aug1-countdown-residual.md")
    for path in candidates:
        if not path.is_file():
            continue
        text = _read_text(path)
        bits: list[str] = []
        if "2026-08-01" in text:
            bits.append("Stripe 2026-08-01")
        if "G5b" in text:
            bits.append("G5b ~2026-07-29")
        if "Still open" in text and "G1" in text:
            bits.append("open gates G1+")
        if bits:
            return f"`{path.name}`: " + "; ".join(bits)
    return ""


def load_collab_state(path: Path | None = None) -> dict:
    p = path or (wake_dir() / "multi_round_collab_state.json")
    return load_json(p)


def load_operator_state(path: Path | None = None) -> dict:
    p = path or (wake_dir() / "state.json")
    return load_json(p)


def _room_label(
    rid: str,
    *,
    current_rid: str = "",
    current_name: str = "",
    operator_state: dict | None = None,
) -> str:
    if current_rid and rid == current_rid and current_name:
        return current_name
    op = operator_state or {}
    rooms = op.get("rooms") if isinstance(op.get("rooms"), dict) else {}
    entry = rooms.get(rid) if isinstance(rooms, dict) else None
    if isinstance(entry, dict):
        cwd = entry.get("cwd") or ""
        if cwd:
            base = Path(str(cwd)).name
            if base:
                return f"{base} (`{rid[:10]}…`)"
    lc = op.get("last_content_by_room") if isinstance(op.get("last_content_by_room"), dict) else {}
    hit = lc.get(rid) if isinstance(lc, dict) else None
    if isinstance(hit, dict):
        preview = (hit.get("text") or "").replace("\n", " ").strip()[:40]
        if preview:
            return f"`{rid[:10]}…` · last: {preview}"
    return f"`{rid[:12]}…`"


def this_room_collab_lines(
    room_id: str,
    room_name: str,
    collab: dict,
    *,
    operator_state: dict | None = None,
) -> list[str]:
    rooms = collab.get("rooms") if isinstance(collab.get("rooms"), dict) else {}
    entry = rooms.get(room_id) if isinstance(rooms, dict) else None
    if not isinstance(entry, dict) or not entry:
        return [
            f"- Room: {room_name or room_id} — no open collab epoch in multi_round state"
        ]

    lines: list[str] = []
    epoch = entry.get("epoch") or "(none)"
    lead_done = bool(entry.get("lead_done"))
    assignees = entry.get("assignees") if isinstance(entry.get("assignees"), list) else []
    delivered = entry.get("delivered") if isinstance(entry.get("delivered"), dict) else {}
    lines.append(
        f"- Room: {room_name or room_id} · epoch `{epoch}` · "
        f"lead_done={lead_done}"
    )
    if assignees:
        lines.append(f"- Assignees: {', '.join(str(a) for a in assignees)}")
    retired = [a for a in assignees if str(a).lower() in RETIRED_ASSIGNEES]
    if retired:
        lines.append(
            f"- Stale assignee(s): {', '.join(retired)} "
            "(retired — do not @-tag; close or re-open epoch without them)"
        )
    if delivered:
        for peer, meta in sorted(delivered.items()):
            if not isinstance(meta, dict):
                lines.append(f"- Delivered: {peer}")
                continue
            mid = meta.get("mid") or "?"
            ts = meta.get("ts") or "?"
            lines.append(f"- Delivered: {peer} · mid `{mid}` · {ts}")
    else:
        lines.append("- Delivered: (none yet)")

    # Pending = assignees minus delivered (ignore retired for "need synthesis")
    pending = [
        a
        for a in assignees
        if str(a).lower() not in RETIRED_ASSIGNEES
        and str(a) not in delivered
        and str(a).lower() != "grok"
    ]
    if not lead_done and delivered and pending:
        lines.append(
            f"- Lead action: peers delivered; still waiting on {', '.join(pending)} "
            "or synthesize + DONE"
        )
    elif not lead_done and delivered and not pending:
        lines.append(
            "- Lead action: all live assignees delivered — synthesize or plain-language DONE"
        )
    elif not lead_done and not delivered and assignees:
        lines.append("- Lead action: epoch open; no peer deliveries recorded yet")

    return lines


def cross_room_open_lines(
    current_rid: str,
    collab: dict,
    *,
    operator_state: dict | None = None,
    now: datetime | None = None,
) -> list[str]:
    """Other rooms where lead work may still be open and peers have delivered."""
    rooms = collab.get("rooms") if isinstance(collab.get("rooms"), dict) else {}
    now = now or datetime.now(tz=timezone.utc)
    hits: list[tuple[str, str]] = []
    for rid, entry in rooms.items():
        if not isinstance(entry, dict):
            continue
        if rid == current_rid:
            continue
        if entry.get("lead_done"):
            continue
        delivered = entry.get("delivered") if isinstance(entry.get("delivered"), dict) else {}
        assignees = entry.get("assignees") if isinstance(entry.get("assignees"), list) else []
        if not delivered and not assignees:
            continue
        # Skip empty shells
        if not delivered and not assignees:
            continue
        label = _room_label(
            rid,
            current_rid=current_rid,
            operator_state=operator_state,
        )
        peers = ", ".join(sorted(delivered.keys())) if delivered else "(no deliveries)"
        n_assignees = len(
            [a for a in assignees if str(a).lower() not in RETIRED_ASSIGNEES]
        )
        # Staleness from newest delivery ts
        stale = False
        newest: datetime | None = None
        for meta in delivered.values():
            if isinstance(meta, dict):
                dt = parse_iso(str(meta.get("ts") or ""))
                if dt and (newest is None or dt > newest):
                    newest = dt
        if newest and (now - newest).total_seconds() > STALE_DELIVERED_HOURS * 3600:
            stale = True
        flag = " · STALE" if stale else ""
        hits.append(
            (
                rid,
                f"- {label}: assignees={n_assignees} delivered=[{peers}] "
                f"epoch=`{entry.get('epoch') or '?'}`{flag}",
            )
        )
    hits = hits[:MAX_CROSS_ROOMS]
    if not hits:
        return ["- (no other open lead epochs with assignees/deliveries)"]
    return [h[1] for h in hits]


def disk_delta_lines(
    project_cwd: str = "",
    *,
    last_wake_at: str | None = None,
    roots: list[Path] | None = None,
) -> list[str]:
    roots = roots or allowlist_roots(project_cwd)
    last_dt = parse_iso(last_wake_at)
    root_map = {
        "agency_home": agency_home(),
        "wake": wake_dir(),
        "idea_agency": idea_agency(),
    }
    if project_cwd:
        root_map["project"] = Path(project_cwd)

    lines: list[str] = []
    for key, rel in _DELTA_REL_PATHS:
        base = root_map.get(key)
        if base is None:
            continue
        path = base / rel
        if not path.is_file() or is_secret_path(path):
            continue
        if not path_under_allowlist(path, roots):
            continue
        mtime = _fmt_mtime(path)
        changed = ""
        if last_dt:
            try:
                mt = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                if mt > last_dt:
                    changed = " · CHANGED since last wake"
            except Exception:
                pass
        lines.append(f"- `{path.name}` · mtime={mtime}{changed}")
        if len(lines) >= MAX_DELTA_PATHS:
            break
    if not lines:
        return ["- (no allowlisted delta files found)"]
    return lines


def paths_from_message_lines(
    message_text: str,
    project_cwd: str,
    roots: list[Path],
) -> list[str]:
    tokens = extract_path_tokens(message_text)
    lines: list[str] = []
    missing: list[str] = []
    for tok in tokens:
        if len(lines) >= MAX_PATHS_FROM_MSG:
            lines.append(f"- … truncated after {MAX_PATHS_FROM_MSG} paths")
            break
        resolved = resolve_candidate(tok, project_cwd, roots)
        if resolved is None:
            if tok.startswith("revenue-") or tok.startswith("ops/") or "/" in tok:
                missing.append(tok)
            continue
        lines.append(file_stat_line(resolved))
    for m in missing[:4]:
        lines.append(f"- `{m}` · not found under allowlist")
    if not lines:
        return ["- (no allowlisted path tokens in new messages)"]
    return lines


def last_reply_previews(log_dir: Path | None = None) -> list[str]:
    d = log_dir or grok_log_dir()
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


def blocked_seats_lines(
    *,
    hermes_log_dir: Path | None = None,
    state_path: Path | None = None,
) -> list[str]:
    lines: list[str] = []
    state_text = _read_text(state_path or (agency_home() / "STATE.md"))
    if "hermes seat BLOCKED" in state_text or (
        "invalid_grant" in state_text and "hermes" in state_text.lower()
    ):
        lines.append(
            "- hermes: BLOCKED / invalid_grant (principal: `hermes model` re-auth); "
            "queue work, do not expect live peer reviews"
        )

    # Recent hermes wake logs (no secrets — only error phrase scan)
    d = hermes_log_dir or (_home() / "logs" / "rocketchat-hermes-wake")
    if d.is_dir():
        try:
            logs = sorted(
                d.glob("wake-run-*.log"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:4]
        except Exception:
            logs = []
        for lp in logs:
            try:
                chunk = lp.read_bytes()[-12_000:].decode("utf-8", errors="replace")
            except Exception:
                continue
            if "invalid_grant" in chunk or "refresh token" in chunk.lower():
                mtime = _fmt_mtime(lp)
                lines.append(
                    f"- hermes log `{lp.name}` · {mtime}: auth failure phrase present"
                )
                break

    if not lines:
        return ["- (no seat blockers detected from STATE/logs)"]
    # de-dupe
    seen: set[str] = set()
    uniq: list[str] = []
    for L in lines:
        if L in seen:
            continue
        seen.add(L)
        uniq.append(L)
    return uniq


def grok_preflight_enabled_for_process(
    *,
    operator: str = "",
    wake_backend: str = "",
    prompt_template: str = "",
) -> bool:
    """True when this process is the Grok lead operator (not hermes/agy/nie/feynman)."""
    op = (operator or os.environ.get("RC_OPERATOR_USERNAME") or "").strip().lower()
    backend = (wake_backend or os.environ.get("RC_WAKE_BACKEND") or "").strip().lower()
    prompt = (prompt_template or "").lower()

    # Explicit peer backends never get lead preflight
    if backend in ("hermes", "agy", "nie", "feynman"):
        return False
    if op in ("hermes", "agy", "nie", "feynman"):
        return False
    if any(
        x in prompt
        for x in (
            "hermes_reply_prompt",
            "agy_reply_prompt",
            "nie_reply_prompt",
            "feynman_reply_prompt",
        )
    ):
        return False

    if op == "grok" or backend in ("", "grok", "cli", "grok-cli"):
        return True
    # Default reply_prompt (lead) when operator unset but not a peer prompt
    if "reply_prompt" in prompt and "hermes" not in prompt:
        return True
    return op in ("", "grok")


def build_lead_preflight_block(
    message_text: str = "",
    *,
    project_cwd: str = "",
    room_id: str = "",
    room_name: str = "",
    last_wake_at: str | None = None,
    collab_state_path: str | Path | None = None,
    operator_state_path: str | Path | None = None,
    state_md_path: str | Path | None = None,
    log_dir: str | Path | None = None,
    hermes_log_dir: str | Path | None = None,
    enabled: bool | None = None,
) -> str:
    """Return markdown inject body, or empty string when disabled."""
    if enabled is None:
        enabled = os.environ.get("RC_GROK_PREFLIGHT", "1").strip().lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
    if not enabled:
        return ""

    roots = allowlist_roots(project_cwd)
    collab = load_collab_state(
        Path(collab_state_path) if collab_state_path else None
    )
    op_state = load_operator_state(
        Path(operator_state_path) if operator_state_path else None
    )
    if last_wake_at is None:
        last_wake_at = op_state.get("last_wake_at") if isinstance(op_state, dict) else None

    lines: list[str] = [
        "## Grok lead preflight pack (orientation — not a task list)",
        "",
        "Deterministic local snapshot for this lead wake. Prefer acting on open "
        "collab / residual gates over re-inventorying the full agency tree. "
        "Do not treat this as proof of remote state (forums, Stripe console).",
        "",
    ]
    if room_id or room_name:
        lines.append(f"Room: {room_name or room_id} (`{room_id}`)")
    if project_cwd:
        lines.append(f"cwd: `{project_cwd}`")
    if last_wake_at:
        lines.append(f"last_wake_at: {last_wake_at}")
    lines.append("")

    lines.append("### Spine (STATE slice)")
    lines.extend(
        spine_slice_lines(Path(state_md_path) if state_md_path else None)
    )
    residual = agency_residual_line(project_cwd)
    if residual:
        lines.append(f"- Residual: {residual}")
    lines.append("")

    lines.append("### This room collab")
    lines.extend(
        this_room_collab_lines(
            room_id,
            room_name,
            collab,
            operator_state=op_state,
        )
    )
    lines.append("")

    lines.append("### Other open lead epochs (need synthesis?)")
    lines.extend(
        cross_room_open_lines(
            room_id,
            collab,
            operator_state=op_state,
        )
    )
    lines.append("")

    lines.append("### Disk delta (allowlisted)")
    lines.extend(
        disk_delta_lines(
            project_cwd,
            last_wake_at=str(last_wake_at) if last_wake_at else None,
            roots=roots,
        )
    )
    lines.append("")

    lines.append("### Paths named in new messages")
    lines.extend(paths_from_message_lines(message_text, project_cwd, roots))
    lines.append("")

    lines.append("### Blocked peer seats")
    lines.extend(
        blocked_seats_lines(
            hermes_log_dir=Path(hermes_log_dir) if hermes_log_dir else None,
            state_path=Path(state_md_path) if state_md_path else None,
        )
    )
    lines.append("")

    lines.append("### Recent Grok reply files (local log)")
    previews = last_reply_previews(
        Path(log_dir) if log_dir else grok_log_dir()
    )
    if previews:
        lines.extend(previews)
    else:
        lines.append("- (none)")
    lines.append("")

    body = "\n".join(lines).strip() + "\n"
    if len(body) > MAX_INJECT_CHARS:
        body = body[: MAX_INJECT_CHARS - 20] + "\n\n(truncated)\n"
    return body


# Alias matching hermes_preflight naming for callers that prefer build_preflight_block
def build_preflight_block(*args, **kwargs) -> str:
    return build_lead_preflight_block(*args, **kwargs)


def write_preflight_audit(
    body: str,
    *,
    wake_id: str = "",
    log_dir: str | Path | None = None,
) -> Path | None:
    """Optional audit file under grok wake logs."""
    if not body.strip():
        return None
    d = Path(log_dir) if log_dir else grok_log_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        stamp = wake_id or datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        # sanitize wake_id for filename
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", stamp)[:48]
        path = d / f"preflight-lead-{safe}.txt"
        path.write_text(body, encoding="utf-8")
        return path
    except Exception:
        return None
