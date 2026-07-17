#!/usr/bin/env python3
"""
Rocket.Chat Call media bot for user `grok`.

When principal presses Call, this process:
  1) video-conference.join as grok (stops "Calling…" / registers callee)
  2) opens the Jitsi URL in Chromium (Playwright)
  3) injects a virtual mic (Web Audio) for TTS
  4) says "Hello, Grok speaking."
  5) listen → Whisper STT → headless Grok (same room session) → TTS → loop

This is Path C MVP: real call answer + speaking-mode conversation.
Not production telephony; relies on meet.jit.si + local Whisper + macOS `say`.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Shared wake helpers (same session pins as text operator)
WAKE_DIR = Path.home() / ".grok" / "agency" / "ops" / "rocketchat" / "wake"
sys.path.insert(0, str(WAKE_DIR))
from wake_lib import (  # noqa: E402
    build_wake_argv,
    extract_session_id_from_output,
    get_room_cwd,
    get_room_session_id,
    load_env,
    load_state,
    resolve_approval_mode,
    save_state,
    set_room_cwd,
    set_room_session_id,
)

# Defaults; apply_call_config() rewrites from load_rc_config (IMP-03).
AGENCY = Path.home() / ".grok" / "agency"
SECRETS = AGENCY / "secrets" / "rocketchat.env"
STATE_PATH = WAKE_DIR / "state.json"
LOG_DIR = Path.home() / "logs" / "rocketchat-dm-wake"
CALL_LOG = LOG_DIR / "call-bot.log"
CALL_MEDIA = LOG_DIR / "call-media"
GROK_BIN = os.environ.get("GROK_BIN", str(Path.home() / ".local" / "bin" / "grok"))
WHISPER_BIN = os.environ.get("RC_WHISPER_BIN", "whisper")
WHISPER_MODEL = os.environ.get("RC_WHISPER_MODEL", "base")
WHISPER_LANGUAGE = os.environ.get("RC_WHISPER_LANGUAGE", "en")
# Ava is Premium-only on many Macs and fails with say -v; Samantha is free/reliable.
SAY_VOICE = os.environ.get("RC_CALL_SAY_VOICE", "Samantha")
GREETING = os.environ.get("RC_CALL_GREETING", "Hello, Grok speaking.")
BASE_HTTP = os.environ.get("RC_BASE", "http://127.0.0.1:3000")
OPERATOR = "grok"
MAX_CALL_S = int(os.environ.get("RC_CALL_MAX_S", "900"))  # 15 min


def apply_call_config() -> None:
    """IMP-03: apply shared rc_config paths into this process."""
    global AGENCY, SECRETS, STATE_PATH, LOG_DIR, CALL_LOG, CALL_MEDIA, GROK_BIN, BASE_HTTP
    try:
        from rc_config import load_rc_config

        cfg = load_rc_config(require_secrets=True)
        AGENCY = cfg.agency_path
        SECRETS = cfg.secrets_path
        LOG_DIR = cfg.log_dir
        CALL_LOG = LOG_DIR / "call-bot.log"
        CALL_MEDIA = LOG_DIR / "call-media"
        STATE_PATH = AGENCY / "ops" / "rocketchat" / "wake" / "state.json"
        GROK_BIN = cfg.grok_bin
        BASE_HTTP = cfg.rc_base.rstrip("/")
        os.environ.setdefault("RC_BASE", BASE_HTTP)
    except Exception as e:
        # log() defined below; print fallback if called too early
        try:
            log(f"call config apply skipped: {e}")
        except Exception:
            print(f"call config apply skipped: {e}", flush=True)
LISTEN_CHUNK_S = float(os.environ.get("RC_CALL_LISTEN_CHUNK_S", "0.6"))
SILENCE_END_S = float(os.environ.get("RC_CALL_SILENCE_END_S", "1.4"))
MIN_SPEECH_S = float(os.environ.get("RC_CALL_MIN_SPEECH_S", "0.8"))
RMS_SPEECH = float(os.environ.get("RC_CALL_RMS_SPEECH", "0.012"))
HEADLESS = os.environ.get("RC_CALL_HEADLESS", "1").strip() not in ("0", "false", "no")


def log(msg: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}] {msg}"
    print(line, flush=True)
    with CALL_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def http_api(
    method: str,
    path: str,
    token: str,
    uid: str,
    body: dict | None = None,
) -> dict:
    data = None if body is None else json.dumps(body).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Auth-Token": token,
        "X-User-Id": uid,
    }
    req = urllib.request.Request(
        f"{BASE_HTTP}{path}", data=data, headers=headers, method=method
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def login_operator() -> tuple[str, str]:
    apply_call_config()
    env = load_env(SECRETS)
    token = (env.get("ROCKETCHAT_OPERATOR_TOKEN") or env.get("ROCKETCHAT_BOT_TOKEN") or "").strip()
    uid = (
        env.get("ROCKETCHAT_OPERATOR_USER_ID") or env.get("ROCKETCHAT_BOT_USER_ID") or ""
    ).strip()
    if token and uid:
        return token, uid
    body = {
        "user": env["ROCKETCHAT_OPERATOR_USERNAME"],
        "password": env["ROCKETCHAT_OPERATOR_PASSWORD"],
    }
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE_HTTP}/api/v1/login",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        d = json.loads(resp.read().decode())
    if d.get("status") != "success":
        raise RuntimeError(f"login failed: {d}")
    return d["data"]["authToken"], d["data"]["userId"]


def _is_voice_room_url(url: str) -> bool:
    """True for lobby-free RC voice room (non-meet.jit.si VideoConf target)."""
    u = (url or "").lower()
    if "meet.jit.si" in u:
        return False
    # Our voice_room server or any non-Jitsi http target for VideoConf
    return u.startswith("http://") or u.startswith("https://")


def _local_lan_hosts() -> set[str]:
    """IPs/hosts that mean “this Mac” for same-host Chromium navigation."""
    hosts: set[str] = {"10.71.11.69"}
    extra = (os.environ.get("RC_VOICE_ROOM_LAN_HOSTS") or "").strip()
    for part in extra.split(","):
        part = part.strip()
        if part:
            hosts.add(part)
    try:
        import socket

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            hosts.add(s.getsockname()[0])
        finally:
            s.close()
    except Exception:
        pass
    try:
        import socket

        hosts.add(socket.gethostname())
        hosts.add(socket.getfqdn())
    except Exception:
        pass
    return {h for h in hosts if h}


def prefer_loopback_nav_url(url: str) -> str:
    """
    Rewrite same-host LAN voice-room URLs to 127.0.0.1 for the media bot.

    Phones still get the LAN URL from RC VideoConf. Headless Chromium on this
    Mac needs loopback so http is a secure context (getUserMedia + WS join).
    Preflight uses the same rule.
    """
    if not url or "meet.jit.si" in url.lower():
        return url
    if not _is_voice_room_url(url):
        return url
    # Explicit opt-out for rare remote bot hosts
    if os.environ.get("RC_CALL_PREFER_LOOPBACK", "1").strip() in ("0", "false", "no"):
        return url
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        host = parsed.hostname or ""
        if host in ("127.0.0.1", "localhost", "::1"):
            return url
        if host not in _local_lan_hosts():
            return url
        # Preserve port; force host to loopback
        port = parsed.port
        netloc = f"127.0.0.1:{port}" if port else "127.0.0.1"
        return urlunparse(parsed._replace(netloc=netloc))
    except Exception:
        for host in _local_lan_hosts():
            if host and host in url:
                return url.replace(host, "127.0.0.1", 1)
        return url


def _jitsi_url_ready(url: str) -> str:
    """
    Prepare conference join URL for the media bot.

    - Lobby-free voice room: strip Jitsi hash junk; set display name query.
    - Public/self-hosted Jitsi: force skip-prejoin, mic unmuted, stable name.
    """
    if _is_voice_room_url(url) and "meet.jit.si" not in (url or ""):
        # Drop Jitsi config hash (breaks nothing on voice room; path is room id)
        base = url.split("#", 1)[0]
        if "name=" not in base:
            sep = "&" if "?" in base else "?"
            base = f"{base}{sep}name=Grok"
        return base

    # Preserve existing hash config if any; append our overrides.
    extras = [
        "config.prejoinPageEnabled=false",
        "config.prejoinConfig.enabled=false",
        "config.startWithAudioMuted=false",
        "config.startWithVideoMuted=true",
        "config.disableDeepLinking=true",
        "config.requireDisplayName=false",
        "config.disableInviteFunctions=true",
        "userInfo.displayName=%22Grok%22",
        "config.p2p.enabled=true",
    ]
    if "#" in url:
        base, frag = url.split("#", 1)
        # Drop empty pieces; keep prior config then ours (ours win on conflict
        # only if listed later — Jitsi often last-wins for same key).
        frag = frag.rstrip("&")
        return f"{base}#{frag}&{'&'.join(extras)}"
    return f"{url}#{'&'.join(extras)}"


def join_call(token: str, uid: str, call_id: str) -> str:
    """Register grok as joined (stops RC ringing) + return Jitsi URL."""
    d = http_api(
        "POST",
        "/api/v1/video-conference.join",
        token,
        uid,
        {"callId": call_id, "state": {"mic": True, "cam": False}},
    )
    if d.get("success") is False:
        raise RuntimeError(f"join failed: {d}")
    url = d.get("url")
    if not isinstance(url, str) or not url.startswith("http"):
        # Some builds put url only on info after join
        try:
            info = call_info(token, uid, call_id)
            url = info.get("url")
        except Exception:
            url = None
    if not isinstance(url, str) or not url.startswith("http"):
        raise RuntimeError(f"join missing url: {d}")
    # Never leave loopback in the RC-facing URL we log/prepare; rewrite to LAN.
    try:
        from rc_call_media import rewrite_loopback_join_url_to_lan

        url = rewrite_loopback_join_url_to_lan(url)
    except Exception:
        pass
    return _jitsi_url_ready(url)


def call_info(token: str, uid: str, call_id: str) -> dict:
    return http_api(
        "GET",
        f"/api/v1/video-conference.info?callId={urllib.parse.quote(call_id)}",
        token,
        uid,
    )


def leave_call(token: str, uid: str, call_id: str) -> None:
    """Best-effort leave so RC does not leave ghost 'status=1' conferences."""
    try:
        http_api(
            "POST",
            "/api/v1/video-conference.leave",
            token,
            uid,
            {"callId": call_id},
        )
        log("left RC call via API")
    except Exception as e:
        log(f"leave_call: {e}")


def post_call_status(token: str, uid: str, room_id: str, text: str) -> None:
    """Chat status so principal sees connect progress while media boots."""
    try:
        http_api(
            "POST",
            "/api/v1/chat.postMessage",
            token,
            uid,
            {"roomId": room_id, "text": text},
        )
    except Exception as e:
        log(f"status post failed: {e}")


def tts_to_wav(text: str, out_wav: Path) -> Path:
    """macOS say → aiff → wav (16k mono for whisper-friendly playback)."""
    CALL_MEDIA.mkdir(parents=True, exist_ok=True)
    # Unique intermediate path so concurrent bots cannot clobber each other
    aiff = out_wav.with_name(f"{out_wav.stem}-{os.getpid()}-{time.time_ns()}.aiff")
    # Strip markdown-ish noise for speech
    clean = re.sub(r"[#*_`>~\[\]()]", " ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean:
        clean = "Okay."
    # Cap length for call turns
    if len(clean) > 800:
        clean = clean[:800].rsplit(" ", 1)[0] + "."
    # Prefer configured voice; fall back if premium/missing (e.g. "Ava" → system default).
    voices = [SAY_VOICE, "Samantha", "Alex", ""]
    last_err: Exception | None = None
    for voice in voices:
        cmd = ["say", "-o", str(aiff), clean]
        if voice:
            cmd = ["say", "-v", voice, "-o", str(aiff), clean]
        try:
            subprocess.run(cmd, check=True, timeout=120, capture_output=True)
            last_err = None
            break
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            last_err = e
            continue
    if last_err is not None:
        raise RuntimeError(f"macOS say TTS failed for voices {voices}: {last_err}") from last_err
    if not aiff.is_file() or aiff.stat().st_size < 32:
        raise RuntimeError(f"macOS say produced empty aiff: {aiff}")
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(aiff),
                "-ac",
                "1",
                "-ar",
                "48000",
                str(out_wav),
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
    except subprocess.CalledProcessError as e:
        err = (e.stderr or b"")[-300:]
        raise RuntimeError(f"ffmpeg aiff→wav failed: {err!r}") from e
    try:
        aiff.unlink(missing_ok=True)
    except OSError:
        pass
    return out_wav


def transcribe_wav(path: Path) -> str:
    out_dir = path.parent / f"stt-{path.stem}"
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        WHISPER_BIN,
        str(path),
        "--model",
        WHISPER_MODEL,
        "--language",
        WHISPER_LANGUAGE,
        "--task",
        "transcribe",
        "--output_format",
        "txt",
        "--output_dir",
        str(out_dir),
        "--verbose",
        "False",
        "--fp16",
        "False",
    ]
    env = os.environ.copy()
    env["PATH"] = (
        f"{Path.home() / '.local' / 'bin'}:"
        f"/Library/Frameworks/Python.framework/Versions/3.13/bin:"
        f"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:{env.get('PATH', '')}"
    )
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=180, env=env
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "")[-400:])
    preferred = out_dir / f"{path.stem}.txt"
    if preferred.is_file():
        t = preferred.read_text(encoding="utf-8", errors="replace").strip()
        if t:
            return t
    for c in out_dir.glob("*.txt"):
        t = c.read_text(encoding="utf-8", errors="replace").strip()
        if t:
            return t
    return ""


def wake_voice_turn(
    user_text: str,
    *,
    room_id: str,
    project_cwd: str,
    resume_session_id: str | None,
) -> tuple[str, str | None]:
    """One conversational turn via headless Grok. Returns (reply, session_id)."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    reply_path = LOG_DIR / f"call-reply-{ts}.txt"
    prompt_path = LOG_DIR / f"call-prompt-{ts}.txt"
    log_file = LOG_DIR / f"call-wake-{ts}.log"
    reply_path.write_text("", encoding="utf-8")
    prompt = (
        "You are Grok on a live phone call with the principal via Rocket.Chat.\n"
        "Speak naturally. Keep answers short (1–4 spoken sentences) unless asked for detail.\n"
        "No markdown, no bullet lists, no code fences, no stage directions.\n"
        "Do not mention being an AI unless asked.\n"
        f"Write ONLY the spoken reply to this file: {reply_path}\n\n"
        f"Principal said:\n{user_text.strip()}\n"
    )
    prompt_path.write_text(prompt, encoding="utf-8")
    # Same approval policy as the text operator (IMP-01). Calls are DMs; still
    # honors RC_WAKE_APPROVAL_MODE (restricted default / admin opt-in).
    call_approval = resolve_approval_mode(room_type="d", room_name="dm:principal")
    cmd = build_wake_argv(
        prompt_path,
        grok_bin=GROK_BIN,
        cwd=project_cwd,
        max_turns=os.environ.get("RC_CALL_MAX_TURNS", "8"),
        resume_session_id=resume_session_id,
        output_format="json",
        approval_mode=call_approval,
    )
    env = os.environ.copy()
    env["PATH"] = (
        f"{Path.home() / '.local' / 'bin'}:{Path.home() / '.grok' / 'bin'}:"
        f"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:{env.get('PATH', '')}"
    )
    env["HOME"] = str(Path.home())
    with log_file.open("w", encoding="utf-8") as out:
        out.write(f"cmd: {cmd}\n\n")
        out.flush()
        proc = subprocess.Popen(
            cmd, stdout=out, stderr=subprocess.STDOUT, env=env, cwd=project_cwd
        )
        try:
            rc = proc.wait(timeout=180)
        except subprocess.TimeoutExpired:
            proc.kill()
            rc = 124
    text = log_file.read_text(encoding="utf-8", errors="replace")
    sid = extract_session_id_from_output(text) or resume_session_id
    body = reply_path.read_text(encoding="utf-8", errors="replace").strip()
    if not body:
        body = (
            "Sorry, I didn't catch a reply on my side. Could you say that again?"
            if rc != 0
            else "Sorry, I blanked for a second. What was that?"
        )
    return body, sid


