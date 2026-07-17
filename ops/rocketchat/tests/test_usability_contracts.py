#!/usr/bin/env python3
"""
Usability contract tests for Rocket.Chat ↔ Grok operator.

These exist because unit/integration tests previously passed while the product
still dropped real channel messages. Each test names a failure mode a human
would hit.

Rules:
- Never touch production STATE_PATH or LOCK_DIR.
- Never post to live Rocket.Chat (no rc-int-test spam).
- Mock wake_grok so runs stay fast and deterministic.

Usage:
  python3 ~/.grok/agency/ops/rocketchat/tests/test_usability_contracts.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
from pathlib import Path

WAKE_DIR = Path.home() / ".grok" / "agency" / "ops" / "rocketchat" / "wake"
SCRATCH = Path(tempfile.mkdtemp(prefix="rc-usability-"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(mod)
    return mod


RESULTS: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    RESULTS.append((name, status, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def _isolate_agent(agent, tmp: Path):
    """Point production module globals at a private sandbox."""
    agent.STATE_PATH = tmp / "state.json"
    agent.LOCK_DIR = tmp / "wake.lock.d"
    agent.LOG_DIR = tmp / "logs"
    agent.LOG_PATH = agent.LOG_DIR / "operator-agent.log"
    agent.LOG_DIR.mkdir(parents=True, exist_ok=True)
    agent.save_state({})
    # Parallel drain uses worker threads; join them for deterministic tests.
    os.environ["RC_WAKE_DRAIN_SYNC"] = "1"


def test_no_canned_autoresponse_strings_in_operator() -> None:
    """Regression: canned fast-path strings must not reappear."""
    try:
        src = (WAKE_DIR / "rc_operator_agent.py").read_text(encoding="utf-8")
        banned = [
            "Operator is online (fast path)",
            "pong — online and listening",
            "On it — working on:",
            "Got it in **#",
            "Acknowledged",
        ]
        # Allow mentions only inside comments that say "no canned"
        for b in banned:
            for line in src.splitlines():
                if b not in line:
                    continue
                if "no canned" in line.lower() or "must not" in line.lower():
                    continue
                if line.strip().startswith("#"):
                    continue
                raise AssertionError(f"canned string present: {b!r} in {line!r}")
        record("no_canned_autoresponse_strings", True)
    except Exception as e:
        record("no_canned_autoresponse_strings", False, repr(e))


def _mock_thinking_io(agent, *, reply_body: str = "status ok"):
    """Mock RC post/update + wake that writes the reply file from the prompt."""
    posts: list[tuple[str, str]] = []
    updates: list[tuple[str, str, str]] = []

    def post_thinking(room_id: str, **_kw) -> str:
        from wake_lib import ACTIVITY_PLACEHOLDER

        posts.append((room_id, ACTIVITY_PLACEHOLDER))
        return "think-msg-1"

    def finalize(room_id: str, thinking_msg_id: str, final_body: str, **_kw) -> bool:
        from wake_lib import compose_unified_reply

        updates.append((room_id, thinking_msg_id, compose_unified_reply(final_body)))
        return True

    def fake_wake(prompt, **kwargs):
        # Extract reply file path from prompt inject and write body
        for line in prompt.splitlines():
            if line.startswith("Reply file (write final user-facing answer here): "):
                path = line.split(": ", 1)[1].strip()
                if path and path != "(none)":
                    Path(path).write_text(reply_body, encoding="utf-8")
                break
        return 0, "sess-1"

    agent.post_thinking_placeholder = post_thinking
    agent.finalize_thinking_message = finalize
    agent.update_thinking_meta = lambda *a, **k: True
    agent.wake_grok = fake_wake
    return posts, updates


def test_mark_processed_only_after_wake() -> None:
    """
    FUNDAMENTAL: a principal message must not land in processed_ids until
    wake_grok has been called (the bug that silently dropped channel messages).
    """
    agent = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
    tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
    try:
        _isolate_agent(agent, tmp)
        order: list[str] = []
        seen_processed_before_wake = False

        def fake_wake(prompt, **kwargs):
            st = agent.load_state()
            if "m-status-1" in (st.get("processed_ids") or []):
                nonlocal seen_processed_before_wake
                seen_processed_before_wake = True
            order.append("wake")
            for line in prompt.splitlines():
                if line.startswith("Reply file (write final user-facing answer here): "):
                    path = line.split(": ", 1)[1].strip()
                    if path and path != "(none)":
                        Path(path).write_text("ok", encoding="utf-8")
                    break
            return 0, "sess-1"

        agent.wake_grok = fake_wake
        agent.post_thinking_placeholder = lambda rid, **_k: "t1"
        agent.finalize_thinking_message = lambda *a, **k: True
        agent.force_clear_wake_lock()

        msg = {
            "_id": "m-status-1",
            "rid": "room-pgs",
            "msg": "project status report",
            "ts": "t1",
            "u": {"username": "principal"},
        }
        # Synchronous drain for determinism
        assert agent._enqueue_pending(msg, "room-pgs", "Prime-Gap-Structure", "p")
        st_mid = agent.load_state()
        assert "m-status-1" not in (st_mid.get("processed_ids") or []), st_mid
        assert any(p.get("mid") == "m-status-1" for p in (st_mid.get("pending_wakes") or []))

        agent._drain_pending_wakes()

        st = agent.load_state()
        assert order == ["wake"], order
        assert not seen_processed_before_wake, "processed before wake"
        assert "m-status-1" in (st.get("processed_ids") or [])
        assert not (st.get("pending_wakes") or [])
        record("mark_processed_only_after_wake", True)
    except Exception as e:
        record("mark_processed_only_after_wake", False, repr(e) + traceback.format_exc())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_stuck_lock_does_not_drop_message() -> None:
    """
    FUNDAMENTAL: a pre-existing wake.lock.d must not cause permanent skip.
    Message stays pending until drain can run; force-clear recovers.
    """
    agent = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
    tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
    try:
        _isolate_agent(agent, tmp)
        wakes: list[str] = []

        def fake_wake(prompt, **kwargs):
            wakes.append("ok")
            for line in prompt.splitlines():
                if line.startswith("Reply file (write final user-facing answer here): "):
                    path = line.split(": ", 1)[1].strip()
                    if path and path != "(none)":
                        Path(path).write_text("ok", encoding="utf-8")
                    break
            return 0, "sess-lock"

        agent.wake_grok = fake_wake
        agent.post_thinking_placeholder = lambda rid, **_k: "t-lock"
        agent.finalize_thinking_message = lambda *a, **k: True

        # Plant a stuck lock dir (the production failure mode)
        agent.LOCK_DIR.mkdir(parents=True, exist_ok=True)
        (agent.LOCK_DIR / "holder.pid").write_text("999999", encoding="utf-8")
        # Make it look old so stale reclaim works even without force path
        old = time.time() - 600
        import os

        os.utime(agent.LOCK_DIR, (old, old))

        msg = {
            "_id": "m-lock-1",
            "rid": "room-pgs",
            "msg": "Give me a project status",
            "u": {"username": "principal"},
        }
        assert agent._enqueue_pending(msg, "room-pgs", "Prime-Gap-Structure", "p")
        # Must still be pending, not processed
        st0 = agent.load_state()
        assert "m-lock-1" not in (st0.get("processed_ids") or [])
        assert st0.get("pending_wakes")

        agent._drain_pending_wakes()

        st = agent.load_state()
        assert wakes == ["ok"], wakes
        assert "m-lock-1" in (st.get("processed_ids") or [])
        assert not (st.get("pending_wakes") or [])
        # Legacy base lock cleared; per-room lock released after drain
        assert not (agent.LOCK_DIR / "holder.pid").exists()
        record("stuck_lock_does_not_drop_message", True)
    except Exception as e:
        record("stuck_lock_does_not_drop_message", False, repr(e) + traceback.format_exc())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_enqueue_during_drain_is_not_lost() -> None:
    """
    FUNDAMENTAL: message arriving while drain is finishing must still run
    (empty-queue / unlock race).
    """
    agent = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
    tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
    try:
        _isolate_agent(agent, tmp)
        wakes: list[str] = []
        gate = threading.Event()
        second_enqueued = threading.Event()

        def fake_wake(prompt, **kwargs):
            # During first wake, enqueue a second message
            if not wakes:
                wakes.append("first")
                msg2 = {
                    "_id": "m-race-2",
                    "rid": "room-pgs",
                    "msg": "follow up",
                    "u": {"username": "principal"},
                }
                agent._enqueue_pending(msg2, "room-pgs", "Prime-Gap-Structure", "p")
                second_enqueued.set()
            else:
                wakes.append("second")
            for line in prompt.splitlines():
                if line.startswith("Reply file (write final user-facing answer here): "):
                    path = line.split(": ", 1)[1].strip()
                    if path and path != "(none)":
                        Path(path).write_text("ok", encoding="utf-8")
                    break
            return 0, "sess-race"

        agent.wake_grok = fake_wake
        agent.post_thinking_placeholder = lambda rid, **_k: "t-race"
        agent.finalize_thinking_message = lambda *a, **k: True
        agent.force_clear_wake_lock()

        msg1 = {
            "_id": "m-race-1",
            "rid": "room-pgs",
            "msg": "first",
            "u": {"username": "principal"},
        }
        assert agent._enqueue_pending(msg1, "room-pgs", "Prime-Gap-Structure", "p")
        agent._drain_pending_wakes()
        assert second_enqueued.is_set()
        st = agent.load_state()
        assert "first" in wakes and "second" in wakes, wakes
        assert "m-race-1" in (st.get("processed_ids") or [])
        assert "m-race-2" in (st.get("processed_ids") or [])
        assert not (st.get("pending_wakes") or []), st.get("pending_wakes")
        record("enqueue_during_drain_is_not_lost", True)
    except Exception as e:
        record("enqueue_during_drain_is_not_lost", False, repr(e) + traceback.format_exc())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_resume_and_cwd_in_wake_argv() -> None:
    """Multi-message chat must pass --resume; channels must not default to agency."""
    wl = _load("wake_lib", WAKE_DIR / "wake_lib.py")
    try:
        argv_new = wl.build_wake_argv("/tmp/p", cwd="/proj/pgs", max_turns=5)
        assert "--resume" not in argv_new
        assert "/proj/pgs" in argv_new

        argv_r = wl.build_wake_argv(
            "/tmp/p", cwd="/proj/pgs", max_turns=5, resume_session_id="sid-9"
        )
        assert argv_r[argv_r.index("--resume") + 1] == "sid-9"
        assert "/proj/pgs" in argv_r

        dm, r = wl.resolve_project_cwd("dm:principal", room_type="d")
        assert r == "dm"
        assert ".grok/agency" in str(dm)

        ch, r2 = wl.resolve_project_cwd(
            "Prime-Gap-Structure", room_type="p", create_if_missing=False
        )
        assert r2 in ("map", "existing")
        assert "prime-gap-structure" in str(ch)
        assert ".grok/agency" not in str(ch)

        agency_ch, r3 = wl.resolve_project_cwd(
            "Agency", room_type="p", create_if_missing=False
        )
        # Channel named Agency must NOT force agency spine
        assert r3 != "dm"
        record("resume_and_cwd_in_wake_argv", True, f"agency_ch={agency_ch} ({r3})")
    except Exception as e:
        record("resume_and_cwd_in_wake_argv", False, repr(e) + traceback.format_exc())


def test_approval_modes_imp01() -> None:
    """IMP-01: restricted default, admin opt-in, admin DMs-only for channels."""
    wl = _load("wake_lib", WAKE_DIR / "wake_lib.py")
    try:
        # Explicit restricted argv
        argv_r = wl.build_wake_argv(
            "/tmp/p", cwd="/proj/x", max_turns=3, approval_mode="restricted"
        )
        assert "--always-approve" not in argv_r
        # acceptEdits cancels headless (empty reply file); restricted uses auto
        assert argv_r[argv_r.index("--permission-mode") + 1] == "auto"

        # Explicit admin argv
        argv_a = wl.build_wake_argv(
            "/tmp/p", cwd="/proj/x", max_turns=3, approval_mode="admin"
        )
        assert "--always-approve" in argv_a
        assert "--permission-mode" not in argv_a

        # Env default → restricted
        assert wl.configured_approval_mode_from_env({}) == "restricted"
        assert wl.normalize_approval_mode("full") == "admin"
        assert wl.normalize_approval_mode("weird") == "restricted"

        # Admin + DMs-only: channel forced restricted
        env_admin = {"RC_WAKE_APPROVAL_MODE": "admin", "RC_WAKE_ADMIN_DMS_ONLY": "1"}
        assert (
            wl.resolve_approval_mode(
                room_type="p", room_name="Prime-Gap-Structure", env=env_admin
            )
            == "restricted"
        )
        assert (
            wl.resolve_approval_mode(
                room_type="d", room_name="dm:principal", env=env_admin
            )
            == "admin"
        )

        # Admin on all rooms when DMs-only off
        env_all = {"RC_WAKE_APPROVAL_MODE": "admin", "RC_WAKE_ADMIN_DMS_ONLY": "0"}
        assert (
            wl.resolve_approval_mode(
                room_type="c", room_name="general", env=env_all
            )
            == "admin"
        )

        # Prompt documents modes
        prompt = (WAKE_DIR / "reply_prompt.txt").read_text(encoding="utf-8")
        assert "restricted" in prompt.lower()
        assert "RC_WAKE_APPROVAL_MODE" in prompt
        assert "--permission-mode auto" in prompt or "permission-mode auto" in prompt

        record("approval_modes_imp01", True)
    except Exception as e:
        record("approval_modes_imp01", False, repr(e) + traceback.format_exc())


def test_handle_principal_queues_without_production_paths() -> None:
    """handle_principal_message must use isolated paths and enqueue+drain."""
    agent = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
    tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
    try:
        _isolate_agent(agent, tmp)
        # Ensure we are not pointing at production
        prod_state = Path.home() / ".grok/agency/ops/rocketchat/wake/state.json"
        assert agent.STATE_PATH != prod_state
        prod_lock = Path.home() / "logs/rocketchat-dm-wake/wake.lock.d"
        assert agent.LOCK_DIR != prod_lock

        wakes: list[str] = []

        def fake_wake(prompt, **kwargs):
            wakes.append(kwargs.get("project_cwd") or "")
            for line in prompt.splitlines():
                if line.startswith("Reply file (write final user-facing answer here): "):
                    path = line.split(": ", 1)[1].strip()
                    if path and path != "(none)":
                        Path(path).write_text("ok", encoding="utf-8")
                    break
            return 0, "sess-h"

        agent.wake_grok = fake_wake
        agent.post_thinking_placeholder = lambda rid, **_k: "t-h"
        agent.finalize_thinking_message = lambda *a, **k: True
        agent.force_clear_wake_lock()

        done = threading.Event()
        original_drain = agent._drain_pending_wakes

        def drain_and_signal():
            original_drain()
            done.set()

        agent._drain_pending_wakes = drain_and_signal

        msg = {
            "_id": "m-handle-1",
            "rid": "6a4f9a42b0e299fde39d6a14",
            "msg": "@grok status",
            "u": {"username": "principal"},
        }
        agent.handle_principal_message(
            msg, "6a4f9a42b0e299fde39d6a14", room_name="Prime-Gap-Structure", room_type="p"
        )
        assert done.wait(5), "drain did not finish"
        assert len(wakes) == 1
        assert "prime-gap-structure" in wakes[0] or wakes[0].endswith("prime-gap-structure")
        st = agent.load_state()
        assert "m-handle-1" in (st.get("processed_ids") or [])
        record("handle_principal_queues_isolated", True, f"cwd={wakes[0]}")
    except Exception as e:
        record("handle_principal_queues_isolated", False, repr(e) + traceback.format_exc())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_source_never_marks_before_lock_pattern() -> None:
    """Static guard: no mark-then-skip-wake path; content still enqueues before drain."""
    try:
        src = (WAKE_DIR / "rc_operator_agent.py").read_text(encoding="utf-8")
        # The old bug: mark then "wake lock held — skip"
        assert "wake lock held — skip wake" not in src, "old skip-without-queue path returned"
        start = src.index("def handle_principal_message")
        end = src.index("\nclass OperatorAgent", start)
        body = src[start:end]
        assert "_enqueue_pending" in body
        # Content path must still enqueue then drain (order preserved)
        enq = body.index("_enqueue_pending")
        drain = body.index("_drain_pending_wakes")
        assert enq < drain, "enqueue must precede drain thread start"
        # NF-SPEC-03: control-plane pure commands may mark processed (no wake).
        # That is allowed only via _try_control_plane / command branch, not the
        # content enqueue path immediately before a skip.
        if "_try_control_plane" in body:
            assert "control_plane_enabled" in body or "control_plane" in body
        record("source_never_marks_before_lock_pattern", True)
    except Exception as e:
        record("source_never_marks_before_lock_pattern", False, repr(e))


def test_compose_unified_reply() -> None:
    """Pure helper: final bubble is answer only; placeholders are not kept as prefix."""
    wl = _load("wake_lib", WAKE_DIR / "wake_lib.py")
    try:
        assert wl.compose_unified_reply("hello") == "hello"
        assert wl.compose_unified_reply("Thinking...\n\nalready") == "already"
        assert wl.compose_unified_reply("") == wl.ACTIVITY_PLACEHOLDER
        assert wl.compose_unified_reply("  hi  ") == "hi"
        # Do not strip mid-sentence uses of the word
        assert (
            wl.compose_unified_reply("Thinking... about next steps")
            == "Thinking... about next steps"
        )
        # Thoughts section retained when stream present (RC-safe bold + unicode rule)
        with_t = wl.compose_final_with_thoughts("Answer here", "I am reasoning.")
        assert with_t.startswith(wl.THOUGHTS_SECTION_LABEL)
        assert "I am reasoning." in with_t
        assert wl.THOUGHTS_SECTION_RULE in with_t
        assert len(wl.THOUGHTS_SECTION_RULE) >= 16
        assert not with_t.startswith("##")
        assert with_t.endswith("Answer here")
        # No thoughts → answer only
        assert wl.compose_final_with_thoughts("Only answer", "") == "Only answer"
        record("compose_unified_reply", True)
    except Exception as e:
        record("compose_unified_reply", False, repr(e))


def test_thinking_then_in_place_update_flow() -> None:
    """
    FUNDAMENTAL UX: 👀 ack + one activity bubble finalized with Thoughts + answer
    when thought_text is provided; no second answer post.
    """
    agent = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
    wl = _load("wake_lib", WAKE_DIR / "wake_lib.py")
    tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
    try:
        _isolate_agent(agent, tmp)
        posts: list[tuple[str, str]] = []
        updates: list[tuple[str, str, str]] = []
        acks: list[str] = []

        def post_thinking(room_id: str, **_kw) -> str:
            posts.append((room_id, wl.ACTIVITY_PLACEHOLDER))
            return "msg-thinking-42"

        def finalize(
            room_id: str,
            thinking_msg_id: str,
            final_body: str,
            *,
            thought_text: str = "",
            **_kw,
        ) -> bool:
            text = wl.compose_final_with_thoughts(final_body, thought_text)
            updates.append((room_id, thinking_msg_id, text))
            return True

        def fake_wake(prompt, **kwargs):
            assert "msg-thinking-42" in prompt or "Thinking message id" in prompt or "Activity message id" in prompt
            assert "Do NOT chat.postMessage" in prompt or "Reply file" in prompt
            # Simulate streaming thought into the real callback if present
            on_ev = kwargs.get("on_stream_event")
            if callable(on_ev):
                on_ev({"type": "thought", "data": "Considering the status request."})
            for line in prompt.splitlines():
                if line.startswith("Reply file (write final user-facing answer here): "):
                    path = line.split(": ", 1)[1].strip()
                    Path(path).write_text("Here is the real answer.", encoding="utf-8")
                    break
            return 0, "sess-think"

        agent.post_thinking_placeholder = post_thinking
        agent.finalize_thinking_message = finalize
        agent.update_thinking_meta = lambda *a, **k: True
        agent.schedule_principal_ack = lambda mid, **_k: acks.append(mid)
        agent.wake_grok = fake_wake
        agent.post_as_grok = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("must not post_as_grok second bubble")
        )
        agent.force_clear_wake_lock()
        # Ensure stream path so on_stream_event is passed
        os.environ["RC_WAKE_STREAM"] = "1"

        msg = {
            "_id": "m-think-1",
            "rid": "room-pgs",
            "msg": "status please",
            "u": {"username": "principal"},
        }
        assert agent._enqueue_pending(msg, "room-pgs", "Prime-Gap-Structure", "p")
        agent._drain_pending_wakes()

        assert acks == ["m-think-1"], acks
        assert posts == [("room-pgs", wl.ACTIVITY_PLACEHOLDER)], posts
        assert len(updates) == 1, updates
        rid, mid, text = updates[0]
        assert rid == "room-pgs" and mid == "msg-thinking-42"
        assert wl.THOUGHTS_SECTION_LABEL in text
        assert "Considering the status request." in text
        assert wl.THOUGHTS_SECTION_RULE in text
        assert "Here is the real answer." in text
        assert not text.startswith("##")
        assert not text.startswith("Thinking...")
        record("thinking_then_in_place_update_flow", True)
    except Exception as e:
        record(
            "thinking_then_in_place_update_flow",
            False,
            repr(e) + traceback.format_exc(),
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_thinking_failure_still_updates_placeholder() -> None:
    """If wake fails with empty reply file, still edit Thinking... (not silent forever)."""
    agent = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
    tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
    try:
        _isolate_agent(agent, tmp)
        updates: list[str] = []

        agent.post_thinking_placeholder = lambda rid, **_k: "msg-fail-1"
        agent.finalize_thinking_message = lambda rid, mid, body, **_k: updates.append(body) or True
        agent.wake_grok = lambda prompt, **k: (1, None)  # fail, no reply file write
        agent.update_thinking_meta = lambda rid, mid, body, **_k: True  # meta optional in this test
        agent.write_health_snapshot = lambda **k: None
        agent.force_clear_wake_lock()

        msg = {
            "_id": "m-fail-1",
            "rid": "room-pgs",
            "msg": "do stuff",
            "u": {"username": "principal"},
        }
        agent._enqueue_pending(msg, "room-pgs", "Prime-Gap-Structure", "p")
        agent._drain_pending_wakes()
        assert len(updates) >= 1
        final = updates[-1]
        # NF-SPEC-02 FINAL_ERR or legacy-compatible wording
        assert (
            "Could not complete" in final
            or "rc=1" in final
            or "rc: 1" in final
            or "Wake did not produce" in final
        ), final
        record("thinking_failure_still_updates_placeholder", True)
    except Exception as e:
        record("thinking_failure_still_updates_placeholder", False, repr(e) + traceback.format_exc())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_videoconf_spawns_call_bot() -> None:
    """Call button (t=videoconf) must spawn media bot (Path C), not full text wake."""
    agent = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
    wl = _load("wake_lib", WAKE_DIR / "wake_lib.py")
    tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
    try:
        _isolate_agent(agent, tmp)
        posts: list[str] = []
        agent.post_as_grok = lambda room_id, text: posts.append(text) or True
        wakes: list[str] = []
        agent.wake_grok = lambda prompt, **k: wakes.append(prompt) or (0, None)
        spawned: list[tuple[str, str]] = []
        agent.spawn_call_bot = lambda call_id, room_id, room_name="": (
            spawned.append((call_id, room_id)) or True
        )

        call_msg = {
            "_id": "vc-1",
            "rid": "room-dm",
            "t": "videoconf",
            "msg": "",
            "ts": "2026-07-09T00:00:00.000Z",
            "u": {"username": "principal"},
            "blocks": [
                {
                    "type": "video_conf",
                    "blockId": "call-abc",
                    "callId": "call-abc",
                    "appId": "videoconf-core",
                }
            ],
        }
        assert wl.is_videoconf_message(call_msg) is True
        assert wl.should_handle_dm_message(call_msg) is False  # not a text wake
        agent.handle_principal_message(call_msg, "room-dm", room_name="dm:principal", room_type="d")
        assert spawned == [("call-abc", "room-dm")], f"spawned={spawned}"
        assert posts, "expected answering notice"
        assert "answering" in posts[0].lower() or "hello" in posts[0].lower()
        assert not wakes, "videoconf must not start a full text wake"
        st = agent.load_state()
        assert "vc-1" in (st.get("processed_ids") or [])
        record("videoconf_spawns_call_bot", True)
    except Exception as e:
        record("videoconf_spawns_call_bot", False, repr(e) + traceback.format_exc())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_voice_note_empty_text_is_enqueued() -> None:
    """
    Path A: pure voice note (empty msg + audio file) must enqueue, not silent-drop.

    Previously should_handle required non-empty text, so mobile voice notes
    never woke Grok.
    """
    agent = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
    wl = _load("wake_lib", WAKE_DIR / "wake_lib.py")
    tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
    try:
        _isolate_agent(agent, tmp)
        # Bypass real download/whisper in unit path
        agent.resolve_message_text_for_wake = lambda msg: (
            wl.compose_wake_user_text(
                msg.get("msg") or "",
                transcripts=["please check the week plan"],
            )
        )
        wakes: list[str] = []

        def fake_wake(prompt, **kwargs):
            wakes.append(prompt)
            # Write reply file from prompt inject
            for line in prompt.splitlines():
                if line.startswith("Reply file (write final user-facing answer here): "):
                    path = Path(line.split(": ", 1)[1].strip())
                    path.write_text("Week plan looks on track.", encoding="utf-8")
            return 0, "sess-voice"

        agent.wake_grok = fake_wake
        agent.post_thinking_placeholder = lambda room_id, **_k: "think-voice"
        updates: list[str] = []

        def finalize(room_id, thinking_msg_id, final_body, **_kw):
            updates.append(final_body)
            return True

        agent.finalize_thinking_message = finalize
        agent.update_thinking_meta = lambda *a, **k: True

        voice_msg = {
            "_id": "voice-1",
            "rid": "room-dm",
            "msg": "",
            "ts": "2026-07-09T00:00:00.000Z",
            "u": {"username": "principal"},
            "file": {"_id": "fid1", "name": "Audio.m4a", "type": "audio/mp4"},
        }
        assert wl.should_handle_dm_message(voice_msg) is True
        agent.handle_principal_message(voice_msg, "room-dm", room_name="dm:principal", room_type="d")
        # Drain is async thread — wait briefly
        deadline = time.time() + 5
        while time.time() < deadline and not wakes:
            time.sleep(0.05)
        assert wakes, "wake never ran for voice note"
        assert "please check the week plan" in wakes[0] or "Voice note transcript" in wakes[0]
        deadline = time.time() + 5
        while time.time() < deadline and not updates:
            time.sleep(0.05)
        assert updates, "Thinking... never finalized for voice note"
        record("voice_note_empty_text_is_enqueued", True, f"wakes={len(wakes)}")
    except Exception as e:
        record("voice_note_empty_text_is_enqueued", False, repr(e) + traceback.format_exc())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_live_thinking_update_if_enabled() -> None:
    """
    Opt-in live RC: post Thinking..., chat.update same id, verify success.
    RC_LIVE_THINKING=1 — default SKIP (avoids DM spam).
    """
    import json as J
    import os
    import urllib.request as U

    if os.environ.get("RC_LIVE_THINKING", "").strip() not in ("1", "true", "yes"):
        RESULTS.append(("live_thinking_update", "SKIP", "set RC_LIVE_THINKING=1"))
        print("[SKIP] live_thinking_update — set RC_LIVE_THINKING=1")
        return
    secrets = Path.home() / ".grok/agency/secrets/rocketchat.env"
    if not secrets.is_file():
        RESULTS.append(("live_thinking_update", "SKIP", "no secrets"))
        print("[SKIP] live_thinking_update — no secrets")
        return
    try:
        U.urlopen("http://127.0.0.1:3000/api/info", timeout=3)
    except Exception as e:
        RESULTS.append(("live_thinking_update", "SKIP", f"RC down: {e}"))
        print(f"[SKIP] live_thinking_update — RC down: {e}")
        return
    agent = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
    wl = _load("wake_lib", WAKE_DIR / "wake_lib.py")
    try:
        env = wl.load_env(secrets)
        body = J.dumps(
            {
                "user": env["ROCKETCHAT_OPERATOR_USERNAME"],
                "password": env["ROCKETCHAT_OPERATOR_PASSWORD"],
            }
        ).encode()
        req = U.Request(
            "http://127.0.0.1:3000/api/v1/login",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with U.urlopen(req, timeout=15) as r:
            d = J.loads(r.read().decode())
        token, uid = d["data"]["authToken"], d["data"]["userId"]
        req = U.Request(
            "http://127.0.0.1:3000/api/v1/im.list",
            headers={"X-Auth-Token": token, "X-User-Id": uid},
        )
        with U.urlopen(req, timeout=15) as r:
            ims = J.loads(r.read().decode())
        room = None
        for im in ims.get("ims") or []:
            users = set(im.get("usernames") or [])
            if "principal" in users and "grok" in users:
                room = im["_id"]
                break
        assert room, "principal↔grok DM not found"
        mid = agent.post_message_get_id(room, wl.THINKING_PLACEHOLDER)
        assert mid, "post Thinking failed"
        ok = agent.update_message(
            room, mid, wl.compose_unified_reply("Live probe: in-place update works.")
        )
        assert ok, "chat.update failed"
        record("live_thinking_update", True, f"room={room} mid={mid}")
    except Exception as e:
        record("live_thinking_update", False, repr(e) + traceback.format_exc())



def test_imp_batch_helpers() -> None:
    """IMP-02/03/07/08/09/14/19: shipped helpers on real wake_lib / config / prompt."""
    wl = _load("wake_lib", WAKE_DIR / "wake_lib.py")
    try:
        # IMP-02 defaults consistent
        assert wl.wake_timeout_and_lock_stale_are_consistent()
        assert wl.DEFAULT_WAKE_LOCK_STALE_S > wl.DEFAULT_WAKE_TIMEOUT_S

        tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
        lock = tmp / "lock"
        assert wl.acquire_wake_lock(lock) is True
        # live pid cannot be stolen even with stale_after=0
        assert wl.acquire_wake_lock(lock, stale_after_s=0) is False
        # dead pid can be reclaimed
        (lock / "holder.pid").write_text("99999999", encoding="utf-8")
        os.utime(lock, (time.time() - 10_000, time.time() - 10_000))
        assert wl.acquire_wake_lock(lock, stale_after_s=1) is True
        wl.release_wake_lock(lock)

        # IMP-09
        assert wl.DEFAULT_WAKE_MAX_TURNS == "100"
        argv = wl.build_wake_argv("/tmp/p", max_turns=None, approval_mode="restricted")
        assert argv[argv.index("--max-turns") + 1] == "100" or os.environ.get("RC_WAKE_MAX_TURNS")

        # IMP-07 prompt
        prompt = (WAKE_DIR / "reply_prompt.txt").read_text(encoding="utf-8")
        assert "rocketchat.env" not in prompt or "Do not" in prompt
        assert "Load secrets only" not in prompt
        assert "Do not" in prompt and "secrets" in prompt.lower()

        # IMP-08 prune
        old = tmp / "wake-prompt-old.txt"
        old.write_text("x", encoding="utf-8")
        os.utime(old, (time.time() - 10 * 86400, time.time() - 10 * 86400))
        ledger = tmp / "media-post-ledger.json"
        ledger.write_text("{}", encoding="utf-8")
        removed = wl.prune_log_artifacts(tmp, max_age_s=7 * 86400, dry_run=False)
        assert old in removed or not old.exists()
        assert ledger.exists()

        # IMP-14 migrate
        v1 = {
            "room_id": "r1",
            "last_seen_id": "m1",
            "grok_sessions": {"r1": "s1", "r2": "s2"},
            "grok_cwds": {"r1": "/tmp/a"},
            "processed_ids": ["a", "b"],
            "pending_wakes": [],
        }
        v2 = wl.migrate_state_to_v2(v1)
        assert v2["version"] == 2
        assert v2["rooms"]["r1"]["session_id"] == "s1"
        assert v2["processed_ids"] == ["a", "b"]
        v2b = wl.migrate_state_to_v2(v2)
        assert v2b["rooms"]["r1"]["session_id"] == "s1"

        # Auto-create default ON; kill switch RC_AUTO_CREATE_PROJECTS=0
        assert wl.auto_create_projects_from_env({}) is True
        assert wl.auto_create_projects_from_env({"RC_AUTO_CREATE_PROJECTS": "1"}) is True
        assert wl.auto_create_projects_from_env({"RC_AUTO_CREATE_PROJECTS": "0"}) is False
        fake_ideas = tmp / "ideas"
        fake_ideas.mkdir()
        # Explicit create_if_missing=False still refuses to mkdir (kill-switch path)
        path, reason = wl.resolve_project_cwd(
            "Brand-New-Never-Exists-XYZ",
            room_type="c",
            idea_projects=fake_ideas,
            create_if_missing=False,
        )
        assert reason == "no_create"
        assert not (fake_ideas / "brand-new-never-exists-xyz").exists()
        # Default auto-create creates the project dir
        path2, reason2 = wl.resolve_project_cwd(
            "Brand-New-Auto-Create-ABC",
            room_type="c",
            idea_projects=fake_ideas,
            create_if_missing=True,
        )
        assert reason2 == "created"
        assert path2.is_dir()
        assert (fake_ideas / "brand-new-auto-create-abc").is_dir()

        # IMP-03 config loader (register module before exec for dataclasses)
        import importlib.util
        import sys as _sys

        cfg_path = WAKE_DIR / "rc_config.py"
        spec = importlib.util.spec_from_file_location("rc_config", cfg_path)
        rc_config = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        _sys.modules["rc_config"] = rc_config
        spec.loader.exec_module(rc_config)
        # missing secrets path
        os.environ["RC_SECRETS_PATH"] = str(tmp / "nope.env")
        try:
            try:
                rc_config.load_rc_config(require_secrets=True)
                raise AssertionError("expected FileNotFoundError")
            except FileNotFoundError:
                pass
        finally:
            os.environ.pop("RC_SECRETS_PATH", None)

        # IMP-10 helpers
        rlock = wl.room_wake_lock_dir(tmp / "base", "room/with spaces")
        assert "rooms" in str(rlock)
        assert wl.max_concurrent_wakes_from_env({}) == 16
        assert wl.max_concurrent_wakes_from_env({"RC_WAKE_MAX_CONCURRENT": "2"}) == 2
        assert wl.max_concurrent_wakes_from_env({"RC_WAKE_MAX_CONCURRENT": "1"}) == 1
        # Cross-room pick skips busy head
        idx = wl.pick_next_pending_index_for_free_room(
            [
                {"rid": "room-a", "mid": "1"},
                {"rid": "room-b", "mid": "2"},
                {"rid": "room-a", "mid": "3"},
            ],
            busy_room_ids={"room-a"},
        )
        assert idx == 1
        assert (
            wl.pick_next_pending_index_for_free_room(
                [{"rid": "room-a", "mid": "1"}],
                busy_room_ids={"room-a"},
            )
            is None
        )

        record("imp_batch_helpers", True)
    except Exception as e:
        record("imp_batch_helpers", False, repr(e) + traceback.format_exc())


def test_imp03_config_wired_and_examples() -> None:
    """IMP-03: production entrypoints call load_rc_config; example configs exist."""
    try:
        root = WAKE_DIR.parent
        # Example placeholders ship with the stack
        assert (root / "config.example").is_file()
        assert (root / ".env.example").is_file()
        assert "CHANGE_ME" in (root / "config.example").read_text(encoding="utf-8")
        assert "RC_BASE" in (root / "config.example").read_text(encoding="utf-8")

        # Operator wires apply_runtime_config → load_rc_config (source + callable)
        agent_src = (WAKE_DIR / "rc_operator_agent.py").read_text(encoding="utf-8")
        assert "def apply_runtime_config" in agent_src
        assert "load_rc_config" in agent_src
        assert "apply_runtime_config" in agent_src
        assert "validate_config_startup" in agent_src
        # main must call apply
        main_idx = agent_src.index("def main()")
        assert "apply_runtime_config" in agent_src[main_idx : main_idx + 800]

        media_src = (WAKE_DIR / "rc_post_media.py").read_text(encoding="utf-8")
        assert "apply_media_config" in media_src
        assert "load_rc_config" in media_src
        assert "ROCKETCHAT_OPERATOR_TOKEN" in media_src

        call_src = (
            WAKE_DIR.parent / "call" / "rc_call_bot.py"
        ).read_text(encoding="utf-8")
        assert "apply_call_config" in call_src
        assert "load_rc_config" in call_src

        # Drive real load_rc_config with temp secrets (no live RC required)
        import importlib.util
        import sys as _sys

        tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
        secrets = tmp / "rocketchat.env"
        secrets.write_text(
            "ROCKETCHAT_OPERATOR_USERNAME=grok\n"
            "ROCKETCHAT_OPERATOR_PASSWORD=test-pass-not-real\n"
            "ROCKETCHAT_ROOT_URL=http://127.0.0.1:3000\n",
            encoding="utf-8",
        )
        os.environ["RC_SECRETS_PATH"] = str(secrets)
        os.environ["RC_BASE"] = "http://127.0.0.1:3000"
        try:
            spec = importlib.util.spec_from_file_location(
                "rc_config_wire", WAKE_DIR / "rc_config.py"
            )
            mod = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            _sys.modules["rc_config_wire"] = mod
            # rc_config imports wake_lib by name — ensure path
            _sys.path.insert(0, str(WAKE_DIR))
            spec.loader.exec_module(mod)
            cfg = mod.load_rc_config(require_secrets=True)
            assert cfg.secrets_path == secrets.resolve() or cfg.secrets_path == secrets
            assert cfg.rc_base.startswith("http")
            problems = mod.validate_config_startup(cfg, check_rc=False)
            assert problems == [], problems
            # token helper
            assert mod.token_pair_from_secrets(cfg.secrets) is None
            tok_secrets = {
                "ROCKETCHAT_OPERATOR_TOKEN": "tok-abc",
                "ROCKETCHAT_OPERATOR_USER_ID": "uid-xyz",
            }
            assert mod.token_pair_from_secrets(tok_secrets) == ("tok-abc", "uid-xyz")
        finally:
            os.environ.pop("RC_SECRETS_PATH", None)

        record("imp03_config_wired_and_examples", True)
    except Exception as e:
        record(
            "imp03_config_wired_and_examples",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_imp11_templates_exist() -> None:
    """IMP-11: launchd templates on disk and install script references them."""
    try:
        root = WAKE_DIR.parent
        tmpl_dir = root / "templates"
        op = tmpl_dir / "com.velocityworks.rocketchat-operator.plist.tmpl"
        ng = tmpl_dir / "com.velocityworks.ngrok-rocketchat.plist.tmpl"
        assert op.is_file(), op
        assert ng.is_file(), ng
        body = op.read_text(encoding="utf-8")
        assert "@HOME@" in body and "@ROOT@" in body and "@PYTHON_BIN@" in body
        assert "RC_WAKE_APPROVAL_MODE" in body
        installer = (root / "install-launchd.sh").read_text(encoding="utf-8")
        assert "plist.tmpl" in installer or "templates/" in installer
        assert "render_from_template" in installer
        # Both operator and ngrok use templates (not operator-only)
        assert "com.velocityworks.ngrok-rocketchat.plist.tmpl" in installer
        assert installer.count("render_from_template") >= 1
        assert "NG_TMPL" in installer or "ngrok-rocketchat.plist.tmpl" in installer
        record("imp11_templates_exist", True)
    except Exception as e:
        record("imp11_templates_exist", False, repr(e) + traceback.format_exc())


def test_imp20_pgs_token_auth_path() -> None:
    """IMP-20: PGS notify + media login prefer token; password login not called."""
    try:
        pgs = (
            Path.home()
            / "IdeaProjects"
            / "prime-gap-structure"
            / "scripts"
            / "pgs_hourly_rocketchat_notify.py"
        )
        assert pgs.is_file(), pgs
        import importlib.util
        import sys as _sys

        spec = importlib.util.spec_from_file_location("pgs_rc_notify", pgs)
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        _sys.modules["pgs_rc_notify"] = mod
        spec.loader.exec_module(mod)
        assert hasattr(mod, "resolve_operator_auth")

        # Token path: no network; rest_login must not be required
        login_calls: list[tuple] = []

        def boom_login(base, user, password):
            login_calls.append((base, user, password))
            raise AssertionError("password login must not run when token set")

        # Patch rest_login on the shipped module
        orig = mod.rest_login
        mod.rest_login = boom_login  # type: ignore[method-assign]
        try:
            tok, uid = mod.resolve_operator_auth(
                "http://127.0.0.1:3000",
                {
                    "ROCKETCHAT_OPERATOR_TOKEN": "pat-token",
                    "ROCKETCHAT_OPERATOR_USER_ID": "user-id-1",
                    "ROCKETCHAT_OPERATOR_PASSWORD": "should-not-use",
                },
            )
            assert tok == "pat-token" and uid == "user-id-1"
            assert login_calls == []
        finally:
            mod.rest_login = orig  # type: ignore[method-assign]

        # Password fallback path invokes rest_login exactly once (mocked)
        def fake_login(base, user, password):
            login_calls.append((base, user, password))
            return "tok-pw", "uid-pw"

        login_calls.clear()
        mod.rest_login = fake_login  # type: ignore[method-assign]
        try:
            tok, uid = mod.resolve_operator_auth(
                "http://127.0.0.1:3000",
                {
                    "ROCKETCHAT_OPERATOR_USERNAME": "grok",
                    "ROCKETCHAT_OPERATOR_PASSWORD": "secret",
                },
            )
            assert (tok, uid) == ("tok-pw", "uid-pw")
            assert len(login_calls) == 1
        finally:
            mod.rest_login = orig  # type: ignore[method-assign]

        # Media poster token-only login() — real shipped function, no network
        media = _load("rc_post_media", WAKE_DIR / "rc_post_media.py")
        tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
        secrets = tmp / "s.env"
        secrets.write_text(
            "ROCKETCHAT_OPERATOR_TOKEN=media-tok\n"
            "ROCKETCHAT_OPERATOR_USER_ID=media-uid\n"
            "ROCKETCHAT_OPERATOR_PASSWORD=unused\n",
            encoding="utf-8",
        )
        media.SECRETS = secrets
        media.BASE_HTTP = "http://127.0.0.1:9"  # would fail if password path hit network

        def media_cfg_noop():
            return None

        media.apply_media_config = media_cfg_noop  # type: ignore[method-assign]
        t, u = media.login()
        assert (t, u) == ("media-tok", "media-uid")

        try:
            mod.resolve_operator_auth(
                "http://127.0.0.1:3000", {"ROCKETCHAT_OPERATOR_USERNAME": "grok"}
            )
            raise AssertionError("expected error without password or token")
        except (RuntimeError, KeyError):
            pass
        record("imp20_pgs_token_auth_path", True)
    except Exception as e:
        record("imp20_pgs_token_auth_path", False, repr(e) + traceback.format_exc())


def test_imp05_auth_cache_and_401_retry() -> None:
    """IMP-05: drive shipped _operator_auth + _rest_with_auth_retry (mocked HTTP)."""
    agent = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
    tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
    try:
        secrets = tmp / "s.env"
        secrets.write_text(
            "ROCKETCHAT_OPERATOR_USERNAME=grok\n"
            "ROCKETCHAT_OPERATOR_PASSWORD=pw\n",
            encoding="utf-8",
        )
        agent.SECRETS = secrets
        agent.clear_operator_auth_cache()
        agent._auth_login_count = 0

        logins: list[tuple[str, str]] = []

        def fake_rest_login(user: str, password: str):
            logins.append((user, password))
            return f"tok-{len(logins)}", f"uid-{len(logins)}"

        agent.rest_login = fake_rest_login  # type: ignore[method-assign]

        t1, u1 = agent._operator_auth()
        t2, u2 = agent._operator_auth()
        assert (t1, u1) == (t2, u2) == ("tok-1", "uid-1")
        assert len(logins) == 1, f"expected single login, got {logins}"

        # force_refresh performs a second login
        t3, u3 = agent._operator_auth(force_refresh=True)
        assert (t3, u3) == ("tok-2", "uid-2")
        assert len(logins) == 2

        # 401 path: first http_api raises HTTPError 401, second succeeds
        agent.clear_operator_auth_cache()
        agent._auth_login_count = 0
        logins.clear()
        agent.rest_login = fake_rest_login  # type: ignore[method-assign]

        calls: list[str] = []

        def fake_http(method, path, token=None, uid=None, body=None):
            calls.append(f"{method}:{path}:{token}")
            if len(calls) == 1:
                from io import BytesIO

                raise urllib.error.HTTPError(
                    url=path,
                    code=401,
                    msg="Unauthorized",
                    hdrs=None,
                    fp=BytesIO(b""),
                )
            return {"success": True, "message": {"_id": "mid-1"}}

        agent.http_api = fake_http  # type: ignore[method-assign]
        d = agent._rest_with_auth_retry("POST", "/api/v1/chat.postMessage", {"roomId": "r"})
        assert d.get("success") is True
        assert len(logins) == 2  # initial + re-login after 401
        assert len(calls) == 2
        assert calls[0].endswith("tok-1") or "tok-1" in calls[0]
        assert "tok-2" in calls[1]
        record("imp05_auth_cache_and_401_retry", True, f"logins={len(logins)} calls={calls}")
    except Exception as e:
        record(
            "imp05_auth_cache_and_401_retry",
            False,
            repr(e) + traceback.format_exc(),
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_imp12_health_check_script() -> None:
    """IMP-12: shipped rc_health_check.sh exit codes for fresh/stale health.json."""
    try:
        script = WAKE_DIR.parent / "scripts" / "rc_health_check.sh"
        assert script.is_file(), script
        tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
        health = tmp / "health.json"
        # Fresh + connected
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        health.write_text(
            json.dumps({"ts": now, "ws_connected": True, "pid": 1}),
            encoding="utf-8",
        )
        env = {**os.environ, "RC_HEALTH_PATH": str(health), "RC_HEALTH_MAX_AGE_S": "120"}
        r = subprocess.run(
            ["bash", str(script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)

        # Stale timestamp
        health.write_text(
            json.dumps(
                {
                    "ts": "2020-01-01T00:00:00+00:00",
                    "ws_connected": True,
                    "pid": 1,
                }
            ),
            encoding="utf-8",
        )
        r2 = subprocess.run(
            ["bash", str(script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert r2.returncode != 0, "stale health must fail"

        # Connected false
        health.write_text(
            json.dumps({"ts": now, "ws_connected": False, "pid": 1}),
            encoding="utf-8",
        )
        r3 = subprocess.run(
            ["bash", str(script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert r3.returncode != 0, "ws_connected=false must fail"

        # Python helper on agent matches
        agent = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
        agent.HEALTH_PATH = health
        health.write_text(
            json.dumps({"ts": now, "ws_connected": True}), encoding="utf-8"
        )
        assert agent.health_check_ok(max_age_s=120) is True
        health.write_text(
            json.dumps({"ts": "2020-01-01T00:00:00+00:00", "ws_connected": True}),
            encoding="utf-8",
        )
        assert agent.health_check_ok(max_age_s=120) is False

        record("imp12_health_check_script", True)
    except Exception as e:
        record("imp12_health_check_script", False, repr(e) + traceback.format_exc())


def test_imp04_docker_health_structural() -> None:
    """IMP-04: compose healthcheck uses node (not curl); optional live docker status."""
    try:
        compose = (WAKE_DIR.parent / "docker-compose.yml").read_text(encoding="utf-8")
        assert "curl" not in compose.split("healthcheck:")[1].split("volumes:")[0] or "node" in compose
        assert "node -e" in compose or 'require("http")' in compose or "require('http')" in compose
        # Live evidence file written by ops if docker available
        evidence = Path(
            os.environ.get(
                "RC_DOCKER_HEALTH_EVIDENCE",
                "/var/folders/k_/spz3zlj566sc4qh29g0tk6jh0000gn/T/grok-goal-0cb2f9c97307/implementer/docker_health_inspect.txt",
            )
        )
        if evidence.is_file():
            text = evidence.read_text(encoding="utf-8")
            assert "health=healthy" in text or "healthy" in text
            assert "127.0.0.1:3000" in text or "3000" in text
        record("imp04_docker_health_structural", True, f"evidence={evidence.is_file()}")
    except Exception as e:
        record("imp04_docker_health_structural", False, repr(e) + traceback.format_exc())


def test_imp15_compose_secrets_dry() -> None:
    """
    IMP-15: drive shipped generate_compose_env.sh + backup_mongo.sh + docs links.

    T1 generate .env from secrets (mode 600, ROOT_URL match, password not on stdout)
    T2 mongo volume backup produces non-empty artifact
    T3 operations.md + filesystem-map mention backup/generate + upgrade path
    """
    try:
        root = WAKE_DIR.parent
        gen = root / "scripts" / "generate_compose_env.sh"
        bak = root / "scripts" / "backup_mongo.sh"
        assert gen.is_file() and os.access(gen, os.X_OK), gen
        assert bak.is_file() and os.access(bak, os.X_OK), bak

        tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
        secrets = tmp / "rocketchat.env"
        root_url = "https://imp15-test.ngrok-free.dev"
        admin_pass = "Imp15TestSecret-DoNotEcho"
        secrets.write_text(
            f"ROCKETCHAT_ROOT_URL={root_url}\n"
            f"ROCKETCHAT_PUBLIC_URL={root_url}\n"
            "ROCKETCHAT_ADMIN_USERNAME=principal\n"
            f"ROCKETCHAT_ADMIN_PASSWORD={admin_pass}\n"
            "ROCKETCHAT_ADMIN_EMAIL=principal@localhost.local\n",
            encoding="utf-8",
        )
        out_env = tmp / "compose.env"
        env = {**os.environ, "RC_SECRETS_PATH": str(secrets)}
        # T1
        r1 = subprocess.run(
            ["bash", str(gen), str(out_env)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert r1.returncode == 0, (r1.returncode, r1.stdout, r1.stderr)
        assert admin_pass not in (r1.stdout or "")
        assert admin_pass not in (r1.stderr or "")
        assert out_env.is_file()
        mode = out_env.stat().st_mode & 0o777
        assert mode == 0o600, f"expected mode 600, got {oct(mode)}"
        body = out_env.read_text(encoding="utf-8")
        assert f"ROOT_URL={root_url}" in body
        assert f"ADMIN_PASS={admin_pass}" in body  # file may hold secret; stdout must not
        assert "RC_PORT_BIND=127.0.0.1" in body

        # T2 — live docker volume (fail if missing; do not soft-skip Done)
        dest = tmp / "mongo-backup.tar.gz"
        r2 = subprocess.run(
            ["bash", str(bak), str(dest)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert r2.returncode == 0, (r2.returncode, r2.stdout, r2.stderr)
        assert dest.is_file(), dest
        assert dest.stat().st_size > 0, "backup artifact empty"
        assert "no mongodb volume found" not in (r2.stderr or "")

        # T3 — docs link backup/generate + upgrade steps
        docs = Path.home() / "IdeaProjects" / "rocketchat-grok-docs" / "docs"
        ops = (docs / "operations.md").read_text(encoding="utf-8")
        fsmap = (docs / "filesystem-map.md").read_text(encoding="utf-8")
        for label, text in (("operations.md", ops), ("filesystem-map.md", fsmap)):
            assert "backup_mongo.sh" in text, f"{label} missing backup_mongo.sh"
            assert "generate_compose_env.sh" in text, f"{label} missing generate_compose_env.sh"
        # Upgrade path: backup → pin/image → smoke
        assert "backup" in ops.lower()
        assert "upgrade" in ops.lower() or "pin" in ops.lower()
        assert "smoke" in ops.lower() or "/api/info" in ops

        record(
            "imp15_compose_secrets_dry",
            True,
            f"env_mode={oct(mode)} backup_bytes={dest.stat().st_size}",
        )
    except Exception as e:
        record(
            "imp15_compose_secrets_dry",
            False,
            repr(e) + traceback.format_exc(),
        )

def main() -> int:
    print("=== Rocket.Chat usability contract tests ===")
    print(f"SCRATCH={SCRATCH} (isolated; production state untouched)")
    test_no_canned_autoresponse_strings_in_operator()
    test_mark_processed_only_after_wake()
    test_stuck_lock_does_not_drop_message()
    test_enqueue_during_drain_is_not_lost()
    test_resume_and_cwd_in_wake_argv()
    test_approval_modes_imp01()
    test_imp_batch_helpers()
    test_imp03_config_wired_and_examples()
    test_imp11_templates_exist()
    test_imp20_pgs_token_auth_path()
    test_imp05_auth_cache_and_401_retry()
    test_imp12_health_check_script()
    test_imp04_docker_health_structural()
    test_imp15_compose_secrets_dry()
    test_handle_principal_queues_without_production_paths()
    test_videoconf_spawns_call_bot()
    test_voice_note_empty_text_is_enqueued()
    test_source_never_marks_before_lock_pattern()
    test_compose_unified_reply()
    test_thinking_then_in_place_update_flow()
    test_thinking_failure_still_updates_placeholder()
    test_live_thinking_update_if_enabled()

    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    failed = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    skipped = sum(1 for _, s, _ in RESULTS if s == "SKIP")
    print(f"\n=== SUMMARY passed={passed} failed={failed} skipped={skipped} ===")
    for n, s, d in RESULTS:
        print(f"  {s:4} {n}" + (f" ({d[:120]})" if d else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
