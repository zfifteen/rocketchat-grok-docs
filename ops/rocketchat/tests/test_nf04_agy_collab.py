#!/usr/bin/env python3
"""
NF-SPEC-04 AGY RocketChat Collab — unit/contract tests on shipped code.

Usage:
  RC_TEST_SCRATCH=... python3 ~/.grok/agency/ops/rocketchat/tests/test_nf04_agy_collab.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

WAKE_DIR = Path.home() / ".grok" / "agency" / "ops" / "rocketchat" / "wake"
SCRATCH = Path(
    os.environ.get(
        "RC_TEST_SCRATCH",
        "/var/folders/k_/spz3lj566sc4qh29g0tk6jh0000gn/T/grok-goal-049f1b283d3b/implementer",
    )
)
# fix typo fallback if env not set — use known goal scratch
if not SCRATCH.exists():
    SCRATCH = Path(
        "/var/folders/k_/spz3zlj566sc4qh29g0tk6jh0000gn/T/grok-goal-049f1b283d3b/implementer"
    )
SCRATCH.mkdir(parents=True, exist_ok=True)

RESULTS: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    RESULTS.append((name, status, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def _load(name: str, path: Path):
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    if name in sys.modules:
        # reload pure modules under test when re-running
        if name in ("rc_collab",):
            del sys.modules[name]
        else:
            return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# L0 Unit — mention / allowlist / self-wake / hop FSM
# ---------------------------------------------------------------------------


def test_master_flag_and_room_arm() -> None:
    try:
        c = _load("rc_collab", WAKE_DIR / "rc_collab.py")
        assert c.collab_master_enabled({"RC_AGY_COLLAB": "1"}) is True
        assert c.collab_master_enabled({"RC_AGY_COLLAB": "0"}) is False
        assert c.collab_master_enabled({}) is False

        prof = {"cwd": "/tmp/pgs", "mode": "agy-collab"}
        assert c.is_collab_profile(prof) is True
        assert c.is_collab_profile({"cwd": "/tmp/x"}) is False

        assert (
            c.collab_armed_for_room(
                "grok-agy-collab",
                env={"RC_AGY_COLLAB": "1"},
                profile=prof,
            )
            is True
        )
        assert (
            c.collab_armed_for_room(
                "grok-agy-collab",
                env={"RC_AGY_COLLAB": "0"},
                profile=prof,
            )
            is False
        )
        assert (
            c.collab_armed_for_room(
                "dm:principal",
                env={"RC_AGY_COLLAB": "1"},
                profile=prof,
                room_type="d",
            )
            is False
        )
        assert (
            c.collab_armed_for_room(
                "general",
                env={"RC_AGY_COLLAB": "1"},
                profile={"cwd": "/tmp", "mode": "normal"},
            )
            is False
        )
        record("master_flag_and_room_arm", True)
    except Exception as e:
        record("master_flag_and_room_arm", False, repr(e) + traceback.format_exc())


def test_mention_parse_structured_and_text() -> None:
    try:
        c = _load("rc_collab", WAKE_DIR / "rc_collab.py")
        msg = {
            "msg": "hello @agy please review",
            "mentions": [{"username": "agy"}],
        }
        t = c.resolve_mention_targets(msg)
        assert t == {"agy"}, t

        # text fallback only
        t2 = c.resolve_mention_targets({"msg": "ping @Grok and later @agy"}, text=None)
        assert t2 == {"grok", "agy"}, t2

        # no false positive inside email-like tokens (word boundary)
        t3 = c.resolve_mention_targets({"msg": "see xagy and grok without at"})
        assert t3 == set(), t3

        # structured wins even if text lacks @
        t4 = c.resolve_mention_targets(
            {"msg": "hello", "mentions": [{"username": "grok"}]}
        )
        assert t4 == {"grok"}, t4
        record("mention_parse_structured_and_text", True)
    except Exception as e:
        record("mention_parse_structured_and_text", False, repr(e) + traceback.format_exc())


def test_classify_routing_matrix() -> None:
    try:
        c = _load("rc_collab", WAKE_DIR / "rc_collab.py")

        # untagged ignore
        d = c.classify_collab_message(
            author="principal", targets=set(), collab_armed=True
        )
        assert d.action == "ignore" and d.reason == "no_agent_mention"

        # principal @agy → agy
        d = c.classify_collab_message(
            author="principal", targets={"agy"}, collab_armed=True
        )
        assert d.action == "wake" and d.target == "agy"

        # principal @grok → grok
        d = c.classify_collab_message(
            author="principal", targets={"grok"}, collab_armed=True
        )
        assert d.action == "wake" and d.target == "grok"

        # grok @agy handoff
        d = c.classify_collab_message(
            author="grok", targets={"agy"}, collab_armed=True
        )
        assert d.action == "wake" and d.target == "agy"

        # agy @grok handoff
        d = c.classify_collab_message(
            author="agy", targets={"grok"}, collab_armed=True
        )
        assert d.action == "wake" and d.target == "grok"

        # self-mention ignore
        d = c.classify_collab_message(
            author="agy", targets={"agy"}, collab_armed=True
        )
        assert d.action == "ignore" and d.reason == "self_mention"

        # double mention reject
        d = c.classify_collab_message(
            author="principal", targets={"agy", "grok"}, collab_armed=True
        )
        assert d.action == "reject" and d.reason == "double_mention"
        assert "one" in d.reply.lower()

        # non-allowlisted
        d = c.classify_collab_message(
            author="stranger", targets={"agy"}, collab_armed=True
        )
        assert d.action == "ignore" and d.reason == "author_not_allowlisted"

        # not armed
        d = c.classify_collab_message(
            author="principal", targets={"agy"}, collab_armed=False
        )
        assert d.action == "ignore" and d.reason == "collab_not_armed"

        # bot paused
        d = c.classify_collab_message(
            author="agy",
            targets={"grok"},
            collab_armed=True,
            auto_handoff=False,
            paused_reason="principal",
        )
        assert d.action == "ignore" and d.reason == "paused"

        # principal still wakes when paused
        d = c.classify_collab_message(
            author="principal",
            targets={"agy"},
            collab_armed=True,
            auto_handoff=False,
            paused_reason="principal",
        )
        assert d.action == "wake" and d.target == "agy"

        # budget on bot
        d = c.classify_collab_message(
            author="grok",
            targets={"agy"},
            collab_armed=True,
            hop_count_epoch=100,
            hop_budget_epoch=100,
        )
        assert d.action == "notify_budget"

        record("classify_routing_matrix", True)
    except Exception as e:
        record("classify_routing_matrix", False, repr(e) + traceback.format_exc())


def test_hop_budget_pause_fsm() -> None:
    try:
        c = _load("rc_collab", WAKE_DIR / "rc_collab.py")
        state: dict = {}
        c.ensure_collab_budget(state, "r1", budget=3)
        cur = c.get_collab_room_state(state, "r1")
        assert cur["hop_budget_epoch"] == 3
        assert cur["auto_handoff"] is True

        # principal hop does not count toward budget
        c.record_collab_hop(state, "r1", author="principal", target="agy")
        cur = c.get_collab_room_state(state, "r1")
        assert cur["hop_count_epoch"] == 0

        # bot hops count
        c.record_collab_hop(state, "r1", author="agy", target="grok")
        c.record_collab_hop(state, "r1", author="grok", target="agy")
        c.record_collab_hop(state, "r1", author="agy", target="grok")
        cur = c.get_collab_room_state(state, "r1")
        assert cur["hop_count_epoch"] == 3
        assert cur["auto_handoff"] is False
        assert cur["paused_reason"] == "budget"
        # pins retained
        c.set_agy_conversation_id(state, "r1", "uuid-abc-123")
        assert c.get_agy_conversation_id(state, "r1") == "uuid-abc-123"

        c.resume_auto_handoff(state, "r1")
        cur = c.get_collab_room_state(state, "r1")
        assert cur["auto_handoff"] is True
        assert cur["paused_reason"] is None
        # hops not wiped unless reset_epoch
        assert cur["hop_count_epoch"] == 3
        assert c.get_agy_conversation_id(state, "r1") == "uuid-abc-123"

        record("hop_budget_pause_fsm", True)
    except Exception as e:
        record("hop_budget_pause_fsm", False, repr(e) + traceback.format_exc())


def test_agy_cli_plan_no_mcp() -> None:
    try:
        c = _load("rc_collab", WAKE_DIR / "rc_collab.py")
        plan = c.build_agy_helper_plan(
            cwd="/tmp/repo",
            prompt_file="/tmp/p.md",
            log_file="/tmp/a.log",
            state_file="/tmp/s.txt",
            conversation_id=None,
            env={"RC_AGY_HELPER": "/tmp/agy_cli.py", "RC_AGY_BIN": "/tmp/agy"},
        )
        assert plan.mode == "start"
        assert plan.uses_mcp is False
        assert "--mode" in plan.argv and "start" in plan.argv
        c.assert_no_mcp_agy_in_argv(plan.argv)

        plan2 = c.build_agy_helper_plan(
            cwd="/tmp/repo",
            prompt_file="/tmp/p.md",
            log_file="/tmp/a.log",
            state_file="/tmp/s.txt",
            conversation_id="11111111-2222-3333-4444-555555555555",
            env={"RC_AGY_HELPER": "/tmp/agy_cli.py", "RC_AGY_BIN": "/tmp/agy"},
        )
        assert plan2.mode == "conversation"
        assert "11111111-2222-3333-4444-555555555555" in plan2.argv

        try:
            c.assert_no_mcp_agy_in_argv(["tool", "agy_ask"])
            raise AssertionError("should have raised")
        except ValueError:
            pass

        err = c.format_agy_cli_error(1, stderr_tail="boom", log_name="x.log")
        assert "agy CLI" in err and "MCP" in err
        assert "Gemini said" not in err

        record("agy_cli_plan_no_mcp", True)
    except Exception as e:
        record("agy_cli_plan_no_mcp", False, repr(e) + traceback.format_exc())


# ---------------------------------------------------------------------------
# L1 Contract — real operator intake + dual-identity/CLI (shipped path)
# ---------------------------------------------------------------------------

ROUTING_EVIDENCE: list[str] = []
IDENTITY_EVIDENCE: list[str] = []


def _isolate_operator(agent, tmp: Path) -> None:
    """Sandbox STATE/LOG/LOCK so contract tests never touch production state."""
    agent.STATE_PATH = tmp / "state.json"
    agent.LOCK_DIR = tmp / "wake.lock.d"
    agent.LOG_DIR = tmp / "logs"
    agent.LOG_PATH = agent.LOG_DIR / "operator-agent.log"
    agent.HEALTH_PATH = agent.LOG_DIR / "health.json"
    agent.LOG_DIR.mkdir(parents=True, exist_ok=True)
    agent.PROMPT_TEMPLATE = WAKE_DIR / "reply_prompt.txt"
    agent.save_state({"processed_ids": [], "pending_wakes": [], "rooms": {}})
    # Never start real drain threads during intake routing contracts
    agent._drain_pending_wakes = lambda: None
    # Swallow posts used for reject/budget notify
    agent.post_as_grok = lambda *a, **k: True
    agent.post_message_get_id = lambda *a, **k: "post-id"


def _pending_targets(agent) -> list[dict]:
    st = agent.load_state()
    return [p for p in (st.get("pending_wakes") or []) if isinstance(p, dict)]


def test_contract_routing_intake() -> None:
    """
    Gate 2: drive shipped handle_principal_message → pending_wakes.

    Asserts correct target backend (or no wake) for collab-armed/off,
    @agy/@grok, untagged, stranger, bot handoff.
    """
    try:
        _load("rc_collab", WAKE_DIR / "rc_collab.py")
        agent = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
        ROUTING_EVIDENCE.clear()
        with tempfile.TemporaryDirectory(dir=str(SCRATCH)) as td:
            tmp = Path(td)
            _isolate_operator(agent, tmp)
            room = "grok-agy-collab"
            rid = "room-collab-1"

            # --- collab ARMED ---
            agent.collab_armed_for_room = lambda *a, **k: True
            agent.lookup_room_profile = lambda *a, **k: {
                "cwd": str(tmp / "repo"),
                "mode": "agy-collab",
                "hop_budget_epoch": 100,
            }
            (tmp / "repo").mkdir(exist_ok=True)

            def feed(mid: str, author: str, text: str, mentions=None) -> None:
                msg = {
                    "_id": mid,
                    "rid": rid,
                    "msg": text,
                    "ts": "2026-07-11T00:00:00.000Z",
                    "u": {"username": author},
                }
                if mentions is not None:
                    msg["mentions"] = mentions
                agent.handle_principal_message(
                    msg, rid, room_name=room, room_type="p"
                )

            # principal @agy → enqueue target=agy collab=True
            feed(
                "m-p-agy",
                "principal",
                "@agy review chamber reset",
                mentions=[{"username": "agy"}],
            )
            pend = _pending_targets(agent)
            assert len(pend) == 1, pend
            assert pend[0]["target"] == "agy" and pend[0].get("collab") is True
            ROUTING_EVIDENCE.append(
                f"armed principal@agy → pending target={pend[0]['target']} collab={pend[0].get('collab')}"
            )

            # principal @grok → target=grok
            feed(
                "m-p-grok",
                "principal",
                "@grok implement falsifier",
                mentions=[{"username": "grok"}],
            )
            pend = _pending_targets(agent)
            last = [p for p in pend if p.get("mid") == "m-p-grok"]
            assert last and last[0]["target"] == "grok" and last[0].get("collab") is True
            ROUTING_EVIDENCE.append(
                f"armed principal@grok → pending target={last[0]['target']}"
            )

            # untagged principal → no new pending
            before = {p.get("mid") for p in _pending_targets(agent)}
            feed("m-untagged", "principal", "just a note without mention")
            after = {p.get("mid") for p in _pending_targets(agent)}
            assert "m-untagged" not in after
            assert after == before
            ROUTING_EVIDENCE.append("armed untagged principal → no enqueue")

            # stranger @agy → no enqueue
            feed(
                "m-stranger",
                "eve",
                "@agy hi",
                mentions=[{"username": "agy"}],
            )
            assert "m-stranger" not in {
                p.get("mid") for p in _pending_targets(agent)
            }
            ROUTING_EVIDENCE.append("armed stranger@agy → no enqueue")

            # bot handoff: agy @grok → target=grok
            feed(
                "m-handoff",
                "agy",
                "Objection below. @grok please respond.",
                mentions=[{"username": "grok"}],
            )
            hand = [p for p in _pending_targets(agent) if p.get("mid") == "m-handoff"]
            assert hand and hand[0]["target"] == "grok" and hand[0].get("collab") is True
            ROUTING_EVIDENCE.append(
                f"armed agy@grok handoff → pending target={hand[0]['target']}"
            )

            # grok @agy handoff → target=agy
            feed(
                "m-g2a",
                "grok",
                "Need review @agy",
                mentions=[{"username": "agy"}],
            )
            g2a = [p for p in _pending_targets(agent) if p.get("mid") == "m-g2a"]
            assert g2a and g2a[0]["target"] == "agy"
            ROUTING_EVIDENCE.append(
                f"armed grok@agy handoff → pending target={g2a[0]['target']}"
            )

            # --- collab OFF (flag/profile): principal-only content wake, not dual ---
            agent.save_state({"processed_ids": [], "pending_wakes": [], "rooms": {}})
            agent.collab_armed_for_room = lambda *a, **k: False
            feed(
                "m-off-agy",
                "principal",
                "@agy should not dual-route",
                mentions=[{"username": "agy"}],
            )
            off = _pending_targets(agent)
            assert len(off) == 1 and off[0]["mid"] == "m-off-agy"
            # Legacy path: target defaults to grok, collab False
            assert off[0].get("target", "grok") == "grok"
            assert off[0].get("collab") in (False, None)
            ROUTING_EVIDENCE.append(
                f"flag/profile off principal@agy → target={off[0].get('target')} collab={off[0].get('collab')}"
            )

            # Bot message ignored when not armed
            agent.save_state({"processed_ids": [], "pending_wakes": [], "rooms": {}})
            agent.collab_armed_for_room = lambda *a, **k: False
            feed(
                "m-off-bot",
                "agy",
                "@grok hi",
                mentions=[{"username": "grok"}],
            )
            assert _pending_targets(agent) == []
            ROUTING_EVIDENCE.append("flag off bot@grok → no enqueue (principal-only)")

            # Double-mention reject: no enqueue, may post help
            agent.save_state({"processed_ids": [], "pending_wakes": [], "rooms": {}})
            agent.collab_armed_for_room = lambda *a, **k: True
            rejects: list[str] = []
            agent.post_as_grok = lambda rid, text: rejects.append(text) or True
            feed(
                "m-double",
                "principal",
                "@agy and @grok both",
                mentions=[{"username": "agy"}, {"username": "grok"}],
            )
            assert _pending_targets(agent) == []
            assert rejects and "one" in rejects[0].lower()
            # double-mention is marked processed (no wake)
            assert "m-double" in (agent.load_state().get("processed_ids") or [])
            ROUTING_EVIDENCE.append(
                f"armed double-mention → no pending; reject_reply={rejects[0][:60]!r}"
            )

        record(
            "contract_routing_intake",
            True,
            f"{len(ROUTING_EVIDENCE)} assertions via handle_principal_message",
        )
    except Exception as e:
        record("contract_routing_intake", False, repr(e) + traceback.format_exc())


def test_contract_identity_and_cli_helpers() -> None:
    """
    Gate 3: dual identity post/update + local agy CLI path + grok collab drain.

    - Thinking/finalize as identity=agy for agy-target drain
    - wake_agy_cli builds helper argv with conversation pin; no MCP
    - CLI fail finalizes honest format_agy_cli_error body as agy
    - _process_pending_item collab=True target=grok: identity=grok + collab inject
    """
    try:
        c = _load("rc_collab", WAKE_DIR / "rc_collab.py")
        agent = _load("rc_operator_agent", WAKE_DIR / "rc_operator_agent.py")
        IDENTITY_EVIDENCE.clear()
        with tempfile.TemporaryDirectory(dir=str(SCRATCH)) as td:
            tmp = Path(td)
            _isolate_operator(agent, tmp)
            repo = tmp / "repo"
            repo.mkdir()

            # --- wake_agy_cli: capture argv + fail path ---
            captured_argv: list[list[str]] = []

            class FakeProc:
                def __init__(self, rc=1, stdout="", stderr="auth failed"):
                    self.returncode = rc
                    self.stdout = stdout
                    self.stderr = stderr

            def fake_run(argv, **kwargs):
                captured_argv.append(list(argv))
                return FakeProc(rc=1, stdout="", stderr="permission denied: not logged in")

            import subprocess as _sp

            real_run = _sp.run
            _sp.run = fake_run  # type: ignore[assignment]
            try:
                # pin conversation → mode conversation in helper plan
                rc, body, new_cid, log_text = agent.wake_agy_cli(
                    cwd=str(repo),
                    prompt_text="# brief\n@agy hello",
                    conversation_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                    room_id="room-id",
                    mid="m-cli-1",
                )
            finally:
                _sp.run = real_run

            assert captured_argv, "wake_agy_cli must invoke subprocess"
            argv = captured_argv[0]
            IDENTITY_EVIDENCE.append(f"wake_agy_cli argv={argv[:8]}... n={len(argv)}")
            joined = " ".join(argv)
            assert "agy_cli.py" in joined or any("agy_cli" in a for a in argv)
            assert "--conversation" in argv
            assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in argv
            assert "--mode" in argv and "conversation" in argv
            for bad in ("agy_ask", "agy_ping", "agy_models", "agy_version"):
                assert bad not in joined
            assert rc == 1
            assert "agy CLI" in body or "did not produce" in body
            assert "MCP" in body or "No MCP" in body
            assert "Gemini said" not in body
            IDENTITY_EVIDENCE.append(
                f"CLI fail body_prefix={body.splitlines()[0]!r} rc={rc}"
            )

            # start mode when no conversation id
            captured_argv.clear()
            _sp.run = fake_run  # type: ignore[assignment]
            try:
                agent.wake_agy_cli(
                    cwd=str(repo),
                    prompt_text="start turn",
                    conversation_id=None,
                    room_id="room-id",
                    mid="m-cli-2",
                )
            finally:
                _sp.run = real_run
            assert "--mode" in captured_argv[0] and "start" in captured_argv[0]
            IDENTITY_EVIDENCE.append("wake_agy_cli mode=start when uuid=None")

            # --- _process_agy_collab_item: identity=agy Thinking + finalize ---
            posts: list[tuple[str, str]] = []
            finals: list[tuple[str, str, str]] = []
            metas: list[tuple[str, str]] = []

            def post_thinking(room_id: str, *, identity: str = "grok") -> str:
                posts.append((identity, "…"))
                return "think-agy-bubble"

            def finalize(
                room_id: str,
                mid: str,
                body: str,
                *,
                identity: str = "grok",
            ) -> bool:
                finals.append((identity, mid, body))
                return True

            def meta(room_id, mid, body, *, identity: str = "grok"):
                metas.append((identity, body[:40]))
                return True

            err_body = c.format_agy_cli_error(
                1, stderr_tail="permission denied", log_name="agy-run-x.log"
            )

            def fake_agy_cli(**kwargs):
                return (1, err_body, None, "log text")

            agent.post_thinking_placeholder = post_thinking
            agent.finalize_thinking_message = finalize
            agent.update_thinking_meta = meta
            agent.wake_agy_cli = fake_agy_cli
            agent._resolve_room_cwd_info = lambda *a, **k: (str(repo), "map")
            agent.force_clear_wake_lock = lambda *a, **k: True
            agent.acquire_wake_lock = lambda *a, **k: True
            agent.release_wake_lock = lambda *a, **k: None

            item = {
                "mid": "m-agy-proc",
                "rid": "room-collab-1",
                "room_name": "grok-agy-collab",
                "room_type": "p",
                "text": "@agy please object",
                "author": "principal",
                "target": "agy",
                "collab": True,
                "u": {"username": "principal"},
                "ts": "2026-07-11T00:00:00.000Z",
            }
            agent._process_agy_collab_item(item)

            assert posts, "must post Thinking as agy"
            assert posts[0][0] == "agy", posts
            assert finals, "must finalize as agy"
            assert finals[0][0] == "agy", finals
            assert finals[0][1] == "think-agy-bubble"
            assert "agy CLI" in finals[0][2] or "did not produce" in finals[0][2]
            assert "fabricated" not in finals[0][2].lower()
            # processed
            assert "m-agy-proc" in (agent.load_state().get("processed_ids") or [])
            IDENTITY_EVIDENCE.append(
                f"process_agy post_identity={posts[0][0]} "
                f"finalize_identity={finals[0][0]} mid={finals[0][1]} "
                f"body_has_error={('agy CLI' in finals[0][2])}"
            )

            # success path still identity=agy
            posts.clear()
            finals.clear()

            def ok_agy_cli(**kwargs):
                return (0, "Peer review complete. @grok next.", "bbbbbbbb-cccc-dddd-eeee-ffffffffffff", "ok")

            agent.wake_agy_cli = ok_agy_cli
            item2 = dict(item)
            item2["mid"] = "m-agy-ok"
            agent._process_agy_collab_item(item2)
            assert posts[0][0] == "agy" and finals[0][0] == "agy"
            assert "Peer review" in finals[0][2]
            cid = c.get_agy_conversation_id(agent.load_state(), "room-collab-1")
            assert cid == "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
            IDENTITY_EVIDENCE.append(
                f"process_agy OK post={posts[0][0]} finalize={finals[0][0]} uuid_pin={cid}"
            )

            # dual auth helper resolves agy creds (pure, but used by operator)
            agy_creds = c.resolve_identity_creds(
                "agy",
                secrets={"RC_AGY_TOKEN": "tok-a", "RC_AGY_USER_ID": "uid-a"},
                env={"RC_AGY_USER": "agy"},
            )
            assert agy_creds.token == "tok-a" and agy_creds.user_id == "uid-a"
            IDENTITY_EVIDENCE.append("resolve_identity_creds agy token+uid ok")

            # static forbid MCP tool names in operator
            op_src = (WAKE_DIR / "rc_operator_agent.py").read_text(encoding="utf-8")
            for bad in ("agy_ask", "agy_ping", "agy_models", "agy_version"):
                assert bad not in op_src
            IDENTITY_EVIDENCE.append("operator source has zero MCP agy_* tokens")

            # --- grok-target collab drain: _process_pending_item collab=True ---
            # Must post/finalize as grok (not agy) and inject dual-account collab rules.
            grok_posts: list[tuple[str, str]] = []
            grok_finals: list[tuple[str, str, str]] = []
            captured_prompts: list[str] = []

            def grok_post_thinking(room_id: str, *, identity: str = "grok") -> str:
                grok_posts.append((identity, "…"))
                return "think-grok-bubble"

            def grok_finalize(
                room_id: str,
                mid: str,
                body: str,
                *,
                identity: str = "grok",
                thought_text: str = "",
                stream_throttle=None,
                **_kw,
            ) -> bool:
                grok_finals.append((identity, mid, body))
                return True

            def fake_wake_grok(prompt: str, **kwargs):
                captured_prompts.append(prompt)
                # Write reply file path from prompt inject (same contract as usability)
                for line in prompt.splitlines():
                    if line.startswith(
                        "Reply file (write final user-facing answer here): "
                    ):
                        path = line.split(": ", 1)[1].strip()
                        if path and path != "(none)":
                            Path(path).write_text(
                                "Grok collab reply with @agy handoff.",
                                encoding="utf-8",
                            )
                        break
                logp = agent.LOG_DIR / "wake-run-collab-grok.log"
                logp.write_text(
                    '{"stopReason":"EndTurn","sessionId":"gsess-1"}\n',
                    encoding="utf-8",
                )
                return (0, "gsess-1", logp, logp.read_text())

            agent.post_thinking_placeholder = grok_post_thinking
            agent.finalize_thinking_message = grok_finalize
            agent.update_thinking_meta = lambda *a, **k: True
            agent.wake_grok = fake_wake_grok
            agent.wake_agy_cli = lambda **k: (_ for _ in ()).throw(
                AssertionError("grok-target collab must not call wake_agy_cli")
            )
            agent._resolve_room_cwd_info = lambda *a, **k: (str(repo), "map")
            # Ensure inject template is loadable (shipped file or empty still gets footer)
            inject_path = WAKE_DIR / "collab_inject_grok.md"
            assert inject_path.is_file(), "collab_inject_grok.md must exist for FR-A42"

            grok_item = {
                "mid": "m-grok-collab",
                "rid": "room-collab-1",
                "room_name": "grok-agy-collab",
                "room_type": "p",
                "text": "@grok implement the falsifier that agy proposed",
                "author": "agy",
                "target": "grok",
                "collab": True,
                "u": {"username": "agy"},
                "ts": "2026-07-11T00:00:00.000Z",
            }
            # Drive the real grok branch of _process_pending_item (not only helpers)
            agent._process_pending_item(grok_item)

            assert grok_posts, "grok collab must post Thinking"
            assert grok_posts[0][0] == "grok", grok_posts
            assert grok_finals, "grok collab must finalize"
            assert grok_finals[0][0] == "grok", grok_finals
            assert grok_finals[0][1] == "think-grok-bubble"
            assert "Grok collab reply" in grok_finals[0][2]
            assert captured_prompts, "wake_grok must receive prompt"
            prompt = captured_prompts[0]
            # Collab inject fragment (FR-A42): no nested agy CLI; dual-account rules
            inject_markers = (
                "dual-peer" in prompt.lower()
                or "dual-account" in prompt.lower()
                or "Do not" in prompt
                or "agy CLI" in prompt
                or "shell out" in prompt.lower()
            )
            assert inject_markers, f"missing collab inject in prompt:\n{prompt[:800]}"
            assert "agy CLI" in prompt or "agy_*" in prompt or "MCP" in prompt
            # Must not be routed to agy process path
            assert "m-grok-collab" in (agent.load_state().get("processed_ids") or [])
            IDENTITY_EVIDENCE.append(
                f"process_grok_collab post_identity={grok_posts[0][0]} "
                f"finalize_identity={grok_finals[0][0]} mid={grok_finals[0][1]}"
            )
            IDENTITY_EVIDENCE.append(
                "process_grok_collab inject_has_anti_nested_agy="
                + str("agy CLI" in prompt or "shell out" in prompt.lower())
            )
            IDENTITY_EVIDENCE.append(
                f"process_grok_collab prompt_has_collab_status="
                f"{('auto_handoff' in prompt or 'Collab status' in prompt)}"
            )
            IDENTITY_EVIDENCE.append(
                "process_grok_collab did_not_call_wake_agy_cli=True"
            )

        record(
            "contract_identity_and_cli_helpers",
            True,
            f"{len(IDENTITY_EVIDENCE)} dual-identity/CLI observations",
        )
    except Exception as e:
        record(
            "contract_identity_and_cli_helpers",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_state_durability_reload() -> None:
    try:
        c = _load("rc_collab", WAKE_DIR / "rc_collab.py")
        wl = _load("wake_lib", WAKE_DIR / "wake_lib.py")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            state: dict = {"processed_ids": [], "rooms": {}}
            c.set_agy_conversation_id(state, "roomA", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
            c.ensure_collab_budget(state, "roomA", budget=100)
            for _ in range(5):
                c.record_collab_hop(state, "roomA", author="agy", target="grok")
            c.pause_auto_handoff(state, "roomA", "principal")
            # also pin grok session via wake_lib
            wl.set_room_session_id(state, "roomA", "grok-session-xyz")
            wl.save_state(state, path)

            loaded = wl.load_state(path)
            assert wl.get_room_session_id(loaded, "roomA") == "grok-session-xyz"
            collab = c.get_collab_room_state(loaded, "roomA")
            assert collab["conversation_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
            assert collab["hop_count_epoch"] == 5
            assert collab["auto_handoff"] is False
            assert collab["paused_reason"] == "principal"
            # soft budget: pins not cleared
            c.resume_auto_handoff(loaded, "roomA")
            assert c.get_agy_conversation_id(loaded, "roomA") == (
                "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
            )
        record("state_durability_reload", True)
    except Exception as e:
        record("state_durability_reload", False, repr(e) + traceback.format_exc())


def test_channel_profile_map_objects() -> None:
    try:
        c = _load("rc_collab", WAKE_DIR / "rc_collab.py")
        wl = _load("wake_lib", WAKE_DIR / "wake_lib.py")
        with tempfile.TemporaryDirectory() as td:
            mp = Path(td) / "channel_projects.json"
            mp.write_text(
                json.dumps(
                    {
                        "_comment": "test",
                        "Prime-Gap-Structure": "prime-gap-structure",
                        "grok-agy-collab": {
                            "cwd": "/Users/x/IdeaProjects/prime-gap-structure",
                            "mode": "agy-collab",
                            "hop_budget_epoch": 50,
                        },
                    }
                ),
                encoding="utf-8",
            )
            profs = c.load_channel_profiles(mp)
            assert "grok-agy-collab" in profs
            assert profs["grok-agy-collab"]["mode"] == "agy-collab"
            cmap = wl.load_channel_project_map(mp)
            assert cmap["Prime-Gap-Structure"] == "prime-gap-structure"
            assert cmap["grok-agy-collab"].endswith("prime-gap-structure")
            p = c.lookup_room_profile("grok-agy-collab", profs)
            assert p and p["mode"] == "agy-collab"
            assert c.profile_hop_budget(p) == 50
        record("channel_profile_map_objects", True)
    except Exception as e:
        record("channel_profile_map_objects", False, repr(e) + traceback.format_exc())


def test_collab_commands_known() -> None:
    try:
        cmd = _load("rc_commands", WAKE_DIR / "rc_commands.py")
        assert "collab" in cmd.KNOWN_CMDS
        assert "pause" in cmd.KNOWN_CMDS
        state: dict = {}
        r = cmd.dispatch_command(
            cmd.parse_command("/collab pause"),
            state=state,
            room_id="r1",
        )
        assert r.ok and "paused" in r.reply.lower()
        from rc_collab import get_collab_room_state

        assert get_collab_room_state(state, "r1")["paused_reason"] == "principal"
        r2 = cmd.dispatch_command(
            cmd.parse_command("/resume"),
            state=state,
            room_id="r1",
        )
        assert r2.ok and get_collab_room_state(state, "r1")["auto_handoff"] is True
        record("collab_commands_known", True)
    except Exception as e:
        record("collab_commands_known", False, repr(e) + traceback.format_exc())


def main() -> int:
    unit_tests = [
        test_master_flag_and_room_arm,
        test_mention_parse_structured_and_text,
        test_classify_routing_matrix,
        test_hop_budget_pause_fsm,
        test_agy_cli_plan_no_mcp,
        test_state_durability_reload,
        test_channel_profile_map_objects,
        test_collab_commands_known,
    ]
    contract_routing = [test_contract_routing_intake]
    contract_identity = [test_contract_identity_and_cli_helpers]

    for t in unit_tests + contract_routing + contract_identity:
        t()

    failed = [n for n, s, _ in RESULTS if s == "FAIL"]
    summary = f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed"
    print(summary)

    def _lines(names: set[str] | None = None) -> str:
        rows = []
        for n, s, d in RESULTS:
            if names is not None and n not in names:
                continue
            rows.append(f"[{s}] {n}" + (f" — {d}" if d else ""))
        return "\n".join(rows) + "\n"

    # Gate 1: pure unit suite
    unit_names = {
        "master_flag_and_room_arm",
        "mention_parse_structured_and_text",
        "classify_routing_matrix",
        "hop_budget_pause_fsm",
        "agy_cli_plan_no_mcp",
        "state_durability_reload",
        "channel_profile_map_objects",
        "collab_commands_known",
    }
    unit_text = _lines(unit_names) + f"unit_gate {summary}\n"
    (SCRATCH / "nf04-unit-mention-fsm.out").write_text(unit_text, encoding="utf-8")
    (SCRATCH / "nf04-state-durability.out").write_text(
        _lines({"state_durability_reload", "hop_budget_pause_fsm"})
        + "durability observations from pure FSM + reload\n",
        encoding="utf-8",
    )

    # Gate 2: distinct routing contract evidence (handle_principal_message)
    routing_body = _lines({"contract_routing_intake"})
    routing_body += "\n## dispatch observations (handle_principal_message → pending_wakes)\n"
    routing_body += "\n".join(f"- {e}" for e in ROUTING_EVIDENCE) + "\n"
    (SCRATCH / "nf04-contract-routing.out").write_text(routing_body, encoding="utf-8")
    print(f"wrote routing evidence n={len(ROUTING_EVIDENCE)}")

    # Gate 3: distinct identity/CLI contract evidence
    id_body = _lines({"contract_identity_and_cli_helpers"})
    id_body += "\n## dual-identity / agy CLI observations\n"
    id_body += "\n".join(f"- {e}" for e in IDENTITY_EVIDENCE) + "\n"
    (SCRATCH / "nf04-contract-identity-cli.out").write_text(id_body, encoding="utf-8")
    print(f"wrote identity evidence n={len(IDENTITY_EVIDENCE)}")

    # Full summary for regression artifact
    (SCRATCH / "nf04-all-results.out").write_text(_lines() + summary + "\n", encoding="utf-8")
    print(f"wrote {SCRATCH / 'nf04-unit-mention-fsm.out'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