# JS injected before Jitsi loads — virtual mic + remote capture helpers
INIT_SCRIPT = r"""
(() => {
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  const ctx = new AudioCtx({ sampleRate: 48000 });
  const dest = ctx.createMediaStreamDestination();
  // Keep a very quiet carrier so the MediaStreamTrack stays live/unmuted
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  gain.gain.value = 0.0008;
  osc.frequency.value = 20;
  osc.connect(gain);
  gain.connect(dest);
  osc.start();
  // Clone tracks on each GUM so Jitsi cannot stop our master track
  const micStream = () => {
    const s = new MediaStream();
    dest.stream.getAudioTracks().forEach((t) => {
      try { t.enabled = true; } catch (e) {}
      s.addTrack(t.clone ? t.clone() : t);
    });
    return s;
  };
  window.__grokAudio = { ctx, dest, gain, micStream };
  window.__grokPlayPcmWavBase64 = async (b64) => {
    try {
      if (ctx.state === 'suspended') await ctx.resume();
      const bin = atob(b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const audioBuf = await ctx.decodeAudioData(bytes.buffer.slice(0));
      const src = ctx.createBufferSource();
      src.buffer = audioBuf;
      // Slight boost into conference mix
      const g = ctx.createGain();
      g.gain.value = 1.35;
      src.connect(g);
      g.connect(dest);
      // local monitor when headed
      try { g.connect(ctx.destination); } catch (e) {}
      src.start();
      return audioBuf.duration;
    } catch (e) {
      console.error('grokPlay', e);
      return 0;
    }
  };
  // Capture remote audio: RTCPeerConnection tracks + <audio> elements
  window.__grokRemoteMix = ctx.createMediaStreamDestination();
  window.__grokRemoteTrackCount = 0;
  const addRemoteTrack = (track) => {
    try {
      if (!track || track.kind !== 'audio') return;
      if (track.__grokAdded) return;
      track.__grokAdded = true;
      try { track.enabled = true; } catch (e) {}
      const ms = new MediaStream([track]);
      const src = ctx.createMediaStreamSource(ms);
      src.connect(window.__grokRemoteMix);
      window.__grokRemoteTrackCount += 1;
      console.log('grok remote track +1 total=' + window.__grokRemoteTrackCount);
    } catch (e) { console.error('addRemoteTrack', e); }
  };
  const OrigPC = window.RTCPeerConnection;
  window.RTCPeerConnection = function(...args) {
    const pc = new OrigPC(...args);
    pc.addEventListener('track', (ev) => {
      if (ev.track) addRemoteTrack(ev.track);
      if (ev.streams) {
        ev.streams.forEach((s) => s.getAudioTracks().forEach(addRemoteTrack));
      }
    });
    const origAddTrack = pc.addTrack.bind(pc);
    pc.addTrack = function(...a) { return origAddTrack(...a); };
    return pc;
  };
  window.RTCPeerConnection.prototype = OrigPC.prototype;
  Object.keys(OrigPC).forEach((k) => {
    try { window.RTCPeerConnection[k] = OrigPC[k]; } catch (e) {}
  });
  window.__grokStartRemoteCapture = () => {
    const hook = (el) => {
      try {
        if (el.__grokHooked) return;
        el.__grokHooked = true;
        el.muted = false;
        el.volume = 1.0;
        if (el.srcObject) {
          el.srcObject.getAudioTracks().forEach(addRemoteTrack);
        }
        try {
          const src = ctx.createMediaElementSource(el);
          src.connect(window.__grokRemoteMix);
          src.connect(ctx.destination);
        } catch (e) {}
      } catch (e) {}
    };
    document.querySelectorAll('audio, video').forEach(hook);
    const mo = new MutationObserver(() => {
      document.querySelectorAll('audio, video').forEach(hook);
    });
    mo.observe(document.documentElement, { childList: true, subtree: true });
    return true;
  };
  window.__grokDiag = () => ({
    remoteTracks: window.__grokRemoteTrackCount || 0,
    ctx: ctx.state,
    micTracks: dest.stream.getAudioTracks().map((t) => ({
      id: t.id, enabled: t.enabled, muted: t.muted, ready: t.readyState,
    })),
  });
  window.__grokForceUnmute = () => {
    try {
      if (window.APP && APP.conference) {
        if (APP.conference.isLocalAudioMuted && APP.conference.isLocalAudioMuted()) {
          APP.conference.muteAudio(false);
        }
        if (APP.conference.setLocalAudio && APP.conference.muteAudio) {
          APP.conference.muteAudio(false);
        }
      }
    } catch (e) {}
    // UI fallbacks
    const sels = [
      '[aria-label="Unmute microphone"]',
      '[aria-label="Unmute"]',
      'button[aria-label*="Unmute"]',
    ];
    for (const s of sels) {
      const el = document.querySelector(s);
      if (el) { try { el.click(); } catch (e) {} }
    }
  };
  window.__grokRecordSeconds = async (seconds) => {
    try {
      if (ctx.state === 'suspended') await ctx.resume();
      window.__grokStartRemoteCapture();
      const stream = window.__grokRemoteMix.stream;
      if (!stream || stream.getAudioTracks().length === 0) {
        return null;
      }
      let mime = 'audio/webm';
      if (!MediaRecorder.isTypeSupported(mime)) mime = 'audio/webm;codecs=opus';
      if (!MediaRecorder.isTypeSupported(mime)) mime = '';
      const rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      const chunks = [];
      rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
      const done = new Promise((resolve) => { rec.onstop = () => resolve(chunks); });
      rec.start(100);
      await new Promise((r) => setTimeout(r, Math.floor(seconds * 1000)));
      rec.stop();
      const parts = await done;
      if (!parts.length) return null;
      const blob = new Blob(parts, { type: mime || 'audio/webm' });
      if (blob.size < 64) return null;
      const ab = await blob.arrayBuffer();
      const bytes = new Uint8Array(ab);
      let s = '';
      for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
      return btoa(s);
    } catch (e) {
      console.error('record', e);
      return null;
    }
  };
  // Override getUserMedia so Jitsi always gets our virtual mic
  const gum = async (constraints) => {
    const c = constraints || { audio: true };
    const wantAudio = c.audio !== false && c.audio !== null;
    const wantVideo = !!c.video;
    if (ctx.state === 'suspended') await ctx.resume();
    if (wantAudio && !wantVideo) return micStream();
    if (wantAudio && wantVideo) {
      try {
        const canvas = document.createElement('canvas');
        canvas.width = 320; canvas.height = 240;
        const g = canvas.getContext('2d');
        g.fillStyle = '#111'; g.fillRect(0,0,320,240);
        g.fillStyle = '#4f8'; g.font = '20px sans-serif';
        g.fillText('Grok', 120, 130);
        const vstream = canvas.captureStream(5);
        const out = new MediaStream([
          ...micStream().getAudioTracks(),
          ...vstream.getVideoTracks(),
        ]);
        return out;
      } catch (e) {
        return micStream();
      }
    }
    return micStream();
  };
  if (navigator.mediaDevices) {
    navigator.mediaDevices.getUserMedia = gum;
    // Advertise a fake mic so device pickers succeed
    const origEnum = navigator.mediaDevices.enumerateDevices.bind(navigator.mediaDevices);
    navigator.mediaDevices.enumerateDevices = async () => {
      try {
        const real = await origEnum();
        if (real && real.some((d) => d.kind === 'audioinput')) return real;
      } catch (e) {}
      return [{
        deviceId: 'grok-virtual-mic',
        groupId: 'grok',
        kind: 'audioinput',
        label: 'Grok Virtual Mic',
        toJSON() { return this; },
      }];
    };
  }
  // Legacy
  navigator.getUserMedia = (c, ok, err) => {
    gum(c).then(ok).catch(err);
  };
})();
"""


