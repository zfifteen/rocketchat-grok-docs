#!/usr/bin/env python3
"""
NF-SPEC-01 True Voice in RC Call — unit/contract tests on shipped code.

Usage:
  RC_TEST_SCRATCH=... python3 tests/test_nf01_true_voice_call.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

OPS = Path.home() / ".grok" / "agency" / "ops" / "rocketchat"
CALL_DIR = OPS / "call"
WAKE_DIR = OPS / "wake"
SCRATCH = Path(
    os.environ.get(
        "RC_TEST_SCRATCH",
        "/var/folders/k_/spz3zlj566sc4qh29g0tk6jh0000gn/T/grok-goal-9797386b3c40/implementer",
    )
)
SCRATCH.mkdir(parents=True, exist_ok=True)

RESULTS: list[tuple[str, str, str]] = []
BACKEND_EVIDENCE: list[str] = []
TOKEN_EVIDENCE: list[str] = []
SPAWN_EVIDENCE: list[str] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    RESULTS.append((name, status, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def _load(name: str, path: Path):
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    if name in sys.modules and name in ("rc_call_media", "voice_agent_worker"):
        del sys.modules[name]
    if name in sys.modules and name not in ("rc_call_media", "voice_agent_worker"):
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Gate 1 — backend flag + lock
# ---------------------------------------------------------------------------


def test_backend_flag_selection() -> None:
    try:
        m = _load("rc_call_media", CALL_DIR / "rc_call_media.py")
        assert m.call_media_backend({"RC_CALL_MEDIA_BACKEND": "livekit"}) == "livekit"
        assert m.call_media_backend({"RC_CALL_MEDIA_BACKEND": "playwright"}) == "playwright"
        assert m.call_media_backend({}) == "playwright"  # pre-cutover default
        assert m.is_livekit_backend({"RC_CALL_MEDIA_BACKEND": "livekit"})
        assert m.is_playwright_lab_backend({"RC_CALL_MEDIA_BACKEND": "playwright"})
        # aliases
        assert m.call_media_backend({"RC_CALL_MEDIA_BACKEND": "voice_agent"}) == "livekit"
        BACKEND_EVIDENCE.append("default_backend=playwright pre-cutover")
        BACKEND_EVIDENCE.append("livekit chosen when RC_CALL_MEDIA_BACKEND=livekit")
        record("backend_flag_selection", True)
    except Exception as e:
        record("backend_flag_selection", False, repr(e) + traceback.format_exc())


def test_call_lock_single_flight() -> None:
    try:
        m = _load("rc_call_media", CALL_DIR / "rc_call_media.py")
        with tempfile.TemporaryDirectory(dir=str(SCRATCH)) as td:
            lock = Path(td) / "call-bot.lock"
            alive = {42: True}

            def kill_check(pid):
                return bool(alive.get(pid))

            ok = m.acquire_call_lock(
                lock,
                call_id="c1",
                room_id="r1",
                backend="livekit",
                pid=42,
                started_at="t0",
                kill_check=kill_check,
            )
            assert ok is True
            # second spawn while busy → reject
            ok2 = m.acquire_call_lock(
                lock,
                call_id="c1",
                room_id="r1",
                backend="livekit",
                pid=99,
                kill_check=kill_check,
            )
            assert ok2 is False
            ok3 = m.acquire_call_lock(
                lock,
                call_id="c2",
                room_id="r2",
                backend="playwright",
                pid=99,
                kill_check=kill_check,
            )
            assert ok3 is False
            BACKEND_EVIDENCE.append("second spawn same/other callId rejected while busy")

            # kill worker → stale clear → re-acquire
            alive[42] = False
            assert m.clear_stale_call_lock(lock, kill_check=kill_check) is True
            ok4 = m.acquire_call_lock(
                lock,
                call_id="c1",
                room_id="r1",
                backend="livekit",
                pid=7,
                kill_check=kill_check,
            )
            assert ok4 is True
            assert m.release_call_lock(lock, call_id="c1", only_if_call_id=True)
            assert not lock.is_file()
            BACKEND_EVIDENCE.append("stale lock cleared; re-acquire ok; release ok")

            # pid=None lock is never busy
            assert m.acquire_call_lock(
                lock, call_id="c3", room_id="r3", backend="playwright", pid=None
            )
            assert m.call_lock_is_busy(lock, kill_check=kill_check) is False
            assert m.clear_stale_call_lock(lock, kill_check=kill_check) is True
            BACKEND_EVIDENCE.append("pid=None lock not busy; cleared")
        record("call_lock_single_flight", True)
    except Exception as e:
        record("call_lock_single_flight", False, repr(e) + traceback.format_exc())


def test_phone_facing_lan_join_host() -> None:
    """Phone join host must be current LAN, never loopback."""
    try:
        m = _load("rc_call_media", CALL_DIR / "rc_call_media.py")
        assert m.is_loopback_host("127.0.0.1")
        assert m.is_loopback_host("localhost")
        assert not m.is_loopback_host("192.168.1.149")
        ip = m.resolve_primary_lan_ipv4(candidates=["127.0.0.1", "192.168.1.50"])
        assert ip == "192.168.1.50"
        netloc = m.phone_facing_voice_room_netloc(lan_ip="192.168.1.50", port=8090)
        assert netloc == "192.168.1.50:8090"
        assert "127.0.0.1" not in netloc
        url = m.phone_facing_join_url("abc123", lan_ip="192.168.1.50", port=8090)
        assert url == "http://192.168.1.50:8090/Agencyabc123"
        assert m.join_url_host_is_phone_safe(url, lan_ip="192.168.1.50")
        assert not m.join_url_host_is_phone_safe(
            "http://127.0.0.1:8090/Agencyabc123", lan_ip="192.168.1.50"
        )
        rewritten = m.rewrite_loopback_join_url_to_lan(
            "http://127.0.0.1:8090/Agencyxyz", lan_ip="10.0.0.9"
        )
        assert rewritten == "http://10.0.0.9:8090/Agencyxyz"
        assert m.should_supersede_lock_for_new_call(
            m.CallLockMeta(call_id="old", room_id="r", pid=1), "new"
        )
        assert not m.should_supersede_lock_for_new_call(
            m.CallLockMeta(call_id="same", room_id="r", pid=1), "same"
        )
        assert m.call_no_peer_timeout_s({}) >= 20
        BACKEND_EVIDENCE.append(f"phone_facing_netloc={netloc} join={url}")
        record("phone_facing_lan_join_host", True)
    except Exception as e:
        record("phone_facing_lan_join_host", False, repr(e) + traceback.format_exc())


def test_timeout_and_status_config() -> None:
    try:
        m = _load("rc_call_media", CALL_DIR / "rc_call_media.py")
        assert m.voice_max_duration_s({"RC_VOICE_MAX_DURATION_S": "900"}) == 900
        assert m.voice_idle_timeout_s({"RC_VOICE_IDLE_TIMEOUT_S": "90"}) == 90
        assert m.voice_max_duration_s({}) >= 30
        assert m.voice_idle_timeout_s({}) >= 15
        assert m.voice_greeting({"RC_VOICE_GREETING": "Hi."}) == "Hi."
        msg = m.format_call_status_message(
            "connecting", call_id="abcdef1234567890", greeting="Hello"
        )
        assert "connecting" in msg.lower() and "Hello" in msg
        assert "transcript" not in msg.lower()
        fail = m.format_call_status_message("failed", call_id="c1", detail="no token")
        assert "failed" in fail.lower()
        end = m.format_call_status_message("ended", call_id="c1")
        assert "ended" in end.lower()
        # secrets must not appear
        assert m.status_must_not_contain_secrets(
            msg, ["supersecret", "sk-live-xxx"]
        )
        BACKEND_EVIDENCE.append(
            f"timeouts max={m.voice_max_duration_s({})} idle={m.voice_idle_timeout_s({})}"
        )
        record("timeout_and_status_config", True)
    except Exception as e:
        record("timeout_and_status_config", False, repr(e) + traceback.format_exc())


# ---------------------------------------------------------------------------
# Gate 2 — token / worker contracts
# ---------------------------------------------------------------------------


def test_livekit_token_and_room() -> None:
    try:
        m = _load("rc_call_media", CALL_DIR / "rc_call_media.py")
        room = m.room_name_from_call_id("6a1b2c3d")
        assert room == "Agency6a1b2c3d", room
        assert m.room_name_from_call_id("Agencyxyz") == "Agencyxyz"
        secret = "livekit_api_secret_value_for_tests_32b"
        tok = m.mint_livekit_access_token(
            api_key="APItestkey",
            api_secret=secret,
            identity="grok",
            room=room,
            ttl_s=300,
            now=1_700_000_000.0,
        )
        assert tok.count(".") == 2
        assert secret not in tok
        assert not m.token_contains_raw_secret(tok, secret)
        # payload contains room grant (decode middle segment)
        import base64

        mid = tok.split(".")[1]
        pad = "=" * (-len(mid) % 4)
        payload = json.loads(base64.urlsafe_b64decode(mid + pad))
        assert payload["sub"] == "grok"
        assert payload["video"]["room"] == room
        assert payload["video"]["roomJoin"] is True
        assert payload["exp"] - payload["nbf"] <= 400
        mat = m.livekit_join_url("wss://example.livekit.cloud", tok, room=room)
        parsed = m.parse_join_material(mat)
        assert parsed["url"].startswith("wss://")
        assert parsed["token"] == tok
        assert secret not in mat
        TOKEN_EVIDENCE.append(f"room={room} token_segments=3 grant_room={payload['video']['room']}")
        TOKEN_EVIDENCE.append("api_secret not in JWT or join material")
        record("livekit_token_and_room", True)
    except Exception as e:
        record("livekit_token_and_room", False, repr(e) + traceback.format_exc())


def test_worker_argv_and_brain_contract() -> None:
    try:
        m = _load("rc_call_media", CALL_DIR / "rc_call_media.py")
        plan = m.build_voice_worker_argv(
            call_id="call99",
            room_id="rid99",
            room_name="dm",
            python_bin="python3",
            env={
                "RC_VOICE_MAX_DURATION_S": "600",
                "RC_VOICE_IDLE_TIMEOUT_S": "45",
                "RC_VOICE_GREETING": "Grok here.",
                "RC_LIVEKIT_URL": "wss://lk.example",
            },
        )
        assert "--call-id" in plan.argv and "call99" in plan.argv
        assert "--room-id" in plan.argv and "rid99" in plan.argv
        assert "--livekit-room" in plan.argv and "Agencycall99" in plan.argv
        assert "--max-duration-s" in plan.argv and "600" in plan.argv
        assert "--idle-timeout-s" in plan.argv and "45" in plan.argv
        assert plan.uses_playwright is False
        assert plan.uses_whisper_cli_tts_primary is False
        assert m.worker_brain_is_voice_agent(plan)
        assert "voice_agent_worker" in " ".join(plan.argv)

        be, argv, vplan = m.select_spawn_plan(
            call_id="c1",
            room_id="r1",
            env={"RC_CALL_MEDIA_BACKEND": "livekit"},
        )
        assert be == "livekit" and vplan is not None
        assert "voice_agent" in " ".join(argv)

        be2, argv2, vplan2 = m.select_spawn_plan(
            call_id="c1",
            room_id="r1",
            env={"RC_CALL_MEDIA_BACKEND": "playwright"},
        )
        assert be2 == "playwright" and vplan2 is None
        assert "rc_call_bot" in " ".join(argv2)
        TOKEN_EVIDENCE.append(f"livekit argv has call/room ids; brain={plan.brain}")
        TOKEN_EVIDENCE.append("playwright only when lab flag set")
        record("worker_argv_and_brain_contract", True)
    except Exception as e:
        record("worker_argv_and_brain_contract", False, repr(e) + traceback.format_exc())


def test_worker_validate_only_subprocess() -> None:
    try:
        env = os.environ.copy()
        env["RC_LIVEKIT_URL"] = "wss://test.livekit.cloud"
        env["RC_LIVEKIT_API_KEY"] = "APIunittest"
        env["RC_LIVEKIT_API_SECRET"] = "unittest_secret_at_least_32_chars!!"
        env.pop("XAI_API_KEY", None)
        worker = CALL_DIR / "voice_agent_worker.py"
        assert worker.is_file()
        tok_path = SCRATCH / "nf01-worker-token.jwt"
        proc = subprocess.run(
            [
                sys.executable,
                str(worker),
                "--call-id",
                "labcall1",
                "--room-id",
                "roomlab",
                "--validate-only",
                "--token-file",
                str(tok_path),
            ],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        assert proc.returncode == 0, out
        assert "VOICE_AGENT_VALIDATE" in out
        # Parse structured result line (brain contract)
        val_line = [ln for ln in out.splitlines() if "VOICE_AGENT_VALIDATE" in ln][-1]
        payload = json.loads(val_line.split("VOICE_AGENT_VALIDATE", 1)[1].strip())
        assert payload.get("ok") is True
        assert payload.get("brain") == "grok_voice_agent_realtime"
        assert payload.get("uses_whisper_cli_tts_primary") is False
        assert payload.get("uses_playwright") is False
        assert tok_path.is_file()
        jwt = tok_path.read_text().strip()
        assert jwt.count(".") == 2
        assert env["RC_LIVEKIT_API_SECRET"] not in jwt
        assert env["RC_LIVEKIT_API_SECRET"] not in out
        TOKEN_EVIDENCE.append(
            f"validate-only rc=0 brain={payload.get('brain')} "
            f"whisper_primary={payload.get('uses_whisper_cli_tts_primary')} "
            f"token_file_len={len(jwt)} secret_not_in_log=True"
        )
        record("worker_validate_only_subprocess", True)
    except Exception as e:
        record(
            "worker_validate_only_subprocess",
            False,
            repr(e) + traceback.format_exc(),
        )


# ---------------------------------------------------------------------------
# Gate 3 — operator spawn lifecycle
# ---------------------------------------------------------------------------


def test_operator_spawn_livekit_vs_playwright() -> None:
    try:
        # Ensure call path importable from wake
        if str(CALL_DIR) not in sys.path:
            sys.path.insert(0, str(CALL_DIR))
        agent = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
        with tempfile.TemporaryDirectory(dir=str(SCRATCH)) as td:
            tmp = Path(td)
            agent.LOG_DIR = tmp / "logs"
            agent.LOG_DIR.mkdir(parents=True)
            agent.LOG_PATH = agent.LOG_DIR / "op.log"
            agent.CALL_LOCK = agent.LOG_DIR / "call-bot.lock"
            agent.LOCK_DIR = agent.LOG_DIR / "wake.lock.d"
            agent.STATE_PATH = tmp / "state.json"
            agent.VOICE_AGENT = CALL_DIR / "voice_agent_worker.py"
            agent.CALL_BOT = CALL_DIR / "rc_call_bot.py"
            agent.AGENCY = OPS.parent  # agency root
            agent.save_state({"processed_ids": []})

            spawned: list[list[str]] = []
            posts: list[str] = []
            # Use this test process PID so call_lock_is_busy sees a live holder
            live_pid = os.getpid()

            class FakeProc:
                def __init__(self):
                    self.pid = live_pid

            def fake_popen(cmd, **kwargs):
                spawned.append(list(cmd))
                return FakeProc()

            import subprocess as _sp_mod

            _real_popen = _sp_mod.Popen
            try:
                agent.subprocess.Popen = fake_popen  # type: ignore
                agent.post_as_grok = lambda rid, text: posts.append(text) or True

                # LiveKit backend
                os.environ["RC_CALL_MEDIA_BACKEND"] = "livekit"
                ok = agent.spawn_call_bot("callLK1", "room1", room_name="dm")
                assert ok is True, "livekit spawn should succeed"
                assert spawned, "Popen must be called"
                assert any("voice_agent" in str(c) for c in spawned[0]), spawned[0]
                assert "rc_call_bot" not in " ".join(spawned[0])
                assert agent.CALL_LOCK.is_file()
                meta = json.loads(agent.CALL_LOCK.read_text())
                assert meta.get("call_id") == "callLK1"
                assert meta.get("pid") == live_pid
                assert meta.get("backend") == "livekit"
                SPAWN_EVIDENCE.append(
                    f"livekit spawn argv_has_voice_agent=True pid={meta.get('pid')} "
                    f"backend={meta.get('backend')}"
                )

                # Second spawn same callId rejected (lock held by live pid)
                spawned.clear()
                ok2 = agent.spawn_call_bot("callLK1", "room1")
                assert ok2 is False, "second spawn must no-op while lock busy"
                assert not spawned
                SPAWN_EVIDENCE.append("second spawn same lock rejected")

                # Different callId supersedes prior lock holder (no false busy)
                hangups: list[dict] = []

                def fake_hangup(**kwargs):
                    hangups.append(kwargs)
                    agent.CALL_LOCK.unlink(missing_ok=True)
                    return {"ok": True}

                agent.hangup_call_media = fake_hangup  # type: ignore
                # re-acquire busy lock for old call
                agent.CALL_LOCK.write_text(
                    json.dumps(
                        {
                            "call_id": "callLK1",
                            "room_id": "room1",
                            "backend": "livekit",
                            "pid": live_pid,
                            "started_at": "t0",
                        }
                    ),
                    encoding="utf-8",
                )
                spawned.clear()
                os.environ["RC_CALL_MEDIA_BACKEND"] = "playwright"
                ok_sup = agent.spawn_call_bot("callNEW99", "room2")
                assert hangups, "must supersede hangup prior media"
                assert hangups[0].get("call_id") == "callLK1"
                assert ok_sup is True, "new callId must spawn after supersede"
                assert any("rc_call_bot" in str(c) for c in spawned[0]), spawned[0]
                SPAWN_EVIDENCE.append(
                    f"supersede hangup prior callId + spawn new={spawned[0][:4]}"
                )

                # Release and switch to playwright (clean)
                agent.CALL_LOCK.unlink(missing_ok=True)
                os.environ["RC_CALL_MEDIA_BACKEND"] = "playwright"
                spawned.clear()
                ok3 = agent.spawn_call_bot("callPW1", "room2")
                assert ok3 is True
                assert any("rc_call_bot" in str(c) for c in spawned[0]), spawned[0]
                assert "voice_agent" not in " ".join(spawned[0])
                SPAWN_EVIDENCE.append("playwright lab spawn uses rc_call_bot")

                # handle_videoconf_call sparse status
                agent.CALL_LOCK.unlink(missing_ok=True)
                os.environ["RC_CALL_MEDIA_BACKEND"] = "livekit"
                posts.clear()
                spawned.clear()
                msg = {
                    "_id": "vc-mid-1",
                    "rid": "room1",
                    "t": "videoconf",
                    "msg": "",
                    "u": {"username": "principal"},
                    "blocks": [{"callId": "vccall99", "type": "video_conf"}],
                }
                from wake_lib import is_videoconf_message

                assert is_videoconf_message(msg)
                agent.videoconf_call_id = lambda m: "vccall99"
                agent.handle_videoconf_call(msg, "room1", room_name="dm:principal")
                assert posts, "must post sparse status"
                assert (
                    "Call" in posts[0]
                    or "connecting" in posts[0].lower()
                    or "Answering" in posts[0]
                )
                assert "whisper" not in posts[0].lower()
                assert "transcript" not in posts[0].lower()
                SPAWN_EVIDENCE.append(f"videoconf status={posts[0][:80]!r}")

                # Failure path: busy lock
                posts.clear()
                agent.handle_videoconf_call(
                    {
                        "_id": "vc-mid-2",
                        "rid": "room1",
                        "t": "videoconf",
                        "u": {"username": "principal"},
                        "blocks": [{"callId": "vccall99", "type": "video_conf"}],
                    },
                    "room1",
                )
                if posts:
                    SPAWN_EVIDENCE.append(f"busy/fail status={posts[0][:80]!r}")
                st = agent.load_state()
                assert "vc-mid-1" in (st.get("processed_ids") or [])
            finally:
                # Critical: do not leave FakeProc on global subprocess.Popen
                _sp_mod.Popen = _real_popen
                agent.subprocess.Popen = _real_popen  # type: ignore

        record("operator_spawn_livekit_vs_playwright", True)
    except Exception as e:
        record(
            "operator_spawn_livekit_vs_playwright",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_source_contracts_structural() -> None:
    try:
        op = (WAKE_DIR / "rc_operator_agent.py").read_text(encoding="utf-8")
        assert "RC_CALL_MEDIA_BACKEND" in op or "call_media_backend" in op
        assert "voice_agent" in op
        assert "select_spawn_plan" in op or "spawn_call_bot" in op
        assert "hangup_call_media" in op or "terminate_call_worker" in op
        assert "STATUS_ENDED" in op
        worker = (CALL_DIR / "voice_agent_worker.py").read_text(encoding="utf-8")
        assert "voice_audio_bridge" in worker
        assert "build_greeting_response_create" in worker or "response.create" in worker
        assert "rc_call_bot" not in worker
        assert (CALL_DIR / "rc_call_media.py").is_file()
        assert (CALL_DIR / "voice_audio_bridge.py").is_file()
        assert (CALL_DIR / "run_voice_agent.sh").is_file()
        req = (OPS / "requirements.txt").read_text(encoding="utf-8")
        assert "livekit" in req and "websockets" in req
        SPAWN_EVIDENCE.append("structural: bridge module + hangup + deps in requirements")
        record("source_contracts_structural", True)
    except Exception as e:
        record("source_contracts_structural", False, repr(e))


def test_audio_bridge_greeting_and_duplex() -> None:
    """
    Drive shipped VoiceAudioBridge (not a reimplementation): greeting bootstrap,
    mic→Realtime append, audio delta→publish. No network.
    """
    try:
        b = _load("voice_audio_bridge", CALL_DIR / "voice_audio_bridge.py")
        # Pure encode/decode roundtrip used by Realtime path
        pcm = b"\x10\x00\x20\x00\x30\x00"
        assert b.b64_to_pcm16(b.pcm16_to_b64(pcm)) == pcm

        sess = b.build_session_update(b.BridgeConfig(call_id="c", greeting="Hi there."))
        assert sess["type"] == "session.update"
        assert sess["session"]["turn_detection"]["type"] == "server_vad"
        assert "Hi there." in sess["session"]["instructions"]
        greet = b.build_greeting_response_create(b.BridgeConfig(call_id="c", greeting="Hi there."))
        assert greet["type"] == "response.create"
        assert "Hi there." in greet["response"]["instructions"]

        # Full simulation helper is the shipped duplex proof
        state = b.simulate_greeting_duplex_session(greeting="Hello, Grok speaking.")
        assert state.greeting_sent is True
        assert state.outbound_frames >= 2
        assert state.inbound_frames >= 1
        assert state.published_pcm_bytes > 0
        assert state.subscribed_pcm_bytes > 0
        assert state.greeting_audio_frames >= 1
        assert state.end_reason in (b.EndReason.HANGUP, b.EndReason.CLEAN)

        # Manual bridge: hangup ends and releases activity
        clock = {"t": 0.0}
        rt = b.FakeRealtimeTransport()
        media = b.FakeMediaTransport()
        bridge = b.VoiceAudioBridge(
            cfg=b.BridgeConfig(call_id="h1", max_duration_s=100, idle_timeout_s=50),
            realtime=rt,
            media=media,
            now_fn=lambda: clock["t"],
        )
        bridge.start()
        assert any(e["type"] == "session.update" for e in rt.sent)
        assert any(e["type"] == "response.create" for e in rt.sent)
        # inject model audio
        rt.push(
            {
                "type": "response.audio.delta",
                "delta": b.pcm16_to_b64(b"\x01\x00" * 100),
            }
        )
        clock["t"] = 1.0
        assert bridge.step() is True
        assert len(media.published) == 1
        bridge.request_hangup()
        assert bridge.step() is False
        assert bridge.state.end_reason == b.EndReason.HANGUP

        # idle timeout
        clock2 = {"t": 0.0}
        bridge2 = b.VoiceAudioBridge(
            cfg=b.BridgeConfig(call_id="i1", max_duration_s=1000, idle_timeout_s=5),
            realtime=b.FakeRealtimeTransport(),
            media=b.FakeMediaTransport(),
            now_fn=lambda: clock2["t"],
        )
        bridge2.start()
        clock2["t"] = 10.0
        assert bridge2.step() is False
        assert bridge2.state.end_reason == b.EndReason.IDLE_TIMEOUT

        TOKEN_EVIDENCE.append(
            f"bridge duplex out={state.outbound_frames} in={state.inbound_frames} "
            f"greeting_audio={state.greeting_audio_frames} end={state.end_reason}"
        )
        TOKEN_EVIDENCE.append("bridge hangup+idle_timeout end reasons work")
        record("audio_bridge_greeting_and_duplex", True)
    except Exception as e:
        record(
            "audio_bridge_greeting_and_duplex",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_worker_bridge_sim_subprocess() -> None:
    try:
        worker = CALL_DIR / "voice_agent_worker.py"
        proc = subprocess.run(
            [
                sys.executable,
                str(worker),
                "--call-id",
                "simcall",
                "--room-id",
                "rsim",
                "--bridge-sim",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        assert proc.returncode == 0, out
        assert "VOICE_AGENT_BRIDGE_SIM" in out
        line = [ln for ln in out.splitlines() if "VOICE_AGENT_BRIDGE_SIM" in ln][-1]
        payload = json.loads(line.split("VOICE_AGENT_BRIDGE_SIM", 1)[1].strip())
        assert payload["ok"] is True
        assert payload["uses_whisper_cli_tts_primary"] is False
        assert payload["state"]["greeting_sent"] is True
        assert payload["state"]["outbound_frames"] >= 1
        assert payload["state"]["inbound_frames"] >= 1
        TOKEN_EVIDENCE.append(
            f"bridge-sim rc=0 greeting_sent={payload['state']['greeting_sent']} "
            f"out={payload['state']['outbound_frames']}"
        )
        record("worker_bridge_sim_subprocess", True)
    except Exception as e:
        record(
            "worker_bridge_sim_subprocess",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_hangup_terminates_and_releases_lock() -> None:
    """
    Gate 3 hangup on REAL intake path:

    handle_principal_message → is_videoconf_message(end) → hangup
    asserts SIGTERM + lock release + STATUS_ENDED.

    Must NOT call handle_videoconf_call directly (that skipped intake).
    """
    try:
        m = _load("rc_call_media", CALL_DIR / "rc_call_media.py")
        wl = _load("wake_lib", WAKE_DIR / "wake_lib.py")
        if str(CALL_DIR) not in sys.path:
            sys.path.insert(0, str(CALL_DIR))
        # Force reload operator so wake_lib is_videoconf_message changes apply
        if "rc_operator_agent" in sys.modules:
            del sys.modules["rc_operator_agent"]
        agent = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")

        # Spot-check: end types are videoconf messages for intake
        end_probe = {"t": "videoconf-end", "msg": "", "u": {"username": "principal"}}
        assert wl.is_videoconf_end_message(end_probe) is True
        assert wl.is_videoconf_message(end_probe) is True
        start_probe = {"t": "videoconf", "u": {"username": "principal"}}
        assert wl.is_videoconf_message(start_probe) is True
        SPAWN_EVIDENCE.append(
            "is_videoconf_message(videoconf-end)=True (intake will route)"
        )

        with tempfile.TemporaryDirectory(dir=str(SCRATCH)) as td:
            tmp = Path(td)
            lock = Path(td) / "call-bot.lock"
            killed: list[tuple[int, int]] = []

            def fake_kill(pid, sig):
                killed.append((pid, sig))

            # Pure helper terminate
            assert m.acquire_call_lock(
                lock,
                call_id="hang1",
                room_id="r1",
                backend="livekit",
                pid=555,
                kill_check=lambda p: True,
            )
            res = m.terminate_call_worker(
                lock, call_id="hang1", kill_fn=fake_kill, signal_num=15
            )
            assert res["signalled"] is True
            assert res["lock_released"] is True
            assert killed == [(555, 15)]
            SPAWN_EVIDENCE.append("terminate_call_worker signalled pid=555 lock_released=True")

            # --- REAL PATH: handle_principal_message with videoconf-end ---
            agent.LOG_DIR = tmp / "logs"
            agent.LOG_DIR.mkdir(parents=True)
            agent.LOG_PATH = agent.LOG_DIR / "op.log"
            agent.CALL_LOCK = agent.LOG_DIR / "call-bot.lock"
            agent.STATE_PATH = tmp / "state.json"
            agent.LOCK_DIR = agent.LOG_DIR / "wake.lock.d"
            agent.save_state({"processed_ids": [], "pending_wakes": []})
            posts: list[str] = []
            agent.post_as_grok = lambda rid, text: posts.append(text) or True
            # prevent drain threads / collab
            agent._drain_pending_wakes = lambda: None
            agent.collab_armed_for_room = lambda *a, **k: False

            live_pid = os.getpid()
            assert m.acquire_call_lock(
                agent.CALL_LOCK,
                call_id="hang-intake",
                room_id="roomH",
                backend="livekit",
                pid=live_pid,
            )
            assert agent.CALL_LOCK.is_file()

            killed_sig: list[tuple[int, int]] = []

            def term_wrap(lock_path, **kw):
                def kfn(pid, sig):
                    killed_sig.append((pid, int(sig)))

                kw = dict(kw)
                kw["kill_fn"] = kfn
                return m.terminate_call_worker(lock_path, **kw)

            # hangup_call_media resolves terminate_call_worker at runtime from globals
            import rc_operator_agent as opmod

            opmod.terminate_call_worker = term_wrap  # type: ignore

            end_msg = {
                "_id": "vc-end-intake-1",
                "rid": "roomH",
                "t": "videoconf-end",
                "msg": "",
                "ts": "2026-07-11T00:00:00.000Z",
                "u": {"username": "principal"},
                "blocks": [{"callId": "hang-intake", "type": "video_conf_end"}],
            }
            # Critical: intake classifier must accept end before routing
            assert agent.is_videoconf_message(end_msg) is True, (
                "intake is_videoconf_message must be True for videoconf-end"
            )
            assert agent.is_videoconf_end_message(end_msg) is True

            # REAL entry point (not handle_videoconf_call directly)
            agent.handle_principal_message(
                end_msg, "roomH", room_name="dm:principal", room_type="d"
            )

            assert killed_sig, f"SIGTERM must fire via intake; posts={posts}"
            assert killed_sig[0][0] == live_pid
            assert not agent.CALL_LOCK.is_file(), "lock must be released after hangup"
            assert posts, "must post STATUS_ENDED"
            assert "ended" in posts[0].lower()
            assert "transcript" not in posts[0].lower()
            st = agent.load_state()
            assert "vc-end-intake-1" in (st.get("processed_ids") or [])
            # must not enqueue a text wake
            assert not (st.get("pending_wakes") or [])
            SPAWN_EVIDENCE.append(
                f"handle_principal_message(videoconf-end) "
                f"SIGTERM_pid={killed_sig[0][0]} lock_gone=True "
                f"ended_status={posts[0][:60]!r}"
            )

        record("hangup_terminates_and_releases_lock", True)
    except Exception as e:
        record(
            "hangup_terminates_and_releases_lock",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_spawn_python_bin_prefers_venv_with_livekit() -> None:
    """Cutover path: default spawn python must be able to import livekit."""
    try:
        if str(CALL_DIR) not in sys.path:
            sys.path.insert(0, str(CALL_DIR))
        # Fresh load + restore real subprocess (prior test may have stubbed Popen)
        if "rc_operator_agent" in sys.modules:
            del sys.modules["rc_operator_agent"]
        agent = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
        import subprocess as real_sp

        # Ensure global subprocess.Popen is the real one (prior tests may pollute)
        if not isinstance(real_sp.Popen, type):
            # restore from a clean import if needed
            import importlib

            real_sp = importlib.reload(real_sp)
        agent.subprocess = real_sp  # type: ignore

        # Clear PYTHON_BIN so resolver prefers .venv
        old = os.environ.pop("PYTHON_BIN", None)
        try:
            py = agent.resolve_operator_python_bin()
        finally:
            if old is not None:
                os.environ["PYTHON_BIN"] = old
        assert py, "python bin required"
        venv_py = OPS / ".venv" / "bin" / "python3"
        if venv_py.is_file():
            assert Path(py).resolve() == venv_py.resolve() or ".venv" in str(py), py
        # That interpreter imports livekit (Frameworks python3 cannot)
        proc = real_sp.run(
            [py, "-c", "import livekit, websockets; print('ok')"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        fw = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
        if Path(fw).is_file():
            bad = real_sp.run(
                [fw, "-c", "import livekit"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            assert bad.returncode != 0
            SPAWN_EVIDENCE.append("Frameworks python3 cannot import livekit (expected)")
        env = os.environ.copy()
        env["RC_LIVEKIT_URL"] = "wss://test.livekit.cloud"
        env["RC_LIVEKIT_API_KEY"] = "APItest"
        env["RC_LIVEKIT_API_SECRET"] = "secretsecretsecretsecret12"
        proc2 = real_sp.run(
            [
                py,
                str(CALL_DIR / "voice_agent_worker.py"),
                "--call-id",
                "pybin1",
                "--room-id",
                "r1",
                "--validate-only",
            ],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        out2 = (proc2.stdout or "") + (proc2.stderr or "")
        assert proc2.returncode == 0, out2
        assert "No module named livekit" not in out2
        SPAWN_EVIDENCE.append(f"resolve_operator_python_bin={py} livekit_import=ok")
        sh = (WAKE_DIR / "run_operator_agent.sh").read_text(encoding="utf-8")
        assert ".venv/bin/python3" in sh
        vsh = (CALL_DIR / "run_voice_agent.sh").read_text(encoding="utf-8")
        assert ".venv/bin/python3" in vsh
        SPAWN_EVIDENCE.append("run_operator_agent.sh + run_voice_agent.sh prefer .venv")
        with tempfile.TemporaryDirectory(dir=str(SCRATCH)) as td:
            t = Path(td)
            agent.LOG_DIR = t / "logs"
            agent.LOG_DIR.mkdir()
            agent.CALL_LOCK = agent.LOG_DIR / "call-bot.lock"
            agent.LOG_PATH = agent.LOG_DIR / "op.log"
            agent.STATE_PATH = t / "state.json"
            agent.save_state({})
            captured: list[list[str]] = []
            _real_popen = real_sp.Popen

            class FP:
                pid = os.getpid()

            def popen(cmd, **kw):
                captured.append(list(cmd))
                return FP()

            try:
                agent.subprocess.Popen = popen  # type: ignore
                os.environ["RC_CALL_MEDIA_BACKEND"] = "livekit"
                saved = os.environ.pop("PYTHON_BIN", None)
                try:
                    ok = agent.spawn_call_bot("venvspawn1", "r1")
                finally:
                    if saved is not None:
                        os.environ["PYTHON_BIN"] = saved
                assert ok and captured
                assert ".venv" in captured[0][0] or Path(captured[0][0]).resolve() == venv_py.resolve()
                SPAWN_EVIDENCE.append(f"spawn_call_bot python={captured[0][0]}")
            finally:
                real_sp.Popen = _real_popen
                agent.subprocess.Popen = _real_popen  # type: ignore
        record("spawn_python_bin_prefers_venv_with_livekit", True)
    except Exception as e:
        record(
            "spawn_python_bin_prefers_venv_with_livekit",
            False,
            repr(e) + traceback.format_exc(),
        )


def main() -> int:
    tests = [
        test_backend_flag_selection,
        test_call_lock_single_flight,
        test_phone_facing_lan_join_host,
        test_timeout_and_status_config,
        test_livekit_token_and_room,
        test_worker_argv_and_brain_contract,
        test_worker_validate_only_subprocess,
        test_audio_bridge_greeting_and_duplex,
        test_worker_bridge_sim_subprocess,
        test_operator_spawn_livekit_vs_playwright,
        test_hangup_terminates_and_releases_lock,
        test_spawn_python_bin_prefers_venv_with_livekit,
        test_source_contracts_structural,
    ]
    for t in tests:
        t()
    failed = [n for n, s, _ in RESULTS if s == "FAIL"]
    summary = f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed"
    print(summary)

    def dump(path: Path, header: str, evidence: list[str], names: set[str]) -> None:
        lines = [header, ""]
        for n, s, d in RESULTS:
            if n in names:
                lines.append(f"[{s}] {n}" + (f" — {d}" if d else ""))
        lines.append("")
        lines.append("## observations")
        lines.extend(f"- {e}" for e in evidence)
        lines.append("")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    dump(
        SCRATCH / "nf01-unit-backend-lock.out",
        "# NF01 gate1 backend + lock",
        BACKEND_EVIDENCE,
        {
            "backend_flag_selection",
            "call_lock_single_flight",
            "timeout_and_status_config",
        },
    )
    dump(
        SCRATCH / "nf01-unit-token-worker.out",
        "# NF01 gate2 token + worker + audio bridge S2S",
        TOKEN_EVIDENCE,
        {
            "livekit_token_and_room",
            "worker_argv_and_brain_contract",
            "worker_validate_only_subprocess",
            "audio_bridge_greeting_and_duplex",
            "worker_bridge_sim_subprocess",
        },
    )
    dump(
        SCRATCH / "nf01-contract-spawn-lifecycle.out",
        "# NF01 gate3 operator spawn + hangup lifecycle",
        SPAWN_EVIDENCE,
        {
            "operator_spawn_livekit_vs_playwright",
            "hangup_terminates_and_releases_lock",
            "spawn_python_bin_prefers_venv_with_livekit",
            "source_contracts_structural",
        },
    )
    (SCRATCH / "nf01-all-results.out").write_text(
        "\n".join(f"[{s}] {n}" + (f" — {d}" if d else "") for n, s, d in RESULTS)
        + f"\n{summary}\n",
        encoding="utf-8",
    )
    print(f"wrote SCRATCH under {SCRATCH}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
