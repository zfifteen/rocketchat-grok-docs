#!/usr/bin/env python3
"""
Local reverse proxy: one public hostname for Rocket.Chat (+ optional voice).

ngrok (HTTPS, branded domain) → this proxy (HTTP) →
  - everything → 127.0.0.1:3000 (RC) by default
  - voice paths → 127.0.0.1:8090 **only if** RC_PUBLIC_VOICE=1 (opt-in)

Security (Heavy review C1 / via_negativa 2026-07-17)
----------------------------------------------------
Path C Call used a lobby-free voice mesh. Publicly routing /Agency* and /ws
without RC join auth is an unauthenticated media plane on the same branded
host as chat. **Default is voice routing OFF.** Do not re-enable until WS
join requires an RC session/token (or keep voice loopback-only + private).

When voice is enabled (explicit opt-in):
  /Agency*          room pages (RC Jitsi URL shape)
  /ws               voice signaling WebSocket
  /voice-health     voice room /health (aliased; /health stays RC-safe)

Everything else goes to Rocket.Chat on :3000 (including RC websockets).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from typing import Iterable, Mapping

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web

LOG = logging.getLogger("rc_public_proxy")

DEFAULT_LISTEN = "127.0.0.1"
DEFAULT_PORT = 9080
DEFAULT_RC = "http://127.0.0.1:3000"
DEFAULT_VOICE = "http://127.0.0.1:8090"


def _env_truthy(raw: str | None) -> bool:
    if raw is None:
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def public_voice_enabled(env: Mapping[str, str] | None = None) -> bool:
    """RC_PUBLIC_VOICE — default OFF (C1: do not publish unauthenticated mesh)."""
    e = env if env is not None else os.environ
    # Explicit only — unset means disabled (not “legacy on”).
    return _env_truthy(str(e.get("RC_PUBLIC_VOICE", "") or ""))


def is_voice_path(path: str, *, voice_enabled: bool | None = None) -> bool:
    """True when the request must go to the lobby-free voice room."""
    if voice_enabled is None:
        voice_enabled = public_voice_enabled()
    if not voice_enabled:
        return False
    if not path:
        return False
    # normalize
    p = path if path.startswith("/") else f"/{path}"
    if p == "/ws" or p.startswith("/ws?"):
        return True
    if p == "/voice-health" or p.startswith("/voice-health?"):
        return True
    # RC Jitsi provider: /{titlePrefix}{callId} — we use Agency…
    first = p.lstrip("/").split("/", 1)[0]
    if first.startswith("Agency"):
        return True
    return False


def _upstream_base(path: str, rc: str, voice: str, *, voice_enabled: bool) -> str:
    return (
        voice.rstrip("/")
        if is_voice_path(path, voice_enabled=voice_enabled)
        else rc.rstrip("/")
    )


def _map_path(path: str) -> str:
    """Map public paths onto upstream paths where they differ."""
    if path == "/voice-health" or path.startswith("/voice-health?"):
        return "/health" + (path[len("/voice-health") :] if "?" in path else "")
    if path.startswith("/voice-health"):
        return "/health" + path[len("/voice-health") :]
    return path


async def proxy_http(request: web.Request) -> web.StreamResponse:
    rc = request.app["rc_base"]
    voice = request.app["voice_base"]
    voice_on = bool(request.app.get("voice_enabled"))
    path = request.rel_url.path
    # WebSocket upgrade handled separately
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return await proxy_ws(request)

    target_base = _upstream_base(path, rc, voice, voice_enabled=voice_on)
    upstream_path = _map_path(str(request.rel_url))
    url = f"{target_base}{upstream_path}"

    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower()
        not in (
            "host",
            "content-length",
            "transfer-encoding",
            "connection",
        )
    }
    body = await request.read()
    timeout = ClientTimeout(total=120)
    session: ClientSession = request.app["session"]
    try:
        async with session.request(
            request.method,
            url,
            headers=headers,
            data=body if body else None,
            timeout=timeout,
            allow_redirects=False,
        ) as resp:
            out_headers = {
                k: v
                for k, v in resp.headers.items()
                if k.lower()
                not in (
                    "transfer-encoding",
                    "content-encoding",
                    "content-length",
                    "connection",
                )
            }
            data = await resp.read()
            return web.Response(status=resp.status, body=data, headers=out_headers)
    except Exception as ex:
        LOG.warning("proxy_http fail method=%s url=%s err=%s", request.method, url, ex)
        return web.Response(status=502, text=f"proxy error: {type(ex).__name__}")


async def proxy_ws(request: web.Request) -> web.WebSocketResponse:
    rc = request.app["rc_base"]
    voice = request.app["voice_base"]
    voice_on = bool(request.app.get("voice_enabled"))
    path = request.rel_url.path
    target_base = _upstream_base(path, rc, voice, voice_enabled=voice_on)
    upstream_path = _map_path(str(request.rel_url))
    # aiohttp client ws wants http(s) URL
    ws_url = f"{target_base}{upstream_path}"

    client_ws = web.WebSocketResponse(heartbeat=20, autoping=True)
    await client_ws.prepare(request)

    session: ClientSession = request.app["session"]
    try:
        async with session.ws_connect(ws_url, heartbeat=20, autoping=True) as up_ws:

            async def client_to_up() -> None:
                async for msg in client_ws:
                    if msg.type == WSMsgType.TEXT:
                        await up_ws.send_str(msg.data)
                    elif msg.type == WSMsgType.BINARY:
                        await up_ws.send_bytes(msg.data)
                    elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                        await up_ws.close()
                        break

            async def up_to_client() -> None:
                async for msg in up_ws:
                    if msg.type == WSMsgType.TEXT:
                        await client_ws.send_str(msg.data)
                    elif msg.type == WSMsgType.BINARY:
                        await client_ws.send_bytes(msg.data)
                    elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                        await client_ws.close()
                        break

            await asyncio.gather(client_to_up(), up_to_client())
    except Exception as ex:
        LOG.warning("proxy_ws fail url=%s err=%s", ws_url, ex)
        if not client_ws.closed:
            await client_ws.close(code=1011, message=b"upstream ws failed")
    return client_ws


async def on_startup(app: web.Application) -> None:
    app["session"] = ClientSession()


async def on_cleanup(app: web.Application) -> None:
    session: ClientSession = app["session"]
    await session.close()


def build_app(
    *,
    rc_base: str,
    voice_base: str,
    voice_enabled: bool | None = None,
) -> web.Application:
    app = web.Application()
    app["rc_base"] = rc_base.rstrip("/")
    app["voice_base"] = voice_base.rstrip("/")
    app["voice_enabled"] = (
        public_voice_enabled() if voice_enabled is None else bool(voice_enabled)
    )
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_route("*", "/{path:.*}", proxy_http)
    app.router.add_route("*", "/", proxy_http)
    return app


def main(argv: Iterable[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    ap = argparse.ArgumentParser(description="RC + voice room public reverse proxy")
    ap.add_argument("--host", default=os.environ.get("RC_PUBLIC_PROXY_HOST", DEFAULT_LISTEN))
    ap.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("RC_PUBLIC_PROXY_PORT", str(DEFAULT_PORT))),
    )
    ap.add_argument("--rc", default=os.environ.get("RC_PUBLIC_PROXY_RC", DEFAULT_RC))
    ap.add_argument(
        "--voice", default=os.environ.get("RC_PUBLIC_PROXY_VOICE", DEFAULT_VOICE)
    )
    ap.add_argument(
        "--enable-public-voice",
        action="store_true",
        help="Opt-in: route /Agency* and /ws to voice (C1 risk if unauthenticated)",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)
    voice_on = bool(args.enable_public_voice) or public_voice_enabled()
    app = build_app(
        rc_base=args.rc, voice_base=args.voice, voice_enabled=voice_on
    )
    LOG.info(
        "public proxy listen=%s:%s rc=%s voice=%s public_voice=%s",
        args.host,
        args.port,
        args.rc,
        args.voice,
        voice_on,
    )
    if voice_on:
        LOG.warning(
            "RC_PUBLIC_VOICE/on: /Agency* and /ws route to unauthenticated mesh "
            "(Heavy C1). Prefer loopback voice + RC join auth before leaving on."
        )
    web.run_app(app, host=args.host, port=args.port, print=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
