#!/usr/bin/env python3
"""
Single configuration surface for Rocket.Chat ↔ Grok (IMP-03).

Loads secrets file + path/env overrides. Never prints secret values.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from wake_lib import (
    DEFAULT_AGENCY,
    DEFAULT_GROK_BIN,
    DEFAULT_IDEA_PROJECTS,
    DEFAULT_LOG_DIR,
    DEFAULT_MAX_TURNS,
    DEFAULT_WAKE_LOCK_STALE_S,
    DEFAULT_WAKE_TIMEOUT_S,
    load_env,
    configured_approval_mode_from_env,
    wake_timeout_and_lock_stale_are_consistent,
)


@dataclass
class RcConfig:
    """Validated integration settings (paths + non-secret flags; secrets in .secrets)."""

    agency_path: Path
    secrets_path: Path
    log_dir: Path
    idea_projects: Path
    grok_bin: str
    rc_base: str
    public_url: str
    wake_timeout_s: int
    wake_lock_stale_s: int
    max_turns: str
    approval_mode: str
    secrets: dict[str, str] = field(default_factory=dict)

    @property
    def operator_username(self) -> str:
        return self.secrets.get("ROCKETCHAT_OPERATOR_USERNAME", "grok")

    @property
    def operator_password(self) -> str | None:
        p = self.secrets.get("ROCKETCHAT_OPERATOR_PASSWORD")
        return p if p else None

    @property
    def operator_token(self) -> str | None:
        """Personal access token if set (IMP-20)."""
        t = self.secrets.get("ROCKETCHAT_OPERATOR_TOKEN") or self.secrets.get(
            "ROCKETCHAT_BOT_TOKEN"
        )
        return t.strip() if t and t.strip() else None

    @property
    def operator_user_id(self) -> str | None:
        u = self.secrets.get("ROCKETCHAT_OPERATOR_USER_ID") or self.secrets.get(
            "ROCKETCHAT_BOT_USER_ID"
        )
        return u.strip() if u and u.strip() else None


def _path_from_env(key: str, default: Path) -> Path:
    raw = os.environ.get(key, "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path(default).expanduser()


def load_rc_config(*, require_secrets: bool = True) -> RcConfig:
    """
    Build config from env + secrets file.

    Env overrides:
      RC_AGENCY_PATH, RC_SECRETS_PATH, RC_LOG_DIR, RC_IDEA_PROJECTS,
      RC_BASE, GROK_BIN, RC_WAKE_TIMEOUT_S, RC_WAKE_LOCK_STALE_S,
      RC_WAKE_MAX_TURNS, RC_WAKE_APPROVAL_MODE
    """
    agency = _path_from_env("RC_AGENCY_PATH", DEFAULT_AGENCY)
    secrets_path = _path_from_env(
        "RC_SECRETS_PATH", agency / "secrets" / "rocketchat.env"
    )
    log_dir = _path_from_env("RC_LOG_DIR", DEFAULT_LOG_DIR)
    ideas = _path_from_env("RC_IDEA_PROJECTS", DEFAULT_IDEA_PROJECTS)
    secrets: dict[str, str] = {}
    if secrets_path.is_file():
        secrets = load_env(secrets_path)
    elif require_secrets:
        raise FileNotFoundError(f"missing secrets: {secrets_path}")

    rc_base = (
        os.environ.get("RC_BASE")
        or secrets.get("ROCKETCHAT_ROOT_URL")
        or "http://127.0.0.1:3000"
    ).rstrip("/")
    # Prefer localhost for operator HTTP when ROOT is public ngrok
    if "ngrok" in rc_base and not os.environ.get("RC_BASE"):
        rc_base = "http://127.0.0.1:3000"

    public_url = (
        secrets.get("ROCKETCHAT_PUBLIC_URL")
        or secrets.get("ROCKETCHAT_ROOT_URL")
        or rc_base
    )
    wake_timeout = int(os.environ.get("RC_WAKE_TIMEOUT_S", str(DEFAULT_WAKE_TIMEOUT_S)))
    lock_stale = int(os.environ.get("RC_WAKE_LOCK_STALE_S", str(DEFAULT_WAKE_LOCK_STALE_S)))
    if not wake_timeout_and_lock_stale_are_consistent(wake_timeout, lock_stale):
        # Fail closed: raise lock stale above timeout
        lock_stale = wake_timeout + 300

    return RcConfig(
        agency_path=agency.resolve(),
        secrets_path=secrets_path,
        log_dir=log_dir.expanduser(),
        idea_projects=ideas.expanduser(),
        grok_bin=os.environ.get("GROK_BIN", DEFAULT_GROK_BIN),
        rc_base=rc_base if rc_base.startswith("http") else f"http://{rc_base}",
        public_url=public_url,
        wake_timeout_s=wake_timeout,
        wake_lock_stale_s=lock_stale,
        max_turns=os.environ.get("RC_WAKE_MAX_TURNS", DEFAULT_MAX_TURNS),
        approval_mode=configured_approval_mode_from_env(),
        secrets=secrets,
    )


def validate_rc_reachable(base: str, *, timeout_s: float = 5.0) -> None:
    """GET /api/info; raises on failure."""
    url = f"{base.rstrip('/')}/api/info"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            if getattr(resp, "status", 200) >= 400:
                raise RuntimeError(f"RC api/info HTTP {resp.status}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Rocket.Chat unreachable at {url}: {e}") from e


def validate_config_startup(cfg: RcConfig, *, check_rc: bool = True) -> list[str]:
    """
    Return list of human-readable problems (empty = ok).
    Does not include secret values.
    """
    problems: list[str] = []
    if not cfg.secrets_path.is_file():
        problems.append(f"secrets file missing: {cfg.secrets_path}")
    if not cfg.operator_token and not cfg.operator_password:
        problems.append("neither ROCKETCHAT_OPERATOR_TOKEN nor PASSWORD set")
    if cfg.operator_token and not cfg.operator_user_id:
        problems.append("ROCKETCHAT_OPERATOR_TOKEN set but USER_ID missing")
    if not Path(cfg.grok_bin).exists() and not os.access(
        cfg.grok_bin, os.X_OK
    ):
        # may be on PATH
        pass
    if not wake_timeout_and_lock_stale_are_consistent(
        cfg.wake_timeout_s, cfg.wake_lock_stale_s
    ):
        problems.append(
            f"wake lock stale ({cfg.wake_lock_stale_s}s) must exceed "
            f"wake timeout ({cfg.wake_timeout_s}s)"
        )
    if check_rc:
        try:
            validate_rc_reachable(cfg.rc_base)
        except RuntimeError as e:
            problems.append(str(e))
    return problems


def token_pair_from_secrets(secrets: dict[str, str]) -> tuple[str, str] | None:
    """
    If personal access token + user id are set, return (token, userId).

    IMP-20: used by operator, media poster, and PGS notify.
    """
    token = (
        secrets.get("ROCKETCHAT_OPERATOR_TOKEN")
        or secrets.get("ROCKETCHAT_BOT_TOKEN")
        or ""
    ).strip()
    uid = (
        secrets.get("ROCKETCHAT_OPERATOR_USER_ID")
        or secrets.get("ROCKETCHAT_BOT_USER_ID")
        or ""
    ).strip()
    if token and uid:
        return token, uid
    return None


def password_login_pair(secrets: dict[str, str]) -> tuple[str, str]:
    """Return (username, password) for REST login fallback."""
    user = (secrets.get("ROCKETCHAT_OPERATOR_USERNAME") or "grok").strip()
    password = secrets.get("ROCKETCHAT_OPERATOR_PASSWORD") or ""
    if not password:
        raise KeyError("ROCKETCHAT_OPERATOR_PASSWORD")
    return user, password


def resolve_operator_auth_headers(
    secrets: dict[str, str],
    *,
    base_http: str,
    login_fn=None,
) -> tuple[str, str, str]:
    """
    Resolve REST auth for the grok operator.

    Returns (authToken, userId, method) where method is "token" or "password".
    login_fn(base, username, password) -> (token, uid) when password path is used.
    """
    pair = token_pair_from_secrets(secrets)
    if pair:
        return pair[0], pair[1], "token"
    if login_fn is None:
        raise RuntimeError("password login required but login_fn not provided")
    user, password = password_login_pair(secrets)
    token, uid = login_fn(base_http, user, password)
    return token, uid, "password"
