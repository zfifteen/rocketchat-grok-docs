#!/usr/bin/env python3
"""
NF-SPEC-01 — LiveKit + Grok Voice Agent worker (primary media plane).

Joins a LiveKit room as identity `grok` and runs speech-to-speech via
Grok Voice Agent / Realtime bridge (`voice_audio_bridge.py`) — NOT Whisper
+ full Grok CLI + TTS.

CLI contract:
  voice_agent_worker.py --call-id ID --room-id RID [--room-name N]
    --livekit-room ROOM [--livekit-url URL]
    [--max-duration-s N] [--idle-timeout-s N] [--greeting TEXT]
    [--validate-only] [--token-file PATH] [--bridge-sim]

Exit codes:
  0  clean hangup / validate-only / bridge-sim success
  1  config / auth failure
  2  media / runtime failure
  124 max-duration timeout
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CALL_DIR = Path(__file__).resolve().parent
if str(_CALL_DIR) not in sys.path:
    sys.path.insert(0, str(_CALL_DIR))

from rc_call_media import (  # noqa: E402
    BRAIN_VOICE_AGENT,
    livekit_api_key,
    livekit_api_secret,
    livekit_join_url,
    livekit_url,
    mint_livekit_access_token,
    release_call_lock,
    room_name_from_call_id,
    token_contains_raw_secret,
    token_ttl_s,
    voice_greeting,
    voice_idle_timeout_s,
    voice_max_duration_s,
    xai_api_key,
)
from voice_audio_bridge import (  # noqa: E402
    AudioFrame,
    BridgeConfig,
    EndReason,
    VoiceAudioBridge,
    build_greeting_response_create,
    build_session_update,
    extract_audio_delta_pcm,
    pcm16_to_b64,
    simulate_greeting_duplex_session,
)

LOG_DIR = Path.home() / "logs" / "rocketchat-dm-wake"
WORKER_LOG = LOG_DIR / "voice-agent-worker.log"
LOCK_PATH = LOG_DIR / "call-bot.lock"
STATUS_PATH = LOG_DIR / "call-media-status.json"

_stop = False
_bridge_ref: VoiceAudioBridge | None = None


def log(msg: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}] {msg}"
    print(line, flush=True)
    with WORKER_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def write_status(payload: dict[str, Any]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        tmp = STATUS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.replace(STATUS_PATH)
    except OSError as e:
        log(f"status write failed: {e}")


def _handle_signal(signum: int, _frame: object) -> None:
    global _stop, _bridge_ref
    log(f"signal {signum} — hangup voice worker")
    _stop = True
    if _bridge_ref is not None:
        _bridge_ref.request_hangup()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="RC LiveKit + Grok Voice Agent worker")
    p.add_argument("--call-id", required=True)
    p.add_argument("--room-id", required=True)
    p.add_argument("--room-name", default="")
    p.add_argument("--livekit-room", default="")
    p.add_argument("--livekit-url", default="")
    p.add_argument("--max-duration-s", type=int, default=0)
    p.add_argument("--idle-timeout-s", type=int, default=0)
    p.add_argument("--greeting", default="")
    p.add_argument("--validate-only", action="store_true")
    p.add_argument(
        "--bridge-sim",
        action="store_true",
        help="Run pure duplex bridge simulation (no network); proves S2S path",
    )
    p.add_argument("--token-file", default="")
    p.add_argument("--identity", default="grok")
    return p.parse_args(argv)


def resolve_config(args: argparse.Namespace) -> dict:
    env = os.environ
    room = (args.livekit_room or "").strip() or room_name_from_call_id(args.call_id)
    url = (args.livekit_url or "").strip() or livekit_url(env)
    max_s = int(args.max_duration_s) if args.max_duration_s > 0 else voice_max_duration_s(env)
    idle_s = int(args.idle_timeout_s) if args.idle_timeout_s > 0 else voice_idle_timeout_s(env)
    greeting = (args.greeting or "").strip() or voice_greeting(env)
    return {
        "call_id": args.call_id.strip(),
        "room_id": args.room_id.strip(),
        "room_name": (args.room_name or "").strip(),
        "livekit_room": room,
        "livekit_url": url,
        "api_key": livekit_api_key(env),
        "api_secret": livekit_api_secret(env),
        "xai_key": xai_api_key(env),
        "max_duration_s": max_s,
        "idle_timeout_s": idle_s,
        "greeting": greeting,
        "identity": (args.identity or "grok").strip() or "grok",
        "brain": BRAIN_VOICE_AGENT,
        "ttl_s": token_ttl_s(env),
    }


def mint_worker_token(cfg: dict) -> str:
    token = mint_livekit_access_token(
        api_key=cfg["api_key"],
        api_secret=cfg["api_secret"],
        identity=cfg["identity"],
        room=cfg["livekit_room"],
        ttl_s=cfg["ttl_s"],
        name=cfg["identity"],
    )
    if token_contains_raw_secret(token, cfg["api_secret"]):
        raise RuntimeError("token embeds raw API secret — refuse")
    return token


def validate_config(cfg: dict) -> list[str]:
    problems: list[str] = []
    if not cfg["call_id"]:
        problems.append("call_id empty")
    if not cfg["room_id"]:
        problems.append("room_id empty")
    if not cfg["livekit_room"]:
        problems.append("livekit_room empty")
    if not cfg["livekit_url"]:
        problems.append("RC_LIVEKIT_URL / --livekit-url missing")
    if not cfg["api_key"]:
        problems.append("RC_LIVEKIT_API_KEY missing")
    if not cfg["api_secret"]:
        problems.append("RC_LIVEKIT_API_SECRET missing")
    return problems


def run_validate_only(cfg: dict, token_file: str = "") -> int:
    problems = validate_config(cfg)
    if problems:
        log(f"validate-only FAIL callId={cfg['call_id']}: {'; '.join(problems)}")
        return 1
    token = mint_worker_token(cfg)
    material = livekit_join_url(cfg["livekit_url"], token, room=cfg["livekit_room"])
    # Prove greeting bootstrap events are well-formed (bridge unit)
    bcfg = BridgeConfig(call_id=cfg["call_id"], greeting=cfg["greeting"])
    sess = build_session_update(bcfg)
    greet = build_greeting_response_create(bcfg)
    assert sess["type"] == "session.update"
    assert greet["type"] == "response.create"
    log(
        f"validate-only OK callId={cfg['call_id']} room={cfg['livekit_room']} "
        f"identity={cfg['identity']} brain={cfg['brain']} "
        f"token_len={len(token)} join_material_len={len(material)} "
        f"greeting_events=session.update+response.create"
    )
    if token_file:
        Path(token_file).write_text(token + "\n", encoding="utf-8")
    result = {
        "ok": True,
        "call_id": cfg["call_id"],
        "livekit_room": cfg["livekit_room"],
        "identity": cfg["identity"],
        "brain": cfg["brain"],
        "max_duration_s": cfg["max_duration_s"],
        "idle_timeout_s": cfg["idle_timeout_s"],
        "token_len": len(token),
        "uses_whisper_cli_tts_primary": False,
        "uses_playwright": False,
        "greeting_bootstrap": True,
        "bridge_module": "voice_audio_bridge",
    }
    print("VOICE_AGENT_VALIDATE " + json.dumps(result), flush=True)
    return 0


def run_bridge_sim(cfg: dict) -> int:
    """
    Drive shipped VoiceAudioBridge with fakes (no network).

    Proves S2S greeting + mic→realtime + reply publish without LiveKit deps.
    """
    log(f"bridge-sim start callId={cfg['call_id']} brain={cfg['brain']}")
    state = simulate_greeting_duplex_session(greeting=cfg["greeting"])
    result = {
        "ok": True,
        "mode": "bridge-sim",
        "call_id": cfg["call_id"],
        "brain": cfg["brain"],
        "state": state.to_dict(),
        "uses_whisper_cli_tts_primary": False,
        "uses_playwright": False,
    }
    print("VOICE_AGENT_BRIDGE_SIM " + json.dumps(result), flush=True)
    log(
        f"bridge-sim OK greeting_sent={state.greeting_sent} "
        f"out_frames={state.outbound_frames} in_frames={state.inbound_frames} "
        f"end={state.end_reason}"
    )
    write_status(
        {
            "phase": "ended",
            "call_id": cfg["call_id"],
            "reason": state.end_reason.value if state.end_reason else "clean",
            "backend": "livekit",
            "sim": True,
        }
    )
    return 0


# --- Live transports (require livekit + websockets) ---------------------------


class WebsocketRealtimeTransport:
    """Async-backed Realtime WS adapted to sync bridge via a queue pump."""

    def __init__(self, ws: Any, loop: asyncio.AbstractEventLoop):
        self._ws = ws
        self._loop = loop
        self._inbox: asyncio.Queue = asyncio.Queue()
        self._closed = False
        self._reader_task: asyncio.Task | None = None

    async def start_reader(self) -> None:
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            async for raw in self._ws:
                if self._closed:
                    break
                if isinstance(raw, (bytes, bytearray)):
                    await self._inbox.put(bytes(raw))
                else:
                    try:
                        await self._inbox.put(json.loads(raw))
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass

    def send_json(self, event: dict[str, Any]) -> None:
        fut = asyncio.run_coroutine_threadsafe(
            self._ws.send(json.dumps(event)), self._loop
        )
        fut.result(timeout=10)

    def recv(self, timeout_s: float = 1.0) -> dict[str, Any] | bytes | None:
        try:
            return self._inbox.get_nowait()
        except asyncio.QueueEmpty:
            pass
        # allow event loop to fill
        time.sleep(min(0.05, timeout_s))
        try:
            return self._inbox.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def close(self) -> None:
        self._closed = True
        try:
            fut = asyncio.run_coroutine_threadsafe(self._ws.close(), self._loop)
            fut.result(timeout=5)
        except Exception:
            pass


class LiveKitMediaTransport:
    """
    LiveKit RTC publish (LocalAudioTrack) + subscribe remote audio.

    Requires `livekit` package. Publishes PCM16 frames from Realtime deltas;
    polls remote participant audio into inbound queue for Realtime append.
    """

    def __init__(self, room: Any, sample_rate: int = 24000):
        self._room = room
        self._sample_rate = sample_rate
        self._inbound: list[AudioFrame] = []
        self._source: Any = None
        self._track: Any = None
        self._closed = False

    async def setup_publish(self) -> None:
        from livekit import rtc  # type: ignore

        self._source = rtc.AudioSource(self._sample_rate, 1)
        self._track = rtc.LocalAudioTrack.create_audio_track("grok-voice", self._source)
        opts = rtc.TrackPublishOptions()
        opts.source = rtc.TrackSource.SOURCE_MICROPHONE
        await self._room.local_participant.publish_track(self._track, opts)
        log("livekit published local audio track grok-voice")

        @self._room.on("track_subscribed")
        def _on_sub(track, publication, participant):  # type: ignore
            if track.kind == rtc.TrackKind.KIND_AUDIO:
                log(f"subscribed remote audio from {participant.identity}")
                audio_stream = rtc.AudioStream(track)

                async def _consume() -> None:
                    async for ev in audio_stream:
                        if self._closed:
                            break
                        frame = ev.frame
                        # convert to pcm16 bytes
                        data = bytes(frame.data)
                        self._inbound.append(
                            AudioFrame(
                                pcm=data,
                                sample_rate=frame.sample_rate or self._sample_rate,
                            )
                        )

                asyncio.create_task(_consume())

    def publish_pcm(self, frame: AudioFrame) -> None:
        if self._source is None or not frame.pcm:
            return
        from livekit import rtc  # type: ignore

        samples = len(frame.pcm) // 2
        audio = rtc.AudioFrame(
            data=frame.pcm,
            sample_rate=frame.sample_rate or self._sample_rate,
            num_channels=1,
            samples_per_channel=samples,
        )
        # capture_frame is async in some versions — schedule best-effort
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self._source.capture_frame(audio))
            else:
                loop.run_until_complete(self._source.capture_frame(audio))
        except Exception:
            try:
                # sync fallback if API allows
                self._source.capture_frame(audio)  # type: ignore
            except Exception as e:
                log(f"publish_pcm failed: {e}")

    def poll_inbound_pcm(self, timeout_s: float = 0.05) -> AudioFrame | None:
        if self._inbound:
            return self._inbound.pop(0)
        return None

    def close(self) -> None:
        self._closed = True


async def run_live_session(cfg: dict, token: str) -> int:
    """
    Full path: LiveKit room + xAI Realtime WS + VoiceAudioBridge.

    Primary turn loop is Realtime S2S via bridge (FR-V4).
    """
    global _bridge_ref, _stop
    try:
        import websockets  # type: ignore
        from livekit import rtc  # type: ignore
    except ImportError as e:
        log(f"missing runtime dep: {e}")
        log("pip install livekit websockets  (see requirements.txt)")
        return 2

    ws_url = f"wss://api.x.ai/v1/realtime?model=grok-voice-latest"
    headers = {"Authorization": f"Bearer {cfg['xai_key']}"}
    log(f"realtime+livekit session callId={cfg['call_id']} room={cfg['livekit_room']}")

    write_status(
        {
            "phase": "connecting",
            "call_id": cfg["call_id"],
            "backend": "livekit",
            "brain": cfg["brain"],
        }
    )

    room = rtc.Room()
    await room.connect(cfg["livekit_url"], token)
    log(
        f"livekit connected room={cfg['livekit_room']} "
        f"local={getattr(room.local_participant, 'identity', '?')}"
    )

    media = LiveKitMediaTransport(room, sample_rate=24000)
    await media.setup_publish()

    try:
        async with websockets.connect(
            ws_url,
            additional_headers=headers,
            max_size=16 * 1024 * 1024,
            open_timeout=30,
        ) as ws:
            loop = asyncio.get_event_loop()
            # Use async-native loop instead of sync bridge for live path
            bcfg = BridgeConfig(
                call_id=cfg["call_id"],
                greeting=cfg["greeting"],
                max_duration_s=cfg["max_duration_s"],
                idle_timeout_s=cfg["idle_timeout_s"],
            )
            # Bootstrap greeting on Realtime
            await ws.send(json.dumps(build_session_update(bcfg)))
            await ws.send(json.dumps(build_greeting_response_create(bcfg)))
            log(
                f"greeting bootstrap sent callId={cfg['call_id']} "
                f"session.update+response.create"
            )

            started = time.time()
            last_activity = started
            outbound_frames = 0
            inbound_frames = 0
            greeting_audio = 0

            while not _stop:
                now = time.time()
                if now - started >= cfg["max_duration_s"]:
                    log("max duration reached")
                    write_status(
                        {
                            "phase": "ended",
                            "call_id": cfg["call_id"],
                            "reason": "max_duration",
                            "backend": "livekit",
                        }
                    )
                    await room.disconnect()
                    return 124
                if now - last_activity >= cfg["idle_timeout_s"]:
                    log("idle timeout")
                    write_status(
                        {
                            "phase": "ended",
                            "call_id": cfg["call_id"],
                            "reason": "idle_timeout",
                            "backend": "livekit",
                        }
                    )
                    await room.disconnect()
                    return 0

                # mic → realtime
                frame = media.poll_inbound_pcm(0.0)
                if frame and frame.pcm:
                    await ws.send(
                        json.dumps(
                            {
                                "type": "input_audio_buffer.append",
                                "audio": pcm16_to_b64(frame.pcm),
                            }
                        )
                    )
                    inbound_frames += 1
                    last_activity = now

                # realtime → publish
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=0.2)
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    log(f"realtime recv error: {e}")
                    break
                last_activity = time.time()
                if isinstance(raw, (bytes, bytearray)):
                    media.publish_pcm(AudioFrame(pcm=bytes(raw)))
                    outbound_frames += 1
                    continue
                try:
                    ev = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                et = ev.get("type") or ""
                if et == "error":
                    log(f"realtime error event: {ev.get('error') or ev}")
                    write_status(
                        {
                            "phase": "failed",
                            "call_id": cfg["call_id"],
                            "reason": "remote_error",
                            "backend": "livekit",
                        }
                    )
                    await room.disconnect()
                    return 2
                pcm = extract_audio_delta_pcm(ev)
                if pcm:
                    media.publish_pcm(AudioFrame(pcm=pcm))
                    outbound_frames += 1
                    if outbound_frames <= 32:
                        greeting_audio += 1
                    last_activity = time.time()

            log(
                f"session loop exit stop={_stop} out={outbound_frames} "
                f"in={inbound_frames} greeting_audio={greeting_audio}"
            )
            write_status(
                {
                    "phase": "ended",
                    "call_id": cfg["call_id"],
                    "reason": "hangup" if _stop else "clean",
                    "backend": "livekit",
                    "outbound_frames": outbound_frames,
                    "inbound_frames": inbound_frames,
                    "greeting_audio_frames": greeting_audio,
                }
            )
            await room.disconnect()
            return 0
    except Exception as e:
        log(f"live session failed: {e}")
        write_status(
            {
                "phase": "failed",
                "call_id": cfg["call_id"],
                "reason": str(e)[:200],
                "backend": "livekit",
            }
        )
        try:
            await room.disconnect()
        except Exception:
            pass
        return 2


def release_lock_if_ours(call_id: str) -> None:
    try:
        release_call_lock(LOCK_PATH, call_id=call_id, only_if_call_id=True)
        log(f"released call lock callId={call_id}")
    except Exception as e:
        log(f"lock release: {e}")


def main(argv: list[str] | None = None) -> int:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    args = parse_args(argv)
    cfg = resolve_config(args)
    log(
        f"worker start callId={cfg['call_id']} rid={cfg['room_id']} "
        f"lk_room={cfg['livekit_room']} validate_only={args.validate_only} "
        f"bridge_sim={args.bridge_sim} brain={cfg['brain']}"
    )

    if args.bridge_sim:
        try:
            return run_bridge_sim(cfg)
        finally:
            release_lock_if_ours(cfg["call_id"])

    if args.validate_only:
        return run_validate_only(cfg, token_file=args.token_file or "")

    problems = validate_config(cfg)
    if problems:
        log(f"config invalid: {'; '.join(problems)}")
        write_status(
            {
                "phase": "failed",
                "call_id": cfg["call_id"],
                "reason": "; ".join(problems),
                "backend": "livekit",
            }
        )
        release_lock_if_ours(cfg["call_id"])
        return 1
    if not cfg["xai_key"]:
        log("XAI_API_KEY missing")
        write_status(
            {
                "phase": "failed",
                "call_id": cfg["call_id"],
                "reason": "XAI_API_KEY missing",
                "backend": "livekit",
            }
        )
        release_lock_if_ours(cfg["call_id"])
        return 1

    try:
        token = mint_worker_token(cfg)
    except Exception as e:
        log(f"token mint failed: {e}")
        release_lock_if_ours(cfg["call_id"])
        return 1

    if args.token_file:
        try:
            Path(args.token_file).write_text(token + "\n", encoding="utf-8")
        except OSError as e:
            log(f"token-file write failed: {e}")

    try:
        rc = asyncio.run(run_live_session(cfg, token))
    except Exception as e:
        log(f"asyncio session failed: {e}")
        rc = 2
    finally:
        release_lock_if_ours(cfg["call_id"])
    log(f"worker exit {rc} callId={cfg['call_id']}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
