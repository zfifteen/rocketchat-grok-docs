#!/usr/bin/env python3
"""
Idempotent Rocket.Chat image/file post (RC 8.6 rooms.media + mediaConfirm).

Hard rule: the same file_id is never confirmed twice (that creates duplicate
bubbles). Also tracks content hash so the same bytes are not re-uploaded in
the same room within the ledger window.

Usage:
  python3 rc_post_media.py --room-id RID --file /path/to.jpg --msg "caption"

Env: RC_BASE, secrets at ~/.grok/agency/secrets/rocketchat.env
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Defaults; apply_media_config() rewrites from shared rc_config (IMP-03).
AGENCY = Path.home() / ".grok" / "agency"
SECRETS = AGENCY / "secrets" / "rocketchat.env"
LOG_DIR = Path.home() / "logs" / "rocketchat-dm-wake"
LEDGER = LOG_DIR / "media-post-ledger.json"
BASE_HTTP = os.environ.get("RC_BASE", "http://127.0.0.1:3000")


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def apply_media_config() -> None:
    """IMP-03: pull paths/base from load_rc_config when available."""
    global AGENCY, SECRETS, LOG_DIR, LEDGER, BASE_HTTP
    try:
        wake = Path(__file__).resolve().parent
        if str(wake) not in sys.path:
            sys.path.insert(0, str(wake))
        from rc_config import load_rc_config

        cfg = load_rc_config(require_secrets=True)
        AGENCY = cfg.agency_path
        SECRETS = cfg.secrets_path
        LOG_DIR = cfg.log_dir
        LEDGER = LOG_DIR / "media-post-ledger.json"
        BASE_HTTP = cfg.rc_base.rstrip("/")
    except Exception:
        # Keep defaults if config layer unavailable (tests / minimal install).
        pass


def login() -> tuple[str, str]:
    apply_media_config()
    env = load_env(SECRETS)
    # IMP-20: token pair preferred
    token = (env.get("ROCKETCHAT_OPERATOR_TOKEN") or env.get("ROCKETCHAT_BOT_TOKEN") or "").strip()
    uid = (
        env.get("ROCKETCHAT_OPERATOR_USER_ID") or env.get("ROCKETCHAT_BOT_USER_ID") or ""
    ).strip()
    if token and uid:
        return token, uid
    body = json.dumps(
        {
            "user": env["ROCKETCHAT_OPERATOR_USERNAME"],
            "password": env["ROCKETCHAT_OPERATOR_PASSWORD"],
        }
    ).encode()
    req = urllib.request.Request(
        f"{BASE_HTTP}/api/v1/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        d = json.loads(resp.read().decode())
    if d.get("status") != "success":
        raise RuntimeError(f"login failed: {d}")
    return d["data"]["authToken"], d["data"]["userId"]


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_ledger() -> dict:
    if not LEDGER.is_file():
        return {"confirmed_file_ids": [], "posts": []}
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"confirmed_file_ids": [], "posts": []}


def save_ledger(data: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    # Cap history
    data["confirmed_file_ids"] = list(data.get("confirmed_file_ids") or [])[-200:]
    data["posts"] = list(data.get("posts") or [])[-100:]
    LEDGER.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def upload_and_confirm(
    room_id: str,
    path: Path,
    *,
    msg: str,
    description: str = "",
    force: bool = False,
) -> dict:
    """
    rooms.media → rooms.mediaConfirm exactly once.

    Returns {success, file_id, msg_id, skipped?, reason?}
    """
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    digest = file_sha256(path)
    ledger = load_ledger()
    confirmed = set(ledger.get("confirmed_file_ids") or [])

    if not force:
        for p in ledger.get("posts") or []:
            if (
                p.get("room_id") == room_id
                and p.get("sha256") == digest
                and p.get("msg_id")
            ):
                return {
                    "success": True,
                    "skipped": True,
                    "reason": "same_bytes_already_posted_in_room",
                    "file_id": p.get("file_id"),
                    "msg_id": p.get("msg_id"),
                }

    token, uid = login()
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"

    # curl multipart is more reliable than hand-rolled boundaries
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "-H",
            f"X-Auth-Token: {token}",
            "-H",
            f"X-User-Id: {uid}",
            "-F",
            f"file=@{path};type={mime}",
            f"{BASE_HTTP}/api/v1/rooms.media/{room_id}",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"rooms.media curl failed: {proc.stderr or proc.stdout}")
    up = json.loads(proc.stdout)
    if not up.get("success"):
        raise RuntimeError(f"rooms.media failed: {up}")
    file_id = (up.get("file") or {}).get("_id")
    if not file_id:
        raise RuntimeError(f"rooms.media missing file id: {up}")

    if file_id in confirmed and not force:
        return {
            "success": True,
            "skipped": True,
            "reason": "file_id_already_confirmed",
            "file_id": file_id,
            "msg_id": None,
        }

    # Single confirm — never retry this call for the same file_id.
    body = json.dumps({"msg": msg or "", "description": description or ""}).encode()
    req = urllib.request.Request(
        f"{BASE_HTTP}/api/v1/rooms.mediaConfirm/{room_id}/{file_id}",
        data=body,
        headers={
            "X-Auth-Token": token,
            "X-User-Id": uid,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            conf = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        # Mark file_id claimed even on ambiguous errors so we do not double-confirm.
        confirmed.add(file_id)
        ledger["confirmed_file_ids"] = list(confirmed)
        save_ledger(ledger)
        raise RuntimeError(f"mediaConfirm failed: {e.read().decode()[:400]}") from e

    mid = (conf.get("message") or {}).get("_id")
    confirmed.add(file_id)
    ledger["confirmed_file_ids"] = list(confirmed)
    ledger.setdefault("posts", []).append(
        {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "room_id": room_id,
            "sha256": digest,
            "file_id": file_id,
            "msg_id": mid,
            "path": str(path),
            "msg": (msg or "")[:200],
        }
    )
    save_ledger(ledger)
    return {
        "success": bool(conf.get("success")),
        "skipped": False,
        "file_id": file_id,
        "msg_id": mid,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Idempotent RC media post")
    ap.add_argument("--room-id", required=True)
    ap.add_argument("--file", required=True, type=Path)
    ap.add_argument("--msg", default="")
    ap.add_argument("--description", default="")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    try:
        result = upload_and_confirm(
            args.room_id,
            args.file,
            msg=args.msg,
            description=args.description,
            force=args.force,
        )
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))
        return 1
    print(json.dumps(result))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
