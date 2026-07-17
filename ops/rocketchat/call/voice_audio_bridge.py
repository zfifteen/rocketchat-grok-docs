#!/usr/bin/env python3
"""
NF-SPEC-01 — LiveKit audio ↔ Grok Voice Agent Realtime bridge (pure logic).

Unit-testable without LiveKit SFU, phone, or network: all I/O goes through
injectable transport protocols. This is the speech-to-speech turn loop —
NOT Whisper + Grok CLI + TTS.

Contracts:
- Session bootstrap + server VAD + greeting response.create
- Inbound mic PCM → Realtime input_audio_buffer.append (base64)
- Realtime response.audio.delta → outbound PCM frames for LiveKit publish
- Idle / max-duration / hangup end reasons
- Never embeds API secrets in outbound event payloads beyond Authorization
  (Authorization is the transport's job; bridge never logs secrets)
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol


# Realtime / LiveKit common audio: 24 kHz mono PCM16 for xAI Voice Agent
DEFAULT_SAMPLE_RATE = 24000
DEFAULT_CHANNELS = 1
DEFAULT_SAMPLE_WIDTH = 2  # PCM16


class EndReason(str, Enum):
    HANGUP = "hangup"
    IDLE_TIMEOUT = "idle_timeout"
    MAX_DURATION = "max_duration"
    REMOTE_ERROR = "remote_error"
    CLEAN = "clean"


@dataclass
class AudioFrame:
    """Raw PCM16 mono frame (little-endian bytes)."""

    pcm: bytes
    sample_rate: int = DEFAULT_SAMPLE_RATE
    channels: int = DEFAULT_CHANNELS
    ts: float = 0.0

    @property
    def duration_s(self) -> float:
        if not self.pcm or self.sample_rate <= 0:
            return 0.0
        samples = len(self.pcm) // (DEFAULT_SAMPLE_WIDTH * max(1, self.channels))
        return samples / float(self.sample_rate)


@dataclass
class BridgeConfig:
    call_id: str
    greeting: str = "Hello, Grok speaking."
    max_duration_s: int = 1800
    idle_timeout_s: int = 120
    sample_rate: int = DEFAULT_SAMPLE_RATE
    identity: str = "grok"
    model: str = "grok-voice-latest"
    voice: str = "Ara"
    instructions_prefix: str = (
        "You are Grok on a Rocket.Chat voice call. Keep spoken replies concise."
    )


class RealtimeTransport(Protocol):
    """Outbound/inbound Realtime WebSocket events (JSON text or binary)."""

    def send_json(self, event: dict[str, Any]) -> None: ...
    def recv(self, timeout_s: float = 1.0) -> dict[str, Any] | bytes | None: ...
    def close(self) -> None: ...


class MediaTransport(Protocol):
    """LiveKit-side mic subscribe + TTS publish (audio only)."""

    def publish_pcm(self, frame: AudioFrame) -> None: ...
    def poll_inbound_pcm(self, timeout_s: float = 0.05) -> AudioFrame | None: ...
    def close(self) -> None: ...


def pcm16_to_b64(pcm: bytes) -> str:
    """Encode PCM16 for Realtime input_audio_buffer.append."""
    return base64.b64encode(pcm).decode("ascii")


def b64_to_pcm16(data: str) -> bytes:
    """Decode Realtime response.audio.delta payload to PCM16 bytes."""
    raw = (data or "").strip()
    if not raw:
        return b""
    # tolerate missing padding
    pad = "=" * (-len(raw) % 4)
    return base64.b64decode(raw + pad)


def build_session_update(cfg: BridgeConfig) -> dict[str, Any]:
    """Realtime session.update with server VAD + collab-safe instructions."""
    instructions = (
        f"{cfg.instructions_prefix} "
        f"When the session starts, greet the caller briefly with exactly: "
        f"{cfg.greeting!r}."
    )
    return {
        "type": "session.update",
        "session": {
            "modalities": ["text", "audio"],
            "instructions": instructions,
            "voice": cfg.voice,
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 500,
            },
        },
    }


def build_greeting_response_create(cfg: BridgeConfig) -> dict[str, Any]:
    """
    Force an initial spoken response so greeting is not instruction-only.

    Realtime models often need response.create after session.update to speak.
    """
    return {
        "type": "response.create",
        "response": {
            "modalities": ["audio", "text"],
            "instructions": (
                f"Say only this greeting, then wait for the caller: {cfg.greeting}"
            ),
        },
    }


def build_input_audio_append(pcm: bytes) -> dict[str, Any]:
    return {
        "type": "input_audio_buffer.append",
        "audio": pcm16_to_b64(pcm),
    }


def build_input_audio_commit() -> dict[str, Any]:
    return {"type": "input_audio_buffer.commit"}


def extract_audio_delta_pcm(event: dict[str, Any]) -> bytes | None:
    """
    Pull PCM bytes from a Realtime audio delta event.

    Supports common shapes:
      - type=response.audio.delta, delta=<b64>
      - type=response.output_audio.delta, delta=<b64>
    """
    et = str(event.get("type") or "")
    if et not in (
        "response.audio.delta",
        "response.output_audio.delta",
        "response.audio_transcript.delta",  # not audio — skip
    ):
        if "audio" not in et or "delta" not in et:
            return None
        if "transcript" in et:
            return None
    delta = event.get("delta") or event.get("audio")
    if not isinstance(delta, str) or not delta:
        return None
    if et.endswith("transcript.delta") or "transcript" in et:
        return None
    try:
        return b64_to_pcm16(delta)
    except Exception:
        return None


def is_activity_event(event: dict[str, Any]) -> bool:
    et = str(event.get("type") or "")
    return et in {
        "response.done",
        "response.audio.done",
        "response.output_audio.done",
        "input_audio_buffer.speech_started",
        "input_audio_buffer.speech_stopped",
        "conversation.item.input_audio_transcription.completed",
        "response.created",
    } or et.endswith(".delta")


def is_fatal_error_event(event: dict[str, Any]) -> bool:
    return str(event.get("type") or "") == "error"


@dataclass
class BridgeState:
    started_at: float | None = None
    last_activity_at: float | None = None
    greeting_sent: bool = False
    greeting_audio_frames: int = 0
    inbound_frames: int = 0
    outbound_frames: int = 0
    realtime_events: int = 0
    ended: bool = False
    end_reason: EndReason | None = None
    published_pcm_bytes: int = 0
    subscribed_pcm_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "greeting_sent": self.greeting_sent,
            "greeting_audio_frames": self.greeting_audio_frames,
            "inbound_frames": self.inbound_frames,
            "outbound_frames": self.outbound_frames,
            "realtime_events": self.realtime_events,
            "ended": self.ended,
            "end_reason": self.end_reason.value if self.end_reason else None,
            "published_pcm_bytes": self.published_pcm_bytes,
            "subscribed_pcm_bytes": self.subscribed_pcm_bytes,
        }


@dataclass
class VoiceAudioBridge:
    """
    Synchronous-step bridge: call step() in a loop until ended.

    Designed so unit tests inject FakeRealtimeTransport + FakeMediaTransport
    and drive greeting + duplex without network.
    """

    cfg: BridgeConfig
    realtime: RealtimeTransport
    media: MediaTransport
    now_fn: Callable[[], float] = field(default=time.time)
    state: BridgeState = field(default_factory=BridgeState)
    _hangup: bool = False

    def request_hangup(self) -> None:
        """Operator/worker SIGTERM path (FR-V6)."""
        self._hangup = True

    def start(self) -> None:
        """Send session.update + greeting response.create; mark greeting_sent."""
        t0 = self.now_fn()
        self.state.started_at = t0
        self.state.last_activity_at = t0
        self.realtime.send_json(build_session_update(self.cfg))
        self.realtime.send_json(build_greeting_response_create(self.cfg))
        self.state.greeting_sent = True
        self.state.last_activity_at = self.now_fn()

    def should_end(self) -> EndReason | None:
        if self._hangup:
            return EndReason.HANGUP
        now = self.now_fn()
        # Use explicit None checks — epoch 0.0 is a valid fake-clock start.
        if self.state.started_at is not None and (
            now - self.state.started_at
        ) >= self.cfg.max_duration_s:
            return EndReason.MAX_DURATION
        if self.state.last_activity_at is not None and (
            now - self.state.last_activity_at
        ) >= self.cfg.idle_timeout_s:
            return EndReason.IDLE_TIMEOUT
        return None

    def _handle_realtime_event(self, event: dict[str, Any]) -> None:
        self.state.realtime_events += 1
        if is_fatal_error_event(event):
            self.state.ended = True
            self.state.end_reason = EndReason.REMOTE_ERROR
            return
        if is_activity_event(event):
            self.state.last_activity_at = self.now_fn()
        pcm = extract_audio_delta_pcm(event)
        if pcm:
            frame = AudioFrame(
                pcm=pcm,
                sample_rate=self.cfg.sample_rate,
                ts=self.now_fn(),
            )
            self.media.publish_pcm(frame)
            self.state.outbound_frames += 1
            self.state.published_pcm_bytes += len(pcm)
            self.state.last_activity_at = self.now_fn()
            # First audio deltas after greeting_sent count as greeting audio
            if self.state.greeting_sent and self.state.outbound_frames <= 32:
                self.state.greeting_audio_frames += 1

    def _pump_inbound_mic(self) -> None:
        frame = self.media.poll_inbound_pcm(timeout_s=0.0)
        if frame is None or not frame.pcm:
            return
        self.realtime.send_json(build_input_audio_append(frame.pcm))
        self.state.inbound_frames += 1
        self.state.subscribed_pcm_bytes += len(frame.pcm)
        self.state.last_activity_at = self.now_fn()

    def step(self) -> bool:
        """
        One bridge tick. Returns False when session has ended.

        Order: check end → mic → realtime recv → publish audio deltas.
        """
        if self.state.ended:
            return False
        reason = self.should_end()
        if reason is not None:
            self.state.ended = True
            self.state.end_reason = reason
            return False

        # Inbound principal mic → Realtime
        self._pump_inbound_mic()

        # Realtime events → outbound publish
        msg = self.realtime.recv(timeout_s=0.05)
        if msg is None:
            return True
        if isinstance(msg, (bytes, bytearray)):
            # binary audio frames if transport delivers them
            frame = AudioFrame(pcm=bytes(msg), sample_rate=self.cfg.sample_rate)
            self.media.publish_pcm(frame)
            self.state.outbound_frames += 1
            self.state.published_pcm_bytes += len(frame.pcm)
            self.state.last_activity_at = self.now_fn()
            return True
        if isinstance(msg, dict):
            self._handle_realtime_event(msg)
        return not self.state.ended

    def run_until_end(self, *, max_steps: int = 1_000_000) -> BridgeState:
        """Drive the loop (tests use small max_steps + fake clock)."""
        if not self.state.greeting_sent:
            self.start()
        for _ in range(max_steps):
            if not self.step():
                break
        if not self.state.ended:
            self.state.ended = True
            self.state.end_reason = self.state.end_reason or EndReason.CLEAN
        try:
            self.realtime.close()
        except Exception:
            pass
        try:
            self.media.close()
        except Exception:
            pass
        return self.state


# --- Test fakes (also usable as dry-run transports) ---------------------------


class FakeRealtimeTransport:
    """In-memory Realtime peer for unit tests."""

    def __init__(self, scripted: list[dict[str, Any] | bytes] | None = None):
        self.sent: list[dict[str, Any]] = []
        self._inbox: list[dict[str, Any] | bytes] = list(scripted or [])
        self.closed = False

    def send_json(self, event: dict[str, Any]) -> None:
        self.sent.append(event)

    def recv(self, timeout_s: float = 1.0) -> dict[str, Any] | bytes | None:
        if self._inbox:
            return self._inbox.pop(0)
        return None

    def close(self) -> None:
        self.closed = True

    def push(self, event: dict[str, Any] | bytes) -> None:
        self._inbox.append(event)


class FakeMediaTransport:
    """Records published frames; supplies scripted inbound mic frames."""

    def __init__(self, inbound: list[AudioFrame] | None = None):
        self.published: list[AudioFrame] = []
        self._inbound: list[AudioFrame] = list(inbound or [])
        self.closed = False

    def publish_pcm(self, frame: AudioFrame) -> None:
        self.published.append(frame)

    def poll_inbound_pcm(self, timeout_s: float = 0.05) -> AudioFrame | None:
        if self._inbound:
            return self._inbound.pop(0)
        return None

    def close(self) -> None:
        self.closed = True


def simulate_greeting_duplex_session(
    *,
    greeting: str = "Hello, Grok speaking.",
    greeting_pcm: bytes | None = None,
    mic_pcm: bytes | None = None,
    reply_pcm: bytes | None = None,
) -> BridgeState:
    """
    Pure end-to-end simulation of greeting + one spoken turn (no network).

    Proves the bridge:
    1) sends session.update + response.create (greeting)
    2) publishes greeting audio deltas to media
    3) forwards mic PCM to Realtime append
    4) publishes reply audio
    """
    g_pcm = greeting_pcm if greeting_pcm is not None else b"\x01\x00" * 240  # 10ms @24k
    m_pcm = mic_pcm if mic_pcm is not None else b"\x02\x00" * 480
    r_pcm = reply_pcm if reply_pcm is not None else b"\x03\x00" * 240

    rt = FakeRealtimeTransport(
        scripted=[
            {
                "type": "response.audio.delta",
                "delta": pcm16_to_b64(g_pcm),
            },
            {"type": "response.audio.done"},
            {"type": "response.done"},
            # after mic, model replies
            {
                "type": "response.audio.delta",
                "delta": pcm16_to_b64(r_pcm),
            },
            {"type": "response.done"},
        ]
    )
    media = FakeMediaTransport(inbound=[AudioFrame(pcm=m_pcm)])
    clock = {"t": 1000.0}

    def now() -> float:
        return clock["t"]

    bridge = VoiceAudioBridge(
        cfg=BridgeConfig(
            call_id="sim-1",
            greeting=greeting,
            max_duration_s=60,
            idle_timeout_s=30,
        ),
        realtime=rt,
        media=media,
        now_fn=now,
    )
    bridge.start()
    # advance through greeting audio + mic + reply
    for _ in range(20):
        clock["t"] += 0.1
        if not bridge.step():
            break
    # hangup cleanly
    bridge.request_hangup()
    bridge.step()
    state = bridge.state
    if not state.ended:
        state.ended = True
        state.end_reason = EndReason.HANGUP
    # assertions for callers
    assert state.greeting_sent
    assert any(e.get("type") == "session.update" for e in rt.sent)
    assert any(e.get("type") == "response.create" for e in rt.sent)
    assert any(e.get("type") == "input_audio_buffer.append" for e in rt.sent)
    assert state.outbound_frames >= 2
    assert state.inbound_frames >= 1
    assert state.published_pcm_bytes > 0
    assert state.subscribed_pcm_bytes > 0
    return state