def play_wav_in_page(page, wav_path: Path) -> float:
    raw = wav_path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    dur = page.evaluate(
        """async (b64) => {
          if (!window.__grokPlayPcmWavBase64) return 0;
          return await window.__grokPlayPcmWavBase64(b64);
        }""",
        b64,
    )
    try:
        return float(dur or 0)
    except (TypeError, ValueError):
        return 0.0


def webm_b64_to_wav(b64: str, out_wav: Path) -> Path | None:
    if not b64:
        return None
    CALL_MEDIA.mkdir(parents=True, exist_ok=True)
    webm = out_wav.with_suffix(".webm")
    webm.write_bytes(base64.b64decode(b64))
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(webm),
                "-ac",
                "1",
                "-ar",
                "16000",
                str(out_wav),
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
    except subprocess.CalledProcessError as e:
        log(f"ffmpeg webm→wav failed: {e.stderr[-200:] if e.stderr else e}")
        return None
    return out_wav if out_wav.is_file() else None


def wav_rms(path: Path) -> float:
    """Rough RMS via ffmpeg volumedetect."""
    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-i",
                str(path),
                "-af",
                "volumedetect",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        m = re.search(r"mean_volume:\s*([-\d.]+)", proc.stderr or "")
        if not m:
            return 0.0
        # mean_volume is dB; map roughly to 0–1
        db = float(m.group(1))
        # -60dB silence-ish, -10dB loud
        if db < -50:
            return 0.0
        return min(1.0, max(0.0, (db + 50) / 40))
    except Exception:
        return 0.0


