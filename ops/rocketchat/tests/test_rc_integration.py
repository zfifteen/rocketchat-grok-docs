#!/usr/bin/env python3
"""
Rocket.Chat ↔ Grok operator integration tests.

Exercises production helpers in ops/rocketchat/wake/ (not re-implementations).

Usage (from any cwd):
  python3 ~/.grok/agency/ops/rocketchat/tests/test_rc_integration.py

Optional live smoke when RC is up on 127.0.0.1:3000.
Does not print secrets.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import traceback
import urllib.error
import urllib.request
from pathlib import Path

WAKE_DIR = Path.home() / ".grok" / "agency" / "ops" / "rocketchat" / "wake"
SECRETS = Path.home() / ".grok" / "agency" / "secrets" / "rocketchat.env"
SCRATCH = Path(
    os.environ.get(
        "RC_TEST_SCRATCH",
        "/var/folders/k_/spz3zlj566sc4qh29g0tk6jh0000gn/T/grok-goal-d2e38be0c8ac/implementer",
    )
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # ensure wake_lib importable as sibling
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(mod)
    return mod


RESULTS: list[tuple[str, str, str]] = []  # name, PASS|FAIL|SKIP, detail


def record(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    RESULTS.append((name, status, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def record_skip(name: str, detail: str) -> None:
    RESULTS.append((name, "SKIP", detail))
    print(f"[SKIP] {name} — {detail}")


def test_load_env_and_missing() -> None:
    wl = _load_module("wake_lib", WAKE_DIR / "wake_lib.py")
    tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
    try:
        p = tmp / "s.env"
        p.write_text("# c\nFOO=bar\nEMPTY=\nBADLINE\nQUOTED=\"x y\"\n", encoding="utf-8")
        env = wl.load_env(p)
        assert env["FOO"] == "bar"
        assert env["QUOTED"] == "x y"
        try:
            wl.load_env(tmp / "nope.env")
            raise AssertionError("expected FileNotFoundError")
        except FileNotFoundError as e:
            assert "missing secrets" in str(e)
        record("load_env_ok_and_missing_raises", True)
    except Exception as e:
        record("load_env_ok_and_missing_raises", False, repr(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_new_principal_messages_edges() -> None:
    wl = _load_module("wake_lib", WAKE_DIR / "wake_lib.py")
    msgs = [
        {"_id": "1", "ts": "t1", "u": {"username": "principal"}, "msg": "a"},
        {"_id": "2", "ts": "t2", "u": {"username": "grok"}, "msg": "reply"},
        {"_id": "3", "ts": "t3", "u": {"username": "principal"}, "msg": "b"},
        {"_id": "4", "ts": "t4", "u": {"username": "principal"}, "msg": "   "},
        {"_id": "5", "ts": "t5", "u": {"username": "principal"}, "msg": "c"},
    ]
    try:
        assert wl.new_principal_messages([], "1") == []
        assert wl.new_principal_messages(msgs, None) == []
        # after seed id 1: principal b and c (not empty, not grok)
        got = wl.new_principal_messages(msgs, "1")
        assert [m["_id"] for m in got] == ["3", "5"], got
        # after 3: only c
        got2 = wl.new_principal_messages(msgs, "3")
        assert [m["_id"] for m in got2] == ["5"]
        # after latest: empty
        assert wl.new_principal_messages(msgs, "5") == []
        # ignore grok-only window
        only_g = [
            {"_id": "g1", "ts": "t1", "u": {"username": "grok"}, "msg": "hi"},
            {"_id": "g2", "ts": "t2", "u": {"username": "grok"}, "msg": "there"},
        ]
        assert wl.new_principal_messages(only_g, "g1") == []
        record("new_principal_messages_edges", True)
    except Exception as e:
        record("new_principal_messages_edges", False, repr(e) + traceback.format_exc())


def test_seed_helper() -> None:
    wl = _load_module("wake_lib", WAKE_DIR / "wake_lib.py")
    try:
        assert wl.seed_state_from_messages([], "room") is None
        msgs = [
            {"_id": "old", "ts": "t0", "u": {"username": "principal"}, "msg": "x"},
            {"_id": "new", "ts": "t1", "u": {"username": "principal"}, "msg": "y"},
        ]
        st = wl.seed_state_from_messages(msgs, "roomX")
        assert st is not None
        assert st["last_seen_id"] == "new"
        assert st["last_wake_at"] is None
        assert st["room_id"] == "roomX"
        assert "seeded_at" in st
        assert wl.new_principal_messages(msgs, st["last_seen_id"]) == []
        # API newest-first order (operator agent path)
        api_order = list(reversed(msgs))
        st2 = wl.seed_state_from_messages(api_order, "roomY", newest_first=True)
        assert st2 is not None and st2["last_seen_id"] == "new"
        record("seed_helper", True)
    except Exception as e:
        record("seed_helper", False, repr(e))


def test_poll_once_seed_without_wake() -> None:
    """Drive shipped poll_once first-run seed branch; wake_grok must not run."""
    poll = _load_module("rc_dm_poll", WAKE_DIR / "rc_dm_poll.py")
    tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
    secrets_file = tmp / "rocketchat.env"
    secrets_file.write_text(
        "ROCKETCHAT_OPERATOR_USERNAME=grok\nROCKETCHAT_OPERATOR_PASSWORD=test-pass\n",
        encoding="utf-8",
    )
    wake_calls: list[str] = []
    msgs = [
        {"_id": "m-old", "ts": "t0", "u": {"username": "principal"}, "msg": "hello"},
        {"_id": "m-new", "ts": "t1", "u": {"username": "principal"}, "msg": "world"},
    ]
    old = {
        "SECRETS": poll.SECRETS,
        "STATE_PATH": poll.STATE_PATH,
        "LOCK_DIR": poll.LOCK_DIR,
        "login": poll.login,
        "principal_dm_room": poll.principal_dm_room,
        "fetch_history": poll.fetch_history,
        "wake_grok": poll.wake_grok,
        "notify_macos": poll.notify_macos,
    }
    try:
        poll.SECRETS = secrets_file
        poll.STATE_PATH = tmp / "state.json"
        poll.LOCK_DIR = tmp / "wake.lock.d"
        poll.login = lambda u, p: ("tok", "uid")
        poll.principal_dm_room = lambda t, u: "room-seed"
        poll.fetch_history = lambda t, u, r, count=25: list(msgs)
        def _fake_wake(prompt, **kwargs):
            wake_calls.append(prompt)
            return 0, "test-session-id"

        poll.wake_grok = _fake_wake
        poll.notify_macos = lambda *a, **k: None

        rc = poll.poll_once()
        assert rc == 0, rc
        assert wake_calls == [], f"seed must not wake: {wake_calls}"
        st = poll.load_state()
        assert st.get("last_seen_id") == "m-new", st
        assert st.get("last_wake_at") is None, st
        assert st.get("room_id") == "room-seed"

        # second poll same history: still no wake
        rc2 = poll.poll_once()
        assert rc2 == 0
        assert wake_calls == []

        # new principal message after seed → would wake
        msgs2 = msgs + [
            {"_id": "m-3", "ts": "t2", "u": {"username": "principal"}, "msg": "ping"},
        ]
        poll.fetch_history = lambda t, u, r, count=25: list(msgs2)
        rc3 = poll.poll_once()
        assert rc3 == 0
        assert len(wake_calls) == 1, wake_calls
        st3 = poll.load_state()
        assert st3.get("last_seen_id") == "m-3"
        record("poll_once_seed_without_wake", True, f"wake_calls={len(wake_calls)}")
    except Exception as e:
        record("poll_once_seed_without_wake", False, repr(e) + traceback.format_exc())
    finally:
        for k, v in old.items():
            setattr(poll, k, v)
        shutil.rmtree(tmp, ignore_errors=True)


def test_agent_state_and_lock_paths() -> None:
    """Exercise operator-agent load_state/save_state/acquire_wake_lock (shipped wrappers → wake_lib)."""
    agent = _load_module("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
    tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
    old_state, old_lock = agent.STATE_PATH, agent.LOCK_DIR
    try:
        agent.STATE_PATH = tmp / "agent-state.json"
        agent.LOCK_DIR = tmp / "agent.lock.d"
        empty = agent.load_state()
        assert empty.get("version") == 2
        assert not empty.get("last_seen_id")
        agent.save_state({"last_seen_id": "seeded-by-agent", "last_wake_at": None})
        st = agent.load_state()
        assert st["last_seen_id"] == "seeded-by-agent"
        assert st.get("version") == 2
        assert agent.acquire_wake_lock() is True
        assert agent.acquire_wake_lock() is False
        agent.release_wake_lock()
        assert agent.acquire_wake_lock() is True
        agent.release_wake_lock()
        import inspect

        src_load = inspect.getsource(agent.load_state)
        src_acq = inspect.getsource(agent.acquire_wake_lock)
        assert "_lib_load_state" in src_load
        assert "_lib_acquire" in src_acq
        assert "LOCK_DIR.mkdir()" not in src_acq
        record("agent_state_and_lock_paths", True)
    except Exception as e:
        record("agent_state_and_lock_paths", False, repr(e) + traceback.format_exc())
    finally:
        agent.STATE_PATH = old_state
        agent.LOCK_DIR = old_lock
        shutil.rmtree(tmp, ignore_errors=True)


def test_agent_bootstrap_seed_without_wake() -> None:
    """
    Drive shipped OperatorAgent.bootstrap_session / seed_cursor_if_empty
    (same prefix as run_forever) with mocked rest_login/find_dm_room/http_api.
    Asserts save_state seed and that wake_grok is never called.
    """
    agent = _load_module("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
    tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
    wake_calls: list[str] = []
    old = {
        "STATE_PATH": agent.STATE_PATH,
        "LOCK_DIR": agent.LOCK_DIR,
        "rest_login": agent.rest_login,
        "find_dm_room": agent.find_dm_room,
        "http_api": agent.http_api,
        "wake_grok": agent.wake_grok,
        "SECRETS": agent.SECRETS,
    }
    try:
        agent.STATE_PATH = tmp / "state.json"
        agent.LOCK_DIR = tmp / "lock.d"
        agent.rest_login = lambda u, p: ("tok-seed", "uid-seed")
        agent.find_dm_room = lambda t, u: "room-agent-seed"
        agent.http_api = lambda method, path, token=None, uid=None, body=None: {
            "messages": [
                {
                    "_id": "api-newest",
                    "ts": "t9",
                    "u": {"username": "principal"},
                    "msg": "latest",
                },
                {
                    "_id": "api-older",
                    "ts": "t1",
                    "u": {"username": "principal"},
                    "msg": "older",
                },
            ]
        }
        agent.wake_grok = lambda prompt, **kwargs: wake_calls.append(prompt) or (99, None)

        inst = agent.OperatorAgent()
        # Same call run_forever makes before opening the websocket
        seeded = inst.bootstrap_session("grok", "unused")
        assert seeded is not None, "expected seed dict"
        assert seeded.get("last_seen_id") == "api-newest"
        assert seeded.get("last_wake_at") is None
        assert seeded.get("room_id") == "room-agent-seed"
        assert inst.token == "tok-seed" and inst.uid == "uid-seed"
        assert inst.room_id == "room-agent-seed"
        assert wake_calls == [], f"seed must not wake: {wake_calls}"
        disk = agent.load_state()
        assert disk.get("last_seen_id") == "api-newest"
        # already seeded → no re-seed, still no wake
        again = inst.seed_cursor_if_empty()
        assert again is None
        assert wake_calls == []
        # run_forever must call bootstrap_session
        import inspect

        rf = inspect.getsource(agent.OperatorAgent.run_forever)
        assert "bootstrap_session" in rf
        record("agent_bootstrap_seed_without_wake", True)
    except Exception as e:
        record("agent_bootstrap_seed_without_wake", False, repr(e) + traceback.format_exc())
    finally:
        for k, v in old.items():
            setattr(agent, k, v)
        shutil.rmtree(tmp, ignore_errors=True)


def test_state_load_save_roundtrip() -> None:
    wl = _load_module("wake_lib", WAKE_DIR / "wake_lib.py")
    tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
    try:
        sp = tmp / "state.json"
        empty = wl.load_state(sp)
        assert empty.get("version") == 2
        assert empty.get("rooms") == {}
        # corrupt
        sp.write_text("{not json", encoding="utf-8")
        empty2 = wl.load_state(sp)
        assert empty2.get("version") == 2
        wl.save_state({"last_seen_id": "abc", "n": 1}, sp)
        loaded = wl.load_state(sp)
        assert loaded["last_seen_id"] == "abc"
        assert loaded.get("version") == 2
        record("state_load_save_roundtrip", True)
    except Exception as e:
        record("state_load_save_roundtrip", False, repr(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_lock_single_flight() -> None:
    wl = _load_module("wake_lib", WAKE_DIR / "wake_lib.py")
    tmp = Path(tempfile.mkdtemp(dir=SCRATCH))
    lock = tmp / "wake.lock.d"
    try:
        assert wl.acquire_wake_lock(lock) is True
        assert wl.acquire_wake_lock(lock) is False  # second fails (live holder)
        wl.release_wake_lock(lock)
        assert wl.acquire_wake_lock(lock) is True
        # IMP-02: live holder is never stolen even if mtime is ancient
        os.utime(lock, (1, 1))
        assert wl.acquire_wake_lock(lock, stale_after_s=0) is False
        # dead pid + age → reclaim
        (lock / "holder.pid").write_text("99999990", encoding="utf-8")
        os.utime(lock, (1, 1))
        assert wl.acquire_wake_lock(lock, stale_after_s=10) is True
        wl.release_wake_lock(lock)
        record("lock_single_flight", True)
    except Exception as e:
        record("lock_single_flight", False, repr(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_wake_argv_no_disallowed_agent() -> None:
    wl = _load_module("wake_lib", WAKE_DIR / "wake_lib.py")
    poll = _load_module("rc_dm_poll", WAKE_DIR / "rc_dm_poll.py")
    agent = _load_module("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
    try:
        argv = wl.build_wake_argv("/tmp/p.txt", grok_bin="/bin/grok", agency="/tmp/a", max_turns=7)
        assert argv[0] == "/bin/grok"
        # IMP-01: default is restricted (no blanket --always-approve)
        assert "--always-approve" not in argv
        assert "--permission-mode" in argv
        assert "auto" in argv
        assert "acceptEdits" not in argv
        assert "--prompt-file" in argv
        assert "/tmp/p.txt" in argv
        assert "--output-format" in argv and "json" in argv
        assert "--resume" not in argv
        argv_admin = wl.build_wake_argv(
            "/tmp/p.txt",
            grok_bin="/bin/grok",
            agency="/tmp/a",
            max_turns=7,
            approval_mode="admin",
        )
        assert "--always-approve" in argv_admin
        assert "--permission-mode" not in argv_admin
        argv_r = wl.build_wake_argv(
            "/tmp/p.txt",
            grok_bin="/bin/grok",
            agency="/tmp/a",
            max_turns=7,
            resume_session_id="019f-test-session",
        )
        assert "--resume" in argv_r and "019f-test-session" in argv_r
        assert wl.extract_session_id_from_output('{"sessionId":"abc-123","ok":true}') == "abc-123"
        st = {}
        wl.set_room_session_id(st, "roomA", "sid-1")
        assert wl.get_room_session_id(st, "roomA") == "sid-1"
        assert wl.get_room_session_id(st, "roomB") is None
        assert wl.slugify_channel_name("Prime-Gap-Structure") == "prime-gap-structure"
        assert wl.slugify_channel_name("#Prime Gap Structure") == "prime-gap-structure"
        pgs, reason = wl.resolve_project_cwd(
            "Prime-Gap-Structure", create_if_missing=False
        )
        assert reason in ("existing", "map"), reason
        assert pgs.name == "prime-gap-structure"
        assert "prime-gap-structure" in str(pgs)
        dm, dm_reason = wl.resolve_project_cwd("dm:principal", room_type="d")
        assert dm_reason == "dm"
        assert dm == wl.DEFAULT_AGENCY.resolve() or str(dm).endswith(".grok/agency")
        # Channels are never forced to agency — only DMs
        gen, gen_reason = wl.resolve_project_cwd(
            "general", room_type="c", create_if_missing=False
        )
        assert gen_reason != "dm" and gen_reason != "special", gen_reason
        assert "IdeaProjects" in str(gen) or gen_reason in ("map", "existing", "created", "agency_fallback")
        argv_cwd = wl.build_wake_argv(
            "/tmp/p.txt",
            grok_bin="/bin/grok",
            cwd="/Users/velocityworks/IdeaProjects/prime-gap-structure",
            max_turns=3,
        )
        assert "--cwd" in argv_cwd
        assert "/Users/velocityworks/IdeaProjects/prime-gap-structure" in argv_cwd
        assert wl.wake_argv_is_safe(argv)
        assert wl.wake_argv_is_safe(argv_r)
        bad = argv + ["--disallowed-tools", "Agent"]
        assert not wl.wake_argv_is_safe(bad)
        # production modules use build_wake_argv
        assert hasattr(poll, "build_wake_argv")
        assert hasattr(agent, "build_wake_argv")
        argv_p = poll.build_wake_argv("/tmp/x.txt", grok_bin="g", agency="a", max_turns="3")
        argv_a = agent.build_wake_argv("/tmp/y.txt", grok_bin="g", agency="a", max_turns="3")
        assert wl.wake_argv_is_safe(argv_p)
        assert wl.wake_argv_is_safe(argv_a)
        # source regression: no production *code* may pass --disallowed-tools Agent
        for fname in ("rc_dm_poll.py", "rc_operator_agent.py", "wake_lib.py"):
            src = (WAKE_DIR / fname).read_text(encoding="utf-8")
            for line in src.splitlines():
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                    continue
                # docstring lines often mention the ban; only flag list/string argv forms
                if "--disallowed-tools" not in line:
                    continue
                if "Agent" not in line:
                    continue
                if any(
                    bad in line
                    for bad in (
                        '"--disallowed-tools"',
                        "'--disallowed-tools'",
                        "[\"--disallowed-tools\"",
                        "['--disallowed-tools'",
                        "--disallowed-tools Agent",
                        "--disallowed-tools=Agent",
                    )
                ):
                    if "must not" in line.lower() or "do not" in line.lower() or "never" in line.lower():
                        continue
                    raise AssertionError(f"unsafe disallowed-tools argv in {fname}: {line}")
        record("wake_argv_no_disallowed_agent", True)
    except Exception as e:
        record("wake_argv_no_disallowed_agent", False, repr(e) + traceback.format_exc())


def test_should_handle_dm_message() -> None:
    wl = _load_module("wake_lib", WAKE_DIR / "wake_lib.py")
    try:
        pmsg = {"_id": "m1", "u": {"username": "principal"}, "msg": "hello"}
        assert wl.should_handle_dm_message(pmsg) is True
        assert wl.should_handle_dm_message({"_id": "m2", "u": {"username": "grok"}, "msg": "hi"}) is False
        assert wl.should_handle_dm_message({"_id": "m3", "u": {"username": "principal"}, "msg": "  "}) is False
        assert wl.should_handle_dm_message(pmsg, last_seen_id="m1") is False
        assert wl.should_handle_dm_message(pmsg, processed_ids=["m1"]) is False
        # Path A: pure voice note (empty text + audio file) must wake
        voice = {
            "_id": "m-audio",
            "u": {"username": "principal"},
            "msg": "",
            "file": {"_id": "f1", "name": "voice.m4a", "type": "audio/mp4"},
        }
        assert wl.should_handle_dm_message(voice) is True
        assert wl.message_has_handleable_content(voice) is True
        assert len(wl.extract_audio_file_candidates(voice)) == 1
        # caption + non-audio only: still handleable as text
        assert wl.compose_wake_user_text("hi", transcripts=["hello world"]) == (
            "hi\n\n[Voice note transcript]\nhello world"
        )
        assert wl.compose_wake_user_text("", transcripts=["only voice"]) == (
            "[Voice note transcript]\nonly voice"
        )
        record("should_handle_dm_message", True)
    except Exception as e:
        record("should_handle_dm_message", False, repr(e))


def test_require_mention_tag_to_talk() -> None:
    """Dual-operator tag-to-talk: channels need @operator; DMs free-wake by default."""
    wl = _load_module("wake_lib", WAKE_DIR / "wake_lib.py")
    try:
        env_off = {"RC_REQUIRE_MENTION": "0"}
        env_ch = {"RC_REQUIRE_MENTION": "1", "RC_REQUIRE_MENTION_SCOPE": "channels"}
        env_all = {"RC_REQUIRE_MENTION": "1", "RC_REQUIRE_MENTION_SCOPE": "all"}

        assert wl.require_mention_enabled(env_off) is False
        assert wl.require_mention_enabled(env_ch) is True
        assert wl.require_mention_scope(env_ch) == "channels"
        assert wl.require_mention_scope(env_all) == "all"

        assert wl.room_requires_operator_mention("c", env=env_ch) is True
        assert wl.room_requires_operator_mention("p", env=env_ch) is True
        assert wl.room_requires_operator_mention("d", env=env_ch) is False
        assert wl.room_requires_operator_mention(None, env=env_ch) is False
        assert wl.room_requires_operator_mention("d", env=env_all) is True
        assert wl.room_requires_operator_mention("c", env=env_off) is False

        untagged = {"_id": "m1", "u": {"username": "principal"}, "msg": "notes for later"}
        tagged_grok = {"_id": "m2", "u": {"username": "principal"}, "msg": "hey @grok summarize"}
        tagged_case = {"_id": "m3", "u": {"username": "principal"}, "msg": "ping @Grok please"}
        tagged_hermes = {
            "_id": "m4",
            "u": {"username": "principal"},
            "msg": "hey @hermes status",
        }
        structured = {
            "_id": "m5",
            "u": {"username": "principal"},
            "msg": "hello",
            "mentions": [{"username": "grok"}],
        }
        dual = {
            "_id": "m6",
            "u": {"username": "principal"},
            "msg": "@grok and @hermes both look",
        }

        assert wl.message_mentions_operator(untagged, "grok") is False
        assert wl.message_mentions_operator(tagged_grok, "grok") is True
        assert wl.message_mentions_operator(tagged_case, "grok") is True
        assert wl.message_mentions_operator(tagged_hermes, "grok") is False
        assert wl.message_mentions_operator(tagged_hermes, "hermes") is True
        assert wl.message_mentions_operator(structured, "grok") is True
        assert wl.message_mentions_operator(dual, "grok") is True
        assert wl.message_mentions_operator(dual, "hermes") is True

        # Flag off: free-wake in channel
        assert (
            wl.should_enqueue_llm_wake(
                untagged, operator="grok", room_type="c", env=env_off
            )
            is True
        )
        # Flag on channels: untagged channel skip; DM free-wake; tagged channel ok
        assert (
            wl.should_enqueue_llm_wake(
                untagged, operator="grok", room_type="c", env=env_ch
            )
            is False
        )
        assert (
            wl.should_enqueue_llm_wake(
                untagged, operator="grok", room_type="d", env=env_ch
            )
            is True
        )
        assert (
            wl.should_enqueue_llm_wake(
                tagged_grok, operator="grok", room_type="c", env=env_ch
            )
            is True
        )
        assert (
            wl.should_enqueue_llm_wake(
                tagged_hermes, operator="grok", room_type="c", env=env_ch
            )
            is False
        )
        assert (
            wl.should_enqueue_llm_wake(
                tagged_hermes, operator="hermes", room_type="c", env=env_ch
            )
            is True
        )
        # Dual mention: both operators may enqueue
        assert (
            wl.should_enqueue_llm_wake(
                dual, operator="grok", room_type="c", env=env_ch
            )
            is True
        )
        assert (
            wl.should_enqueue_llm_wake(
                dual, operator="hermes", room_type="c", env=env_ch
            )
            is True
        )
        # Scope all: DM needs @
        assert (
            wl.should_enqueue_llm_wake(
                untagged, operator="grok", room_type="d", env=env_all
            )
            is False
        )
        assert (
            wl.should_enqueue_llm_wake(
                tagged_grok, operator="grok", room_type="d", env=env_all
            )
            is True
        )

        # Peer tags: any author @operator wakes; self never wakes; flag-off blocks peers
        peer_tag = {
            "_id": "m-peer",
            "u": {"username": "grok"},
            "msg": "handoff @hermes please pong",
        }
        self_tag = {
            "_id": "m-self",
            "u": {"username": "hermes"},
            "msg": "ignore @hermes self",
        }
        peer_untagged = {
            "_id": "m-peer-plain",
            "u": {"username": "grok"},
            "msg": "noise without tag",
        }
        env_peer_off = {
            "RC_REQUIRE_MENTION": "1",
            "RC_REQUIRE_MENTION_SCOPE": "channels",
            "RC_PEER_TAG_WAKE": "0",
        }
        assert wl.peer_tag_wake_enabled(env_ch) is True
        assert wl.peer_tag_wake_enabled(env_peer_off) is False
        assert (
            wl.should_enqueue_llm_wake(
                peer_tag, operator="hermes", room_type="c", env=env_ch
            )
            is True
        )
        assert (
            wl.should_enqueue_llm_wake(
                peer_untagged, operator="hermes", room_type="c", env=env_ch
            )
            is False
        )
        assert (
            wl.should_enqueue_llm_wake(
                self_tag, operator="hermes", room_type="c", env=env_ch
            )
            is False
        )
        assert (
            wl.should_enqueue_llm_wake(
                peer_tag, operator="hermes", room_type="c", env=env_peer_off
            )
            is False
        )
        record("require_mention_tag_to_talk", True)
    except Exception as e:
        record("require_mention_tag_to_talk", False, repr(e) + traceback.format_exc())


def test_poller_unreachable_soft_fail() -> None:
    """poll_once returns soft fail (1) when RC base is unreachable — not crash."""
    poll = _load_module("rc_dm_poll", WAKE_DIR / "rc_dm_poll.py")
    if not SECRETS.is_file():
        record_skip("poller_unreachable_soft_fail", "secrets missing")
        return
    old = poll.BASE_URL
    try:
        poll.BASE_URL = "http://127.0.0.1:1"  # nothing listening
        rc = poll.poll_once()
        assert rc == 1, f"expected soft fail 1, got {rc}"
        record("poller_unreachable_soft_fail", True, f"rc={rc}")
    except Exception as e:
        record("poller_unreachable_soft_fail", False, repr(e))
    finally:
        poll.BASE_URL = old


def test_poller_missing_secrets() -> None:
    poll = _load_module("rc_dm_poll", WAKE_DIR / "rc_dm_poll.py")
    old = poll.SECRETS
    try:
        poll.SECRETS = Path("/nonexistent/path/rocketchat.env")
        rc = poll.poll_once()
        assert rc == 2, f"expected hard fail 2, got {rc}"
        record("poller_missing_secrets", True, f"rc={rc}")
    except Exception as e:
        record("poller_missing_secrets", False, repr(e))
    finally:
        poll.SECRETS = old


def test_live_smoke_if_available() -> None:
    """
    Opt-in live RC checks only (RC_LIVE_SMOKE=1).

    Default is SKIP: posting as principal into the real DM wakes production
    Grok and previously polluted the operator (rc-int-test spam + wake lock).
    When enabled: login both users + presence only — no chat.postMessage.
    """
    if os.environ.get("RC_LIVE_SMOKE", "").strip() not in ("1", "true", "yes"):
        record_skip(
            "live_smoke",
            "set RC_LIVE_SMOKE=1 to run (default off: avoids production wake spam)",
        )
        return
    try:
        urllib.request.urlopen("http://127.0.0.1:3000/api/info", timeout=3)
    except Exception as e:
        record_skip("live_smoke", f"RC down: {e}")
        return
    if not SECRETS.is_file():
        record_skip("live_smoke", "secrets missing")
        return
    wl = _load_module("wake_lib", WAKE_DIR / "wake_lib.py")
    poll = _load_module("rc_dm_poll", WAKE_DIR / "rc_dm_poll.py")
    try:
        secrets = wl.load_env(SECRETS)

        def login(user_key: str, pass_key: str):
            body = json.dumps(
                {"user": secrets[user_key], "password": secrets[pass_key]}
            ).encode()
            req = urllib.request.Request(
                "http://127.0.0.1:3000/api/v1/login",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                d = json.loads(r.read().decode())
            assert d.get("status") == "success"
            return d["data"]["authToken"], d["data"]["userId"]

        _p_tok, _p_uid = login("ROCKETCHAT_ADMIN_USERNAME", "ROCKETCHAT_ADMIN_PASSWORD")
        g_tok, g_uid = login("ROCKETCHAT_OPERATOR_USERNAME", "ROCKETCHAT_OPERATOR_PASSWORD")
        room = poll.principal_dm_room(g_tok, g_uid)
        assert room

        req2 = urllib.request.Request(
            "http://127.0.0.1:3000/api/v1/users.info?username=grok",
            headers={"X-Auth-Token": g_tok, "X-User-Id": g_uid},
        )
        with urllib.request.urlopen(req2, timeout=10) as r:
            u = json.loads(r.read().decode()).get("user") or {}
        status = u.get("status")
        conn = u.get("statusConnection")
        presence_ok = status is not None
        detail = f"room={room} status={status} statusConnection={conn} (no post)"
        olog = Path.home() / "logs" / "rocketchat-dm-wake" / "operator-agent.log"
        if olog.is_file() and "login OK" in olog.read_text(encoding="utf-8", errors="replace")[-5000:]:
            detail += " agent_log=login_ok"
        record("live_smoke", presence_ok, detail)
    except Exception as e:
        record("live_smoke", False, repr(e) + traceback.format_exc())


def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    print("=== Rocket.Chat ↔ Grok integration tests ===")
    print(f"WAKE_DIR={WAKE_DIR}")
    print(f"SCRATCH={SCRATCH}")

    test_load_env_and_missing()
    test_new_principal_messages_edges()
    test_seed_helper()
    test_poll_once_seed_without_wake()
    test_agent_state_and_lock_paths()
    test_agent_bootstrap_seed_without_wake()
    test_state_load_save_roundtrip()
    test_lock_single_flight()
    test_wake_argv_no_disallowed_agent()
    test_should_handle_dm_message()
    test_require_mention_tag_to_talk()
    test_poller_missing_secrets()
    test_poller_unreachable_soft_fail()
    test_live_smoke_if_available()

    # Usability contracts (isolated; never touch production lock/state)
    import subprocess

    u = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "test_usability_contracts.py")],
        capture_output=True,
        text=True,
    )
    print(u.stdout)
    if u.stderr:
        print(u.stderr)
    if u.returncode != 0:
        RESULTS.append(("usability_contracts_suite", "FAIL", (u.stdout + u.stderr)[-500:]))
    else:
        RESULTS.append(("usability_contracts_suite", "PASS", ""))

    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    failed = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    skipped = sum(1 for _, s, _ in RESULTS if s == "SKIP")
    summary = f"\n=== SUMMARY passed={passed} failed={failed} skipped={skipped} ===\n"
    print(summary)
    for name, status, detail in RESULTS:
        print(f"  {status:4} {name}" + (f" ({detail[:100]})" if detail else ""))

    log_path = SCRATCH / "rc_integration_test.log"
    lines = [f"[{s}] {n}" + (f" — {d}" if d else "") for n, s, d in RESULTS]
    lines.append(summary.strip())
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {log_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
