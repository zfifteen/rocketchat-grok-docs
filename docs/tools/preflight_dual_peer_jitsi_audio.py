#!/usr/bin/env python3
"""
Pre-principal dual-peer audio probe for the live RC Call media path.

Starts a VideoConf on principal↔grok DM via RC API, opens two Chromium peers
on the join URL RC returns, publishes audio from the Grok peer, measures remote
RMS at the principal peer.

Works with:
  - Lobby-free RC voice room (http://host:port/Agency{callId})
  - Legacy Jitsi URLs (usually FAIL on public meet.jit.si lobby)

Exit codes:
  0 = PASS (remote_rms >= threshold)
  2 = FAIL media
  3 = setup failure
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import struct
import subprocess
import sys
import time
import urllib.request
import wave
from pathlib import Path

SECRETS = Path.home() / ".grok" / "agency" / "secrets" / "rocketchat.env"
BASE = os.environ.get("RC_BASE", "http://127.0.0.1:3000")
OUT_DIR = Path.home() / "logs" / "rocketchat-dm-wake" / "preflight"
REPORT = OUT_DIR / "dual-peer-report.json"

INIT_GROK_TONE = r"""
(() => {
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  const ctx = new AudioCtx({ sampleRate: 48000 });
  const dest = ctx.createMediaStreamDestination();
  const tone = ctx.createOscillator();
  const g = ctx.createGain();
  g.gain.value = 0.4;
  tone.frequency.value = 880;
  tone.connect(g); g.connect(dest); tone.start();
  // quiet carrier keep-alive
  const o2 = ctx.createOscillator();
  const g2 = ctx.createGain();
  g2.gain.value = 0.0005;
  o2.frequency.value = 20;
  o2.connect(g2); g2.connect(dest); o2.start();
  const micStream = () => {
    const s = new MediaStream();
    dest.stream.getAudioTracks().forEach((t) => {
      try { t.enabled = true; } catch (e) {}
      s.addTrack(t.clone ? t.clone() : t);
    });
    return s;
  };
  window.__probeLocalInfo = () => ({
    ctx: ctx.state,
    tracks: dest.stream.getAudioTracks().map((t) => ({
      id: t.id, enabled: t.enabled, muted: t.muted, ready: t.readyState, label: t.label,
    })),
  });
  const gum = async () => {
    if (ctx.state === 'suspended') await ctx.resume();
    return micStream();
  };
  if (navigator.mediaDevices) {
    navigator.mediaDevices.getUserMedia = gum;
    navigator.mediaDevices.enumerateDevices = async () => ([{
      deviceId: 'probe-mic', kind: 'audioinput', label: 'Probe Mic', groupId: 'probe',
      toJSON() { return this; },
    }]);
  }
  navigator.getUserMedia = (c, ok, err) => gum().then(ok).catch(err);
})();
"""

INIT_PRINCIPAL = r"""
(() => {
  // Prefer page-provided hooks (voice room); fall back to RTCPeerConnection hook.
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  const ctx = new AudioCtx({ sampleRate: 48000 });
  window.__remoteMix = ctx.createMediaStreamDestination();
  window.__remoteCount = 0;
  const add = (track) => {
    try {
      if (!track || track.kind !== 'audio' || track.__p) return;
      track.__p = true;
      try { track.enabled = true; } catch (e) {}
      const ms = new MediaStream([track]);
      const src = ctx.createMediaStreamSource(ms);
      src.connect(window.__remoteMix);
      window.__remoteCount += 1;
    } catch (e) {}
  };
  const OrigPC = window.RTCPeerConnection;
  window.RTCPeerConnection = function (...args) {
    const pc = new OrigPC(...args);
    pc.addEventListener('track', (ev) => {
      if (ev.track) add(ev.track);
      (ev.streams || []).forEach((s) => s.getAudioTracks().forEach(add));
    });
    return pc;
  };
  window.RTCPeerConnection.prototype = OrigPC.prototype;
  const baseDiag = () => ({
    remoteCount: window.__remoteCount,
    ctx: ctx.state,
    voiceRoom: !!(window.__voiceRoom),
    vrRemote: window.__voiceRoom ? window.__voiceRoom.remoteTrackCount : null,
  });
  window.__probeDiag = () => {
    if (window.__voiceRoom) {
      return {
        remoteCount: window.__voiceRoom.remoteTrackCount || 0,
        localReady: window.__voiceRoom.localReady,
        peers: window.__voiceRoom.peers ? window.__voiceRoom.peers() : [],
        room: window.__voiceRoom.room,
        via: 'voiceRoom',
      };
    }
    return Object.assign({ via: 'hook' }, baseDiag());
  };
  window.__probeRecord = async (sec) => {
    if (window.__voiceRoom && typeof window.__probeRecord === 'function') {
      // room page may redefine; call after re-bind below
    }
    if (ctx.state === 'suspended') await ctx.resume();
    // Prefer remoteMix from voice room audio element if present
    let stream = window.__remoteMix.stream;
    const ra = document.getElementById('remoteAudio');
    if (ra && ra.srcObject) {
      stream = ra.srcObject;
    }
    if (window.__voiceRoom && window.__voiceRoom.remoteTrackCount) {
      // wait — room page also exposes __probeRecord later; use mix
    }
    if (!stream.getAudioTracks().length) {
      // pull from voice room remoteMix if audio element tracks
      if (ra && ra.srcObject) stream = ra.srcObject;
    }
    if (!stream.getAudioTracks().length) {
      return { ok: false, reason: 'no_remote_tracks', count: 0, diag: window.__probeDiag() };
    }
    let mime = 'audio/webm';
    if (!MediaRecorder.isTypeSupported(mime)) mime = '';
    const rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
    const chunks = [];
    rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
    const done = new Promise((r) => { rec.onstop = () => r(chunks); });
    rec.start(100);
    await new Promise((r) => setTimeout(r, Math.floor(sec * 1000)));
    rec.stop();
    const parts = await done;
    if (!parts.length) return { ok: false, reason: 'empty_chunks', count: stream.getAudioTracks().length };
    const blob = new Blob(parts, { type: mime || 'audio/webm' });
    const ab = await blob.arrayBuffer();
    const bytes = new Uint8Array(ab);
    let s = '';
    for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return { ok: true, b64: btoa(s), bytes: bytes.length, count: stream.getAudioTracks().length };
  };
})();
"""


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def http_json(
    method: str,
    path: str,
    token: str | None = None,
    uid: str | None = None,
    body: dict | None = None,
) -> dict:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token and uid:
        headers["X-Auth-Token"] = token
        headers["X-User-Id"] = uid
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, headers=headers, method=method
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode())


def login(user: str, password: str) -> tuple[str, str]:
    d = http_json("POST", "/api/v1/login", body={"user": user, "password": password})
    if d.get("status") != "success":
        raise RuntimeError(f"login failed for {user}: {d}")
    return d["data"]["authToken"], d["data"]["userId"]


def start_and_join_urls() -> tuple[str, str, str, str]:
    """call_id, principal_url, grok_url, rid"""
    env = load_env(SECRETS)
    g_token, g_uid = login(
        env["ROCKETCHAT_OPERATOR_USERNAME"], env["ROCKETCHAT_OPERATOR_PASSWORD"]
    )
    p_token, p_uid = login(
        env["ROCKETCHAT_ADMIN_USERNAME"], env["ROCKETCHAT_ADMIN_PASSWORD"]
    )
    ims = http_json("GET", "/api/v1/im.list?count=50", g_token, g_uid)
    rid = None
    for im in ims.get("ims") or []:
        us = set(im.get("usernames") or [])
        if "principal" in us and "grok" in us:
            rid = im["_id"]
            break
    if not rid:
        raise RuntimeError("principal↔grok DM not found")

    start = http_json(
        "POST",
        "/api/v1/video-conference.start",
        g_token,
        g_uid,
        {"roomId": rid},
    )
    call_id = (start.get("data") or {}).get("callId")
    if not call_id:
        raise RuntimeError(f"no callId: {start}")

    def join(token: str, uid: str, name: str) -> str:
        j = http_json(
            "POST",
            "/api/v1/video-conference.join",
            token,
            uid,
            {"callId": call_id, "state": {"mic": True, "cam": False}},
        )
        url = j.get("url") or (j.get("data") or {}).get("url")
        if not url:
            raise RuntimeError(f"no join url: {j}")
        # Append display name query for voice room (hash ignored by our page)
        sep = "&" if "?" in url.split("#")[0] else "?"
        base = url
        if "#" in base:
            # move identity into query before hash for our room page
            path, frag = base.split("#", 1)
            base = f"{path}{sep}name={name}"
        else:
            base = f"{base}{sep}name={name}"
        return base

    return (
        call_id,
        join(p_token, p_uid, "PrincipalProbe"),
        join(g_token, g_uid, "GrokProbe"),
        rid,
    )


def make_tone_wav(path: Path, seconds: float = 1.0, hz: float = 880.0, rate: int = 48000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(seconds * rate)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for i in range(n):
            val = int(0.5 * 32767 * math.sin(2 * math.pi * hz * (i / rate)))
            frames += struct.pack("<h", val)
        w.writeframes(frames)
    return path


def webm_rms(b64: str, out_webm: Path) -> float:
    out_webm.parent.mkdir(parents=True, exist_ok=True)
    out_webm.write_bytes(base64.b64decode(b64))
    wav = out_webm.with_suffix(".wav")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(out_webm), "-ac", "1", "-ar", "16000", str(wav)],
            check=True,
            capture_output=True,
            timeout=60,
        )
    except subprocess.CalledProcessError:
        return 0.0
    with wave.open(str(wav), "rb") as w:
        frames = w.readframes(w.getnframes())
    if len(frames) < 2:
        return 0.0
    acc = 0.0
    n = 0
    for i in range(0, len(frames) - 1, 2):
        sample = struct.unpack_from("<h", frames, i)[0] / 32768.0
        acc += sample * sample
        n += 1
    return math.sqrt(acc / n) if n else 0.0


def run(settle_s: float, record_s: float, headed: bool) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report: dict = {"ts": time.time(), "ok": False}

    try:
        call_id, p_url, g_url, rid = start_and_join_urls()
    except Exception as e:
        report["error"] = str(e)
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 3

    report.update(
        {
            "call_id": call_id,
            "rid": rid,
            "principal_url": p_url[:220],
            "grok_url": g_url[:220],
            "provider_hint": (
                "voice_room"
                if "8090" in p_url or "voice" in p_url
                else ("jitsi_public" if "meet.jit.si" in p_url else "other")
            ),
        }
    )

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=not headed,
            args=[
                "--autoplay-policy=no-user-gesture-required",
                "--use-fake-ui-for-media-stream",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        ctx_p = browser.new_context(permissions=["microphone", "camera"], ignore_https_errors=True)
        ctx_g = browser.new_context(permissions=["microphone", "camera"], ignore_https_errors=True)
        # Grant mic for the actual VideoConf origin (LAN voice room or Jitsi)
        try:
            from urllib.parse import urlparse

            for u in (p_url, g_url):
                p = urlparse(u)
                origin = f"{p.scheme}://{p.netloc}"
                for ctx in (ctx_p, ctx_g):
                    try:
                        ctx.grant_permissions(["microphone", "camera"], origin=origin)
                    except Exception:
                        pass
        except Exception:
            pass
        page_p = ctx_p.new_page()
        page_g = ctx_g.new_page()
        # Grok publishes continuous tone via GUM override (before room JS runs)
        page_g.add_init_script(INIT_GROK_TONE)
        # Principal: quiet carrier so headless GUM succeeds (voice room needs a local track)
        page_p.add_init_script(
            INIT_GROK_TONE.replace("880", "200").replace("0.4", "0.0008")
        )
        # Only use RTCPeerConnection hook for legacy Jitsi; it can interfere with voice room
        if "meet.jit.si" in p_url:
            page_p.add_init_script(INIT_PRINCIPAL)

        # Same-host dual-peer: prefer loopback if domain is this machine's LAN IP
        # (WebRTC ICE via LAN self-hairpin is flaky in headless Chromium).
        def prefer_loopback(u: str) -> str:
            import socket

            lan_hosts = {"10.71.11.69"}
            try:
                # best-effort: primary outbound interface IP
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                lan_hosts.add(s.getsockname()[0])
                s.close()
            except Exception:
                pass
            for host in lan_hosts:
                if host and host in u:
                    return u.replace(host, "127.0.0.1")
            return u

        p_nav = prefer_loopback(p_url)
        g_nav = prefer_loopback(g_url)
        report["nav_principal_url"] = p_nav[:220]
        report["nav_grok_url"] = g_nav[:220]

        page_p.goto(p_nav, wait_until="domcontentloaded", timeout=60_000)
        page_g.goto(g_nav, wait_until="domcontentloaded", timeout=60_000)

        # Wait for remote tracks
        deadline = time.time() + settle_s
        last_diag = {}
        while time.time() < deadline:
            try:
                last_diag = page_p.evaluate(
                    """() => {
                      if (window.__voiceRoom) {
                        return {
                          remoteCount: window.__voiceRoom.remoteTrackCount || 0,
                          localReady: window.__voiceRoom.localReady,
                          peers: window.__voiceRoom.peers ? window.__voiceRoom.peers() : [],
                          via: 'voiceRoom',
                        };
                      }
                      if (window.__probeDiag) return window.__probeDiag();
                      return {};
                    }"""
                )
            except Exception as e:
                last_diag = {"err": str(e)}
            if (last_diag or {}).get("remoteCount", 0) >= 1:
                break
            page_p.wait_for_timeout(500)
            page_g.wait_for_timeout(200)

        report["diag_before_record"] = last_diag

        # Record using page helpers
        rec = page_p.evaluate(
            """async (sec) => {
              // Prefer voice room remoteAudio stream
              const ra = document.getElementById('remoteAudio');
              let stream = null;
              if (ra && ra.srcObject && ra.srcObject.getAudioTracks().length) {
                stream = ra.srcObject;
              } else if (window.__remoteMix && window.__remoteMix.stream) {
                stream = window.__remoteMix.stream;
              }
              if (!stream || !stream.getAudioTracks().length) {
                return { ok: false, reason: 'no_remote_tracks',
                  count: stream ? stream.getAudioTracks().length : 0,
                  diag: window.__voiceRoom ? {
                    remoteCount: window.__voiceRoom.remoteTrackCount,
                    peers: window.__voiceRoom.peers(),
                  } : null };
              }
              let mime = 'audio/webm';
              if (!MediaRecorder.isTypeSupported(mime)) mime = '';
              const rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
              const chunks = [];
              rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
              const done = new Promise((r) => { rec.onstop = () => r(chunks); });
              rec.start(100);
              await new Promise((r) => setTimeout(r, Math.floor(sec * 1000)));
              rec.stop();
              const parts = await done;
              if (!parts.length) return { ok: false, reason: 'empty_chunks', count: stream.getAudioTracks().length };
              const blob = new Blob(parts, { type: mime || 'audio/webm' });
              const ab = await blob.arrayBuffer();
              const bytes = new Uint8Array(ab);
              let s = '';
              for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
              return { ok: true, b64: btoa(s), bytes: bytes.length, count: stream.getAudioTracks().length };
            }""",
            record_s,
        )
        report["record"] = {
            k: (rec or {}).get(k)
            for k in ("ok", "reason", "bytes", "count", "diag")
            if isinstance(rec, dict)
        }
        rms = 0.0
        if isinstance(rec, dict) and rec.get("ok") and rec.get("b64"):
            rms = webm_rms(rec["b64"], OUT_DIR / "principal-remote.webm")
        report["remote_rms"] = rms
        threshold = float(os.environ.get("RC_PREFLIGHT_RMS_OK", "0.008"))
        report["threshold"] = threshold
        report["ok"] = rms >= threshold
        try:
            report["grok_local"] = page_g.evaluate(
                "() => window.__probeLocalInfo ? window.__probeLocalInfo() : (window.__voiceRoom || {})"
            )
            report["title_p"] = page_p.title()
            report["url_p"] = page_p.url[:160]
            page_p.screenshot(path=str(OUT_DIR / "principal-final.png"))
            page_g.screenshot(path=str(OUT_DIR / "grok-final.png"))
        except Exception as e:
            report["meta_err"] = str(e)
        browser.close()

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nReport: {REPORT}")
    if report["ok"]:
        print("RESULT: PASS — remote audio energy detected on RC Call media path.")
        return 0
    print("RESULT: FAIL — no remote audio energy.")
    return 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--settle-s", type=float, default=20.0)
    ap.add_argument("--record-s", type=float, default=3.5)
    ap.add_argument("--headed", action="store_true")
    # legacy flags ignored for compatibility
    ap.add_argument("--mode", default="inject")
    ap.add_argument("--join-url", default=None)
    args = ap.parse_args()
    try:
        return run(args.settle_s, args.record_s, args.headed)
    except Exception as e:
        print(f"SETUP FAIL: {e}", file=sys.stderr)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps({"ok": False, "error": str(e)}, indent=2))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