def _call_lock_path() -> Path:
    return LOG_DIR / "call-bot.lock"


def _clear_call_lock() -> None:
    lock = _call_lock_path()
    try:
        meta = json.loads(lock.read_text(encoding="utf-8")) if lock.is_file() else {}
        # Only clear if we own it (or lock is empty/stale)
        if meta.get("pid") in (None, os.getpid()) or not meta:
            lock.unlink(missing_ok=True)
        else:
            # Stale if owner dead
            pid = meta.get("pid")
            if isinstance(pid, int):
                try:
                    os.kill(pid, 0)
                except OSError:
                    lock.unlink(missing_ok=True)
    except (OSError, json.JSONDecodeError):
        try:
            lock.unlink(missing_ok=True)
        except OSError:
            pass


def acquire_call_bot_lock(call_id: str, room_id: str) -> bool:
    """
    Single-instance guard inside the bot (not only the operator spawner).

    Prevents double-spawn races (operator + manual criterion, or dual wake).
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    lock = _call_lock_path()
    if lock.is_file():
        try:
            meta = json.loads(lock.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
        pid = meta.get("pid")
        age = time.time() - lock.stat().st_mtime
        alive = False
        if isinstance(pid, int) and pid > 0:
            try:
                os.kill(pid, 0)
                alive = True
            except OSError:
                alive = False
        if alive and age < MAX_CALL_S + 60 and pid != os.getpid():
            log(
                f"call-bot lock held by pid={pid} callId={meta.get('call_id')} "
                f"age={age:.0f}s — exit to avoid dual media peers"
            )
            return False
        try:
            lock.unlink(missing_ok=True)
        except OSError:
            pass
    try:
        lock.write_text(
            json.dumps(
                {
                    "call_id": call_id,
                    "room_id": room_id,
                    "pid": os.getpid(),
                    "started_at": datetime.now(timezone.utc).isoformat(),
                }
            ),
            encoding="utf-8",
        )
        return True
    except OSError as e:
        log(f"call lock write failed: {e}")
        return False


def _click_join_buttons(page) -> None:
    for sel in (
        'button:has-text("Join meeting")',
        'button:has-text("Join now")',
        'button:has-text("Join")',
        'div[aria-label="Join meeting"]',
        'button[aria-label="Join meeting"]',
        'button[aria-label="Join"]',
        '[data-testid="prejoin.joinMeeting"]',
        "#modal-dialog button",
    ):
        try:
            btn = page.locator(sel)
            if btn.count() and btn.first.is_visible(timeout=400):
                btn.first.click(timeout=1500)
                page.wait_for_timeout(800)
                log(f"clicked join control: {sel}")
        except Exception:
            continue


def run_call(call_id: str, room_id: str, room_name: str = "") -> int:
    log(f"call bot start callId={call_id} room={room_id}")
    if not acquire_call_bot_lock(call_id, room_id):
        log("FATAL: another call bot already holds the media lock")
        return 2
    token, uid = login_operator()
    # Answer on RC first — this is what should stop the phone ringing.
    join_url = join_call(token, uid, call_id)
    log(f"joined RC call url={join_url[:160]}...")
    try:
        info = call_info(token, uid, call_id)
        users = info.get("users") or []
        log(
            f"post-join status={info.get('status')} ringing={info.get('ringing')} "
            f"users={[u.get('username') for u in users if isinstance(u, dict)]}"
        )
    except Exception as e:
        log(f"post-join info: {e}")
    post_call_status(
        token,
        uid,
        room_id,
        "Joined the call on my side — connecting audio now. "
        "You should leave the ring screen; wait for: “Hello, Grok speaking.”",
    )

    st = load_state(STATE_PATH)
    sid = get_room_session_id(st, room_id)
    cwd = get_room_cwd(st, room_id) or str(AGENCY)
    if not Path(cwd).is_dir():
        cwd = str(AGENCY)

    CALL_MEDIA.mkdir(parents=True, exist_ok=True)
    try:
        return _run_jitsi_loop(
            join_url=join_url,
            token=token,
            uid=uid,
            call_id=call_id,
            room_id=room_id,
            cwd=cwd,
            sid=sid,
        )
    finally:
        leave_call(token, uid, call_id)
        _clear_call_lock()


def _run_jitsi_loop(
    *,
    join_url: str,
    token: str,
    uid: str,
    call_id: str,
    room_id: str,
    cwd: str,
    sid: str | None,
) -> int:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--autoplay-policy=no-user-gesture-required",
                "--use-fake-ui-for-media-stream",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-web-security",
                "--allow-running-insecure-content",
                "--enable-features=NetworkService,NetworkServiceInProcess",
            ],
        )
        context = browser.new_context(
            permissions=["microphone", "camera"],
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True,
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        # Grant media for join origin (Jitsi or LAN voice room)
        try:
            from urllib.parse import urlparse

            origin = f"{urlparse(join_url).scheme}://{urlparse(join_url).netloc}"
            context.grant_permissions(["microphone", "camera"], origin=origin)
        except Exception:
            pass
        try:
            context.grant_permissions(
                ["microphone", "camera"], origin="https://meet.jit.si"
            )
        except Exception:
            pass
        page = context.new_page()
        page.add_init_script(INIT_SCRIPT)
        voice_room = _is_voice_room_url(join_url)
        # Navigate via loopback on this Mac so Chromium has a secure context
        # (LAN IP http blocks getUserMedia → no WS join → log-only TTS).
        nav_url = prefer_loopback_nav_url(join_url) if voice_room else join_url
        log(
            f"opening conference voice_room={voice_room} "
            f"url={join_url[:100]} nav={nav_url[:100]}"
        )
        # Permissions for actual nav origin (often 127.0.0.1 after rewrite)
        try:
            from urllib.parse import urlparse as _up

            nav_origin = f"{_up(nav_url).scheme}://{_up(nav_url).netloc}"
            context.grant_permissions(["microphone", "camera"], origin=nav_origin)
        except Exception:
            pass
        page.goto(nav_url, wait_until="domcontentloaded", timeout=120_000)
        # Jitsi prejoin only; voice room auto-joins after GUM
        if not voice_room:
            for _ in range(6):
                _click_join_buttons(page)
                page.wait_for_timeout(700)
            page.wait_for_timeout(2500)
        else:
            # Wait until voice room has local mic + signaling identity (real media join)
            media_deadline = time.time() + 20
            last_diag: dict = {}
            while time.time() < media_deadline:
                try:
                    last_diag = page.evaluate(
                        """() => {
                          if (!window.__voiceRoom) return { voiceRoom: false };
                          return {
                            voiceRoom: true,
                            remote: window.__voiceRoom.remoteTrackCount || 0,
                            local: !!window.__voiceRoom.localReady,
                            selfId: window.__voiceRoom.selfId || null,
                            peers: window.__voiceRoom.peers
                              ? window.__voiceRoom.peers() : [],
                            status: (document.getElementById('status') || {}).textContent || '',
                          };
                        }"""
                    )
                except Exception as e:
                    last_diag = {"err": str(e)}
                if (
                    isinstance(last_diag, dict)
                    and last_diag.get("local")
                    and last_diag.get("selfId")
                ):
                    log(f"voice room media joined diag={last_diag}")
                    break
                page.wait_for_timeout(400)
            else:
                log(f"FATAL: voice room never media-joined diag={last_diag}")
                post_call_status(
                    token,
                    uid,
                    room_id,
                    "Call media failed to join the voice room (mic/signaling). "
                    "Trying again may help; operator will check logs.",
                )
                browser.close()
                return 1
        try:
            page.evaluate("() => { try { window.__grokForceUnmute(); } catch(e){} }")
        except Exception:
            pass
        page.evaluate("() => { try { window.__grokStartRemoteCapture(); } catch(e){} }")
        try:
            diag = page.evaluate(
                """() => {
                  if (window.__voiceRoom) {
                    return {
                      voiceRoom: true,
                      remote: window.__voiceRoom.remoteTrackCount,
                      local: window.__voiceRoom.localReady,
                      selfId: window.__voiceRoom.selfId || null,
                      peers: window.__voiceRoom.peers ? window.__voiceRoom.peers() : [],
                    };
                  }
                  return window.__grokDiag ? window.__grokDiag() : {};
                }"""
            )
            log(f"conference diag after join: {diag}")
        except Exception as e:
            log(f"diag failed: {e}")

        # Wait briefly for peer (principal) — greeting still plays either way
        peer_deadline = time.time() + 20
        while time.time() < peer_deadline:
            try:
                info = call_info(token, uid, call_id)
                if info.get("endedAt") or info.get("status") == 4:
                    log("call ended before greeting")
                    browser.close()
                    return 0
                users = [
                    u.get("username")
                    for u in (info.get("users") or [])
                    if isinstance(u, dict)
                ]
                if any(u and u != OPERATOR for u in users):
                    log(f"peer present: {users}")
                    break
            except Exception:
                pass
            # Voice room: peer may be present on media plane before RC user list updates
            if voice_room:
                try:
                    peers = page.evaluate(
                        "() => (window.__voiceRoom && window.__voiceRoom.peers)"
                        " ? window.__voiceRoom.peers().length : 0"
                    )
                    if int(peers or 0) >= 1:
                        log(f"voice room media peer(s)={peers}")
                        break
                except Exception:
                    pass
            page.wait_for_timeout(500)

        try:
            page.evaluate("() => { try { window.__grokForceUnmute(); } catch(e){} }")
        except Exception:
            pass

        # Greeting only after media join (voice room) — inject into virtual mic
        greet_wav = CALL_MEDIA / f"greet-{os.getpid()}-{time.time_ns()}.wav"
        tts_to_wav(GREETING, greet_wav)
        dur = play_wav_in_page(page, greet_wav)
        if dur < 0.3:
            page.wait_for_timeout(500)
            dur = play_wav_in_page(page, greet_wav)
        # Re-check media still live after TTS (not log-only theater)
        if voice_room:
            try:
                post = page.evaluate(
                    """() => ({
                      local: !!(window.__voiceRoom && window.__voiceRoom.localReady),
                      selfId: window.__voiceRoom && window.__voiceRoom.selfId,
                    })"""
                )
                if not (post or {}).get("local") or not (post or {}).get("selfId"):
                    log(f"FATAL: lost media join before/after greeting post={post}")
                    browser.close()
                    return 1
            except Exception as e:
                log(f"FATAL: post-greeting media check failed: {e}")
                browser.close()
                return 1
        log(f"played greeting dur={dur:.1f}s media_ok=1")
        page.wait_for_timeout(int(max(dur, 1.5) * 1000) + 400)
        post_call_status(
            token,
            uid,
            room_id,
            "Audio up — I just said the greeting. Speak after the beep-gap; "
            "I will answer out loud.",
        )

        deadline = time.time() + MAX_CALL_S
        turn = 0
        no_remote_streak = 0
        # Exit if phone never joins media — free lock for next Call.
        try:
            from rc_call_media import call_no_peer_timeout_s

            no_peer_limit_s = float(call_no_peer_timeout_s())
        except Exception:
            no_peer_limit_s = 90.0
        no_peer_deadline = time.time() + no_peer_limit_s
        saw_remote = False
        while time.time() < deadline:
            # Check call still open
            try:
                info = call_info(token, uid, call_id)
                status = info.get("status")
                # status 4 = ended
                if status == 4 or info.get("endedAt"):
                    log(f"call ended by RC status={status}")
                    break
            except Exception as e:
                log(f"call info poll: {e}")

            try:
                diag = page.evaluate(
                    "() => (window.__grokDiag ? window.__grokDiag() : {})"
                )
                remote_n = int((diag or {}).get("remoteTracks", 0) or 0)
                if voice_room:
                    try:
                        remote_n = max(
                            remote_n,
                            int(
                                page.evaluate(
                                    "() => (window.__voiceRoom && "
                                    "window.__voiceRoom.remoteTrackCount) || 0"
                                )
                                or 0
                            ),
                        )
                    except Exception:
                        pass
                if remote_n == 0:
                    no_remote_streak += 1
                    if no_remote_streak in (5, 20, 50):
                        log(f"still no remote audio tracks diag={diag}")
                        page.evaluate(
                            "() => { try { window.__grokStartRemoteCapture(); "
                            "window.__grokForceUnmute(); } catch(e){} }"
                        )
                    if (
                        not saw_remote
                        and time.time() >= no_peer_deadline
                    ):
                        log(
                            f"no remote peer within {no_peer_limit_s:.0f}s — "
                            "ending media worker to free call lock"
                        )
                        post_call_status(
                            token,
                            uid,
                            room_id,
                            "Call media timed out waiting for your phone to join "
                            "the voice room (same Wi‑Fi as the Mac). "
                            "Cancel and Call again.",
                        )
                        break
                else:
                    saw_remote = True
                    no_remote_streak = 0
            except Exception:
                pass

            # Collect speech until silence after min speech
            speech_parts: list[Path] = []
            speech_started = False
            silent_for = 0.0
            collect_start = time.time()
            max_utterance = 25.0
            while time.time() - collect_start < max_utterance:
                b64 = page.evaluate(
                    """async (sec) => {
                      if (!window.__grokRecordSeconds) return null;
                      return await window.__grokRecordSeconds(sec);
                    }""",
                    LISTEN_CHUNK_S,
                )
                if not b64:
                    silent_for += LISTEN_CHUNK_S
                    if speech_started and silent_for >= SILENCE_END_S:
                        break
                    continue
                chunk_wav = CALL_MEDIA / f"chunk-{int(time.time()*1000)}.wav"
                path = webm_b64_to_wav(b64, chunk_wav)
                if not path:
                    silent_for += LISTEN_CHUNK_S
                    continue
                level = wav_rms(path)
                if level >= RMS_SPEECH:
                    speech_started = True
                    silent_for = 0.0
                    speech_parts.append(path)
                else:
                    silent_for += LISTEN_CHUNK_S
                    if speech_started and silent_for >= SILENCE_END_S:
                        break
                if time.time() >= deadline:
                    break

            if not speech_parts:
                continue

            turn += 1
            list_file = CALL_MEDIA / f"concat-{turn}.txt"
            utter_wav = CALL_MEDIA / f"utter-{turn}.wav"
            with list_file.open("w", encoding="utf-8") as f:
                for pth in speech_parts:
                    # ffmpeg concat demuxer needs escaped single quotes
                    safe = str(pth).replace("'", r"'\''")
                    f.write(f"file '{safe}'\n")
            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        str(list_file),
                        "-ac",
                        "1",
                        "-ar",
                        "16000",
                        str(utter_wav),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
            except subprocess.CalledProcessError as e:
                log(f"concat failed: {e}")
                continue

            try:
                pr = subprocess.run(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=noprint_wrappers=1:nokey=1",
                        str(utter_wav),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                dur_u = float((pr.stdout or "0").strip() or 0)
            except Exception:
                dur_u = 0.0
            if dur_u < MIN_SPEECH_S:
                log(f"skip short utterance {dur_u:.2f}s")
                continue

            try:
                transcript = transcribe_wav(utter_wav)
            except Exception as e:
                log(f"stt failed: {e}")
                err_wav = CALL_MEDIA / f"err-{turn}.wav"
                tts_to_wav("Sorry, I couldn't hear that clearly.", err_wav)
                play_wav_in_page(page, err_wav)
                continue

            transcript = (transcript or "").strip()
            log(f"turn {turn} transcript={transcript[:160]!r}")
            if not transcript or transcript.lower() in (
                "you",
                "thank you.",
                "thanks.",
                ".",
            ):
                continue

            low = transcript.lower().strip()
            if any(
                p in low
                for p in (
                    "goodbye",
                    "good bye",
                    "hang up",
                    "end call",
                    "stop call",
                )
            ):
                bye_wav = CALL_MEDIA / f"bye-{turn}.wav"
                tts_to_wav("Goodbye.", bye_wav)
                d = play_wav_in_page(page, bye_wav)
                page.wait_for_timeout(int(max(d, 1) * 1000) + 300)
                break

            reply, sid = wake_voice_turn(
                transcript,
                room_id=room_id,
                project_cwd=cwd,
                resume_session_id=sid,
            )
            log(f"turn {turn} reply={reply[:160]!r} session={sid}")
            st = load_state(STATE_PATH)
            if sid:
                set_room_session_id(st, room_id, sid)
            set_room_cwd(st, room_id, cwd)
            save_state(st, STATE_PATH)

            reply_wav = CALL_MEDIA / f"reply-{turn}.wav"
            tts_to_wav(reply, reply_wav)
            d = play_wav_in_page(page, reply_wav)
            page.wait_for_timeout(int(max(d, 0.5) * 1000) + 350)

        browser.close()
    log("call bot finished")
    return 0


def main() -> int:
    apply_call_config()
    ap = argparse.ArgumentParser(description="RC Call media bot for grok")
    ap.add_argument("--call-id", required=True)
    ap.add_argument("--room-id", required=True)
    ap.add_argument("--room-name", default="")
    args = ap.parse_args()
    try:
        return run_call(args.call_id, args.room_id, room_name=args.room_name)
    except Exception as e:
        log(f"FATAL: {e}")
        _clear_call_lock()
        return 1


if __name__ == "__main__":
    sys.exit(main())
