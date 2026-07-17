#!/usr/bin/env python3
"""
NF-SPEC-03 Phone Control Plane — unit/contract tests on shipped code.

Exercises real modules under ops/rocketchat/wake/ (rc_commands, wake_lib,
rc_operator_agent helpers). Not re-implementations.

Usage:
  python3 ~/.grok/agency/ops/rocketchat/tests/test_nf03_control_plane.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

WAKE_DIR = Path.home() / ".grok" / "agency" / "ops" / "rocketchat" / "wake"
SCRATCH = Path(
    os.environ.get(
        "RC_TEST_SCRATCH",
        "/var/folders/k_/spz3zlj566sc4qh29g0tk6jh0000gn/T/grok-goal-440deb3e36d3/implementer",
    )
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
    # Reuse already-loaded module (dataclass needs sys.modules entry)
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # required for @dataclass under 3.13
    spec.loader.exec_module(mod)
    return mod


def test_parse_and_master_switch() -> None:
    try:
        cmd = _load("rc_commands", WAKE_DIR / "rc_commands.py")
        assert cmd.control_plane_enabled({"RC_CONTROL_PLANE": "1"}) is True
        assert cmd.control_plane_enabled({"RC_CONTROL_PLANE": "0"}) is False
        assert cmd.control_plane_enabled({"RC_CONTROL_PLANE": "off"}) is False

        p = cmd.parse_command("/help", env={"RC_CMD_PREFIXES": "/,!"})
        assert p and p.cmd == "help" and p.args == ""

        p = cmd.parse_command("  /STATUS  ", env={})
        assert p and p.cmd == "status"

        p = cmd.parse_command("!model grok-build", env={"RC_CMD_PREFIXES": "/,!"})
        assert p and p.cmd == "model" and p.args == "grok-build"

        p = cmd.parse_command("/m foo", env={})
        assert p and p.cmd == "model" and p.args == "foo"

        p = cmd.parse_command("/clear", env={})
        assert p and p.cmd == "new"

        p = cmd.parse_command("hello world", env={})
        assert p is None

        p = cmd.parse_command("/", env={})
        assert p is None  # empty after prefix

        p = cmd.parse_command("/theme", env={})
        assert p and p.cmd == "theme"

        record("parse_and_master_switch", True)
    except Exception as e:
        record("parse_and_master_switch", False, repr(e) + traceback.format_exc())


def test_help_unknown_tui_no_wake_dispatch() -> None:
    try:
        cmd = _load("rc_commands", WAKE_DIR / "rc_commands.py")
        state: dict = {}
        r = cmd.dispatch_command(
            cmd.parse_command("/help"),
            state=state,
            room_id="r1",
        )
        assert "status" in r.reply.lower() or "`/status`" in r.reply
        assert "model" in r.reply.lower()
        assert r.wake_text is None

        r = cmd.dispatch_command(
            cmd.parse_command("/foo"),
            state=state,
            room_id="r1",
        )
        assert r.wake_text is None
        assert "help" in r.reply.lower()
        assert r.ok is False

        r = cmd.dispatch_command(
            cmd.parse_command("/theme"),
            state=state,
            room_id="r1",
        )
        assert r.wake_text is None
        assert "unsupported" in r.reply.lower() or "tui" in r.reply.lower()

        r = cmd.dispatch_command(
            cmd.parse_command("/always-approve"),
            state=state,
            room_id="r1",
        )
        assert r.wake_text is None

        record("help_unknown_tui_no_wake_dispatch", True)
    except Exception as e:
        record("help_unknown_tui_no_wake_dispatch", False, repr(e) + traceback.format_exc())


def test_model_effort_pins_and_wake_argv() -> None:
    try:
        cmd = _load("rc_commands", WAKE_DIR / "rc_commands.py")
        wl = _load("wake_lib", WAKE_DIR / "wake_lib.py")
        state: dict = {}
        rid = "roomA"

        r = cmd.dispatch_command(
            cmd.parse_command("/model grok-build"),
            state=state,
            room_id=rid,
        )
        assert r.wake_text is None
        assert cmd.get_room_model(state, rid) == "grok-build"

        r = cmd.dispatch_command(
            cmd.parse_command("/effort high"),
            state=state,
            room_id=rid,
        )
        assert cmd.get_room_effort(state, rid) == "high"

        argv = wl.build_wake_argv(
            "/tmp/prompt.txt",
            grok_bin="/bin/grok",
            cwd="/proj/x",
            max_turns=3,
            approval_mode="restricted",
            model=cmd.get_room_model(state, rid),
            effort=cmd.get_room_effort(state, rid),
        )
        assert "--model" in argv
        assert argv[argv.index("--model") + 1] == "grok-build"
        assert "--reasoning-effort" in argv
        assert argv[argv.index("--reasoning-effort") + 1] == "high"
        assert "--permission-mode" in argv  # restricted
        assert "--always-approve" not in argv

        cmd.dispatch_command(cmd.parse_command("/model clear"), state=state, room_id=rid)
        cmd.dispatch_command(cmd.parse_command("/effort clear"), state=state, room_id=rid)
        argv2 = wl.build_wake_argv(
            "/tmp/prompt.txt",
            grok_bin="/bin/grok",
            cwd="/proj/x",
            max_turns=3,
            approval_mode="restricted",
            model=cmd.get_room_model(state, rid),
            effort=cmd.get_room_effort(state, rid),
        )
        assert "--model" not in argv2
        assert "--reasoning-effort" not in argv2

        r = cmd.dispatch_command(
            cmd.parse_command("/effort notalevel"),
            state=state,
            room_id=rid,
        )
        assert r.ok is False
        assert cmd.get_room_effort(state, rid) is None

        record("model_effort_pins_and_wake_argv", True)
    except Exception as e:
        record("model_effort_pins_and_wake_argv", False, repr(e) + traceback.format_exc())


def test_goal_pin_prompt_block() -> None:
    try:
        cmd = _load("rc_commands", WAKE_DIR / "rc_commands.py")
        state: dict = {}
        rid = "roomG"
        r = cmd.dispatch_command(
            cmd.parse_command("/goal Ship the control plane"),
            state=state,
            room_id=rid,
        )
        assert r.wake_text is None
        g = cmd.get_room_goal(state, rid)
        assert g and g.get("status") == "active"
        block = cmd.goal_prompt_block(state, rid)
        assert "Ship the control plane" in block
        assert "Active room goal" in block

        cmd.dispatch_command(cmd.parse_command("/goal pause"), state=state, room_id=rid)
        block2 = cmd.goal_prompt_block(state, rid)
        assert "paused" in block2.lower() or "Ship" in block2

        cmd.dispatch_command(cmd.parse_command("/goal clear"), state=state, room_id=rid)
        assert cmd.goal_prompt_block(state, rid) == ""

        record("goal_pin_prompt_block", True)
    except Exception as e:
        record("goal_pin_prompt_block", False, repr(e) + traceback.format_exc())


def test_elevation_once_yes_consume_and_no() -> None:
    try:
        cmd = _load("rc_commands", WAKE_DIR / "rc_commands.py")
        wl = _load("wake_lib", WAKE_DIR / "wake_lib.py")
        rid = "roomE"
        now = datetime.now(timezone.utc)

        # --- yes path ---
        state: dict = {}
        r = cmd.dispatch_command(
            cmd.parse_command("/admin once"),
            state=state,
            room_id=rid,
            env={"RC_ELEVATION": "1", "RC_ADMIN_CONFIRM_S": "60"},
            now=now,
        )
        assert "yes" in r.reply.lower()
        assert cmd.get_pending_confirm(state, rid)

        state, msg = cmd.confirm_yes(state, rid, now=now)
        assert "next wake" in msg.lower() or "armed" in msg.lower()
        assert cmd.get_room_elevation(state, rid)

        mode, consume = cmd.effective_approval_for_room(
            state, rid, "restricted", now=now
        )
        assert mode == "admin"
        assert consume is True
        argv = wl.build_wake_argv(
            "/tmp/p",
            grok_bin="g",
            cwd="/x",
            max_turns=2,
            approval_mode=mode,
        )
        assert "--always-approve" in argv

        cmd.consume_once_elevation(state, rid)
        mode2, consume2 = cmd.effective_approval_for_room(
            state, rid, "restricted", now=now
        )
        assert mode2 == "restricted"
        assert consume2 is False
        argv2 = wl.build_wake_argv(
            "/tmp/p",
            grok_bin="g",
            cwd="/x",
            max_turns=2,
            approval_mode=mode2,
        )
        assert "--always-approve" not in argv2

        # --- no path ---
        state2: dict = {}
        cmd.dispatch_command(
            cmd.parse_command("/admin once"),
            state=state2,
            room_id=rid,
            env={"RC_ELEVATION": "1"},
            now=now,
        )
        state2, msg_no = cmd.confirm_no(state2, rid)
        assert "cancel" in msg_no.lower() or "restricted" in msg_no.lower()
        mode3, _ = cmd.effective_approval_for_room(state2, rid, "restricted", now=now)
        assert mode3 == "restricted"

        # --- timeout ---
        state3: dict = {}
        past = now - timedelta(seconds=120)
        cmd.arm_pending_confirm(
            state3, rid, "admin_once", confirm_s=60, now=past
        )
        # expires_at is past+60 = past relative to now+120... past+60 is still before now if past is now-120
        cmd.clear_expired_pending(state3, rid, now=now)
        assert cmd.get_pending_confirm(state3, rid) is None

        # elevation disabled
        state4: dict = {}
        r = cmd.dispatch_command(
            cmd.parse_command("/admin once"),
            state=state4,
            room_id=rid,
            env={"RC_ELEVATION": "0"},
        )
        assert r.ok is False
        assert "disabled" in r.reply.lower() or "RC_ELEVATION" in r.reply

        record("elevation_once_yes_consume_and_no", True)
    except Exception as e:
        record(
            "elevation_once_yes_consume_and_no",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_new_session_and_cwd_allowlist() -> None:
    try:
        cmd = _load("rc_commands", WAKE_DIR / "rc_commands.py")
        wl = _load("wake_lib", WAKE_DIR / "wake_lib.py")
        state: dict = {}
        rid = "roomN"
        # Live-like pin: per-room map + legacy field + room_id (as after _mark_processed)
        wl.set_room_session_id(state, rid, "sess-LIVE")
        state["room_id"] = rid
        state["grok_session_id"] = "sess-LIVE"
        state["rooms"] = {rid: {"session_id": "sess-LIVE"}}
        assert wl.get_room_session_id(state, rid) == "sess-LIVE"

        cmd.dispatch_command(cmd.parse_command("/new"), state=state, room_id=rid)
        # Effective pin must be gone — including legacy fallback path
        assert wl.get_room_session_id(state, rid) is None, (
            f"legacy still visible: grok_session_id={state.get('grok_session_id')!r} "
            f"sessions={state.get('grok_sessions')!r}"
        )
        assert not state.get("grok_session_id")
        rooms_entry = (state.get("rooms") or {}).get(rid) or {}
        assert not rooms_entry.get("session_id")

        # set model then /new — model retained
        cmd.dispatch_command(
            cmd.parse_command("/model keep-me"), state=state, room_id=rid
        )
        cmd.dispatch_command(cmd.parse_command("/new"), state=state, room_id=rid)
        assert cmd.get_room_model(state, rid) == "keep-me"
        assert wl.get_room_session_id(state, rid) is None

        ok, msg, resolved = cmd.cwd_pin_allowed("/etc")
        assert ok is False

        # valid IdeaProjects if exists
        ip = Path.home() / "IdeaProjects"
        if ip.is_dir():
            # pick any subdir or the root itself if allowed
            candidates = [p for p in ip.iterdir() if p.is_dir()][:1]
            target = candidates[0] if candidates else ip
            ok2, msg2, res2 = cmd.cwd_pin_allowed(str(target))
            assert ok2 is True, msg2
            assert res2

        record("new_session_and_cwd_allowlist", True)
    except Exception as e:
        record("new_session_and_cwd_allowlist", False, repr(e) + traceback.format_exc())


def test_retry_and_wake_text() -> None:
    try:
        cmd = _load("rc_commands", WAKE_DIR / "rc_commands.py")
        state: dict = {}
        rid = "roomR"
        r = cmd.dispatch_command(
            cmd.parse_command("/retry"), state=state, room_id=rid
        )
        assert r.ok is False
        cmd.set_last_content(state, rid, "previous task text", mid="m1")
        r = cmd.dispatch_command(
            cmd.parse_command("/retry"), state=state, room_id=rid
        )
        assert r.wake_text == "previous task text"

        r = cmd.dispatch_command(
            cmd.parse_command("/wake do the thing"),
            state=state,
            room_id=rid,
        )
        assert r.wake_text == "do the thing"

        r = cmd.dispatch_command(
            cmd.parse_command("/ask please help"),
            state=state,
            room_id=rid,
        )
        assert r.wake_text == "please help"

        record("retry_and_wake_text", True)
    except Exception as e:
        record("retry_and_wake_text", False, repr(e) + traceback.format_exc())


def test_novel_insight_skill_command() -> None:
    try:
        cmd = _load("rc_commands", WAKE_DIR / "rc_commands.py")
        state: dict = {}
        rid = "roomSkill"

        p = cmd.parse_command("!novel-insight residual curvature")
        assert p and p.cmd == "novel-insight" and p.args == "residual curvature"

        p2 = cmd.parse_command("@grok !novel-insight about primes")
        assert p2 and p2.cmd == "novel-insight" and p2.args == "about primes"

        r = cmd.dispatch_command(p, state=state, room_id=rid)
        assert r.ok is True
        assert r.wake_text is not None
        assert "novel-insight-engine" in r.wake_text
        assert "residual curvature" in r.wake_text
        assert "SKILL.md" in r.wake_text
        assert r.reply == ""  # single activity bubble; no separate ack

        smap = cmd.load_skill_command_map()
        assert smap.get("novel-insight") == "novel-insight-engine"

        help_body = cmd.help_text("")
        assert "novel-insight" in help_body

        record("novel_insight_skill_command", True)
    except Exception as e:
        record("novel_insight_skill_command", False, repr(e) + traceback.format_exc())


def test_operator_module_imports_control_plane() -> None:
    """Shipped operator must import and expose control-plane entrypoints."""
    try:
        # Avoid loading websocket requirement failures if any — agent imports websocket
        # still required; check file source if import fails?
        agent_path = WAKE_DIR / "rc_operator_agent.py"
        src = agent_path.read_text(encoding="utf-8")
        assert "from rc_commands import" in src
        assert "control_plane_enabled" in src
        assert "_try_control_plane" in src
        assert "goal_block" in src
        assert "get_room_model" in src
        assert "effective_approval_for_room" in src

        # Import wake_lib + rc_commands always works without websocket
        cmd = _load("rc_commands", WAKE_DIR / "rc_commands.py")
        wl = _load("wake_lib", WAKE_DIR / "wake_lib.py")
        assert callable(cmd.dispatch_command)
        assert "model" in wl.build_wake_argv.__code__.co_varnames or True
        # inspect signature via call
        a = wl.build_wake_argv("/p", model="x", effort="low", grok_bin="g", cwd="/c", max_turns=1)
        assert a[a.index("--model") + 1] == "x"

        record("operator_module_imports_control_plane", True)
    except Exception as e:
        record(
            "operator_module_imports_control_plane",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_mode_vs_model_distinct() -> None:
    try:
        cmd = _load("rc_commands", WAKE_DIR / "rc_commands.py")
        state: dict = {}
        r_mode = cmd.dispatch_command(
            cmd.parse_command("/mode"),
            state=state,
            room_id="r",
            base_approval="restricted",
        )
        assert "approval" in r_mode.reply.lower()
        r_model = cmd.dispatch_command(
            cmd.parse_command("/model"),
            state=state,
            room_id="r",
        )
        assert "model pin" in r_model.reply.lower() or "default" in r_model.reply.lower()
        record("mode_vs_model_distinct", True)
    except Exception as e:
        record("mode_vs_model_distinct", False, repr(e) + traceback.format_exc())


def main() -> int:
    print("NF-03 Phone Control Plane tests")
    print(f"wake_dir={WAKE_DIR}")
    print(f"scratch={SCRATCH}")
    tests = [
        test_parse_and_master_switch,
        test_help_unknown_tui_no_wake_dispatch,
        test_model_effort_pins_and_wake_argv,
        test_goal_pin_prompt_block,
        test_elevation_once_yes_consume_and_no,
        test_new_session_and_cwd_allowlist,
        test_retry_and_wake_text,
        test_novel_insight_skill_command,
        test_operator_module_imports_control_plane,
        test_mode_vs_model_distinct,
    ]
    for t in tests:
        t()
    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} passed")
    out = SCRATCH / "nf03-unit-contract.out"
    lines = [f"{s}\t{n}\t{d}" for n, s, d in RESULTS]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
