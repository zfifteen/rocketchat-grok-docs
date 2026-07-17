#!/usr/bin/env python3
"""
Lobby-free WebRTC mesh voice room for Rocket.Chat Call (VideoConf/Jitsi URL shape).

RC Jitsi provider generates:  {http|https}://{domain}/{titlePrefix}{callId}
This server serves a room page at /{roomName} and WebSocket signaling at /ws.

No moderator/lobby. Two peers join the same room path and exchange audio via WebRTC.

Security: default bind is **127.0.0.1** (not 0.0.0.0). Public exposure requires an
authenticated join policy + explicit RC_PUBLIC_VOICE=1 on the reverse proxy.
Join currently accepts room/name only — do not publish this process.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import ssl
import uuid
from http import HTTPStatus
from pathlib import Path

from aiohttp import WSMsgType, web

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
ROOM_HTML = STATIC / "room.html"
LOG = logging.getLogger("voice_room")

# room_name -> { peer_id: WebSocketResponse, meta }
ROOMS: dict[str, dict[str, dict]] = {}


def _room_name_from_path(path: str) -> str:
    # /Agency6a... or /Agency6a.../extra
    parts = [p for p in path.split("/") if p]
    if not parts:
        return "default"
    return parts[0]


async def index(_request: web.Request) -> web.Response:
    return web.Response(
        text=(
            "RC voice room server. Join via /{roomId} "
            "(same path RC VideoConf/Jitsi provider generates)."
        ),
        content_type="text/plain",
    )


async def health(_request: web.Request) -> web.Response:
    return web.json_response(
        {
            "ok": True,
            "rooms": {k: len(v) for k, v in ROOMS.items()},
            "service": "rc-voice-room",
        }
    )


async def room_page(request: web.Request) -> web.Response:
    if not ROOM_HTML.is_file():
        raise web.HTTPInternalServerError(text="room.html missing")
    # Serve SPA shell; room id is path (and optional query)
    html = ROOM_HTML.read_text(encoding="utf-8")
    return web.Response(text=html, content_type="text/html")


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    room = request.query.get("room") or "default"
    name = request.query.get("name") or "Guest"
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    peer_id = uuid.uuid4().hex[:12]

    peers = ROOMS.setdefault(room, {})
    # notify existing
    existing = [
        {"id": pid, "name": meta.get("name")}
        for pid, meta in peers.items()
    ]
    peers[peer_id] = {"ws": ws, "name": name}
    LOG.info("join room=%s peer=%s name=%s peers=%d", room, peer_id, name, len(peers))

    await ws.send_json(
        {"type": "welcome", "id": peer_id, "room": room, "peers": existing}
    )
    # announce to others
    dead: list[str] = []
    for pid, meta in peers.items():
        if pid == peer_id:
            continue
        try:
            await meta["ws"].send_json(
                {"type": "peer-join", "id": peer_id, "name": name}
            )
        except Exception:
            dead.append(pid)
    for pid in dead:
        peers.pop(pid, None)

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue
                if data.get("type") != "signal":
                    continue
                to = data.get("to")
                payload = data.get("data")
                if not to or to not in peers:
                    continue
                try:
                    await peers[to]["ws"].send_json(
                        {
                            "type": "signal",
                            "from": peer_id,
                            "data": payload,
                        }
                    )
                except Exception:
                    peers.pop(to, None)
            elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                break
    finally:
        peers.pop(peer_id, None)
        LOG.info("leave room=%s peer=%s left=%d", room, peer_id, len(peers))
        for pid, meta in list(peers.items()):
            try:
                await meta["ws"].send_json({"type": "peer-leave", "id": peer_id})
            except Exception:
                peers.pop(pid, None)
        if not peers:
            ROOMS.pop(room, None)
    return ws


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/health", health)
    app.router.add_get("/ws", websocket_handler)
    # Catch room paths used by RC Jitsi provider
    app.router.add_get("/{room:.*}", room_page)
    return app


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    ap = argparse.ArgumentParser(description="RC lobby-free voice room")
    ap.add_argument(
        "--host",
        default=os.environ.get("RC_VOICE_ROOM_HOST", "127.0.0.1"),
        help="Bind address (default 127.0.0.1 — not 0.0.0.0; C1)",
    )
    ap.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("RC_VOICE_ROOM_PORT", "8090")),
    )
    ap.add_argument("--cert", default=os.environ.get("RC_VOICE_ROOM_CERT", ""))
    ap.add_argument("--key", default=os.environ.get("RC_VOICE_ROOM_KEY", ""))
    args = ap.parse_args()

    ssl_ctx = None
    if args.cert and args.key:
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(args.cert, args.key)
        LOG.info("TLS enabled cert=%s", args.cert)

    app = build_app()
    LOG.info("listening on %s:%s", args.host, args.port)
    web.run_app(app, host=args.host, port=args.port, ssl_context=ssl_ctx, print=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
