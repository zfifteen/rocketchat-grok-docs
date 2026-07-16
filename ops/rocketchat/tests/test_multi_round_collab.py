#!/usr/bin/env python3
"""
Multi-round RC collab — unit tests against pure helpers (+ optional runtime).

Pure policy tests default to the **repo/mirror** wake dir next to this file
(`…/ops/rocketchat/wake`). That keeps the docs-repo PR self-validating.

Runtime-only cases (wake_lib enqueue, four reply prompts, skill path) run when
`RC_TEST_RUNTIME=1` and the live agency tree is present.

Usage:
  python3 ops/rocketchat/tests/test_multi_round_collab.py
  RC_TEST_RUNTIME=1 python3 ~/.grok/agency/ops/rocketchat/tests/test_multi_round_collab.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import threading
import traceback
from pathlib import Path

_TEST_DIR = Path(__file__).resolve().parent
_MIRROR_WAKE = _TEST_DIR.parent / "wake"
_RUNTIME_WAKE = Path.home() / ".grok" / "agency" / "ops" / "rocketchat" / "wake"


def _env_truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


# Pure policy: prefer mirror adjacent to this test file (PR self-check).
if (_MIRROR_WAKE / "rc_multi_round_collab.py").is_file():
    POLICY_WAKE = _MIRROR_WAKE
else:
    POLICY_WAKE = _RUNTIME_WAKE

# Backward-compatible alias used in older call sites.
WAKE_DIR = POLICY_WAKE
RUNTIME_WAKE = _RUNTIME_WAKE
RC_TEST_RUNTIME = _env_truthy(os.environ.get("RC_TEST_RUNTIME"))

SCRATCH = Path(
    os.environ.get("RC_TEST_SCRATCH")
    or str(Path(tempfile.gettempdir()) / "rc-multi-round-tests")
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
    # Always reload pure modules under test
    if name in sys.modules:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# (a)(b) tag-to-talk enqueue — real should_enqueue_llm_wake
# ---------------------------------------------------------------------------


def test_untagged_channel_no_enqueue() -> None:
    if not RC_TEST_RUNTIME or not (RUNTIME_WAKE / "wake_lib.py").is_file():
        record("untagged_channel_no_enqueue", True, "SKIP (RC_TEST_RUNTIME!=1)")
        return
    try:
        wl = _load("wake_lib", RUNTIME_WAKE / "wake_lib.py")
        env = {
            "RC_REQUIRE_MENTION": "1",
            "RC_REQUIRE_MENTION_SCOPE": "channels",
            "RC_PEER_TAG_WAKE": "1",
        }
        msg = {
            "_id": "m-untagged",
            "msg": "team please continue the research without tags",
            "u": {"username": "principal"},
        }
        for op in ("grok", "hermes", "agy", "claude"):
            assert (
                wl.should_enqueue_llm_wake(
                    msg, operator=op, room_type="c", env=env
                )
                is False
            ), f"untagged should not wake {op}"
        # peer author untagged
        msg2 = {
            "_id": "m-peer-untagged",
            "msg": "here is my dig without tagging anyone",
            "u": {"username": "hermes"},
        }
        assert (
            wl.should_enqueue_llm_wake(
                msg2, operator="grok", room_type="p", env=env
            )
            is False
        )
        record("untagged_channel_no_enqueue", True)
    except Exception as e:
        record("untagged_channel_no_enqueue", False, repr(e) + traceback.format_exc())


def test_peer_tag_enqueues_target() -> None:
    if not RC_TEST_RUNTIME or not (RUNTIME_WAKE / "wake_lib.py").is_file():
        record("peer_tag_enqueues_target", True, "SKIP (RC_TEST_RUNTIME!=1)")
        return
    try:
        wl = _load("wake_lib", RUNTIME_WAKE / "wake_lib.py")
        env = {
            "RC_REQUIRE_MENTION": "1",
            "RC_REQUIRE_MENTION_SCOPE": "channels",
            "RC_PEER_TAG_WAKE": "1",
        }
        msg = {
            "_id": "m-tag-hermes",
            "msg": "@hermes dig deeper on residual honesty",
            "mentions": [{"username": "hermes"}],
            "u": {"username": "grok"},
        }
        assert (
            wl.should_enqueue_llm_wake(
                msg, operator="hermes", room_type="c", env=env
            )
            is True
        )
        assert (
            wl.should_enqueue_llm_wake(
                msg, operator="agy", room_type="c", env=env
            )
            is False
        )
        assert (
            wl.should_enqueue_llm_wake(
                msg, operator="grok", room_type="c", env=env
            )
            is False
        )  # self never; author is grok tagging hermes
        # text-only mention without structured mentions[]
        msg_txt = {
            "_id": "m-tag-claude",
            "msg": "please @claude pressure-test falsifiability",
            "u": {"username": "grok"},
        }
        assert (
            wl.should_enqueue_llm_wake(
                msg_txt, operator="claude", room_type="p", env=env
            )
            is True
        )
        record("peer_tag_enqueues_target", True)
    except Exception as e:
        record("peer_tag_enqueues_target", False, repr(e) + traceback.format_exc())


# ---------------------------------------------------------------------------
# (c)(d) assigner resolution + return-notify text
# ---------------------------------------------------------------------------


def test_return_notify_targets_assigner() -> None:
    try:
        m = _load("rc_multi_round_collab", POLICY_WAKE / "rc_multi_round_collab.py")
        t = m.resolve_return_notify_target(
            "claude", completing_operator="hermes"
        )
        assert t == "claude", t
        t2 = m.resolve_return_notify_target(
            "grok", completing_operator="agy"
        )
        assert t2 == "grok", t2
        # emit allowed for peer with known assigner
        assert (
            m.should_emit_return_notify(
                operator="hermes",
                assigner="grok",
                room_type="c",
                lead_done=False,
                reply_body="Finished inventory note.",
                env={"RC_MULTI_ROUND_COLLAB": "1"},
            )
            is True
        )
        text = m.build_return_notify_text(
            target="grok",
            completing_operator="hermes",
            source_mid="abc123",
            room_name="Prime-Gap-Structure",
            summary="Inventory merged.",
        )
        assert "@grok" in text
        assert m.COLLAB_RETURN_MARKER in text
        assert "hermes" in text
        assert "abc123" in text
        record("return_notify_targets_assigner", True, text[:80])
    except Exception as e:
        record(
            "return_notify_targets_assigner", False, repr(e) + traceback.format_exc()
        )


def test_return_notify_unknown_assigner_targets_grok() -> None:
    try:
        m = _load("rc_multi_round_collab", POLICY_WAKE / "rc_multi_round_collab.py")
        assert m.resolve_return_notify_target(None, completing_operator="agy") == "grok"
        assert m.resolve_return_notify_target("", completing_operator="claude") == "grok"
        assert (
            m.resolve_return_notify_target("principal", completing_operator="hermes")
            == "grok"
        )
        assert (
            m.resolve_return_notify_target("some-human", completing_operator="agy")
            == "grok"
        )
        record("return_notify_unknown_assigner_targets_grok", True)
    except Exception as e:
        record(
            "return_notify_unknown_assigner_targets_grok",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_principal_direct_peer_no_return_notify() -> None:
    """Principal → @peer is solo; must not collab-return to grok (2026-07-15 bug)."""
    try:
        m = _load("rc_multi_round_collab", POLICY_WAKE / "rc_multi_round_collab.py")
        env = {"RC_MULTI_ROUND_COLLAB": "1"}
        body = (
            "Your Mersenne generator lives under research/09-exponents as PGSMPG v0.1."
        )
        # Direct principal → hermes
        assert (
            m.should_emit_return_notify(
                operator="hermes",
                assigner="principal",
                room_type="c",
                lead_done=False,
                reply_body=body,
                trigger_text="@hermes Find my Mersenne prime generator and explain how it works",
                env=env,
            )
            is False
        )
        # Missing / non-bot assigner
        assert (
            m.should_emit_return_notify(
                operator="agy",
                assigner=None,
                room_type="p",
                lead_done=False,
                reply_body=body,
                env=env,
            )
            is False
        )
        assert (
            m.should_emit_return_notify(
                operator="claude",
                assigner="some-human",
                room_type="c",
                lead_done=False,
                reply_body=body,
                env=env,
            )
            is False
        )
        # Lead → peer collab hop still emits
        assert (
            m.should_emit_return_notify(
                operator="hermes",
                assigner="grok",
                room_type="c",
                lead_done=False,
                reply_body=body,
                trigger_text="@hermes dig residuals for the collab",
                env=env,
            )
            is True
        )
        # Peer → peer hop still emits
        assert (
            m.should_emit_return_notify(
                operator="agy",
                assigner="hermes",
                room_type="c",
                lead_done=False,
                reply_body=body,
                trigger_text="@agy continue the residual table",
                env=env,
            )
            is True
        )
        record("principal_direct_peer_no_return_notify", True)
    except Exception as e:
        record(
            "principal_direct_peer_no_return_notify",
            False,
            repr(e) + traceback.format_exc(),
        )


# ---------------------------------------------------------------------------
# (e) lead DONE suppresses return-notify
# ---------------------------------------------------------------------------


def test_lead_done_suppresses_return_notify() -> None:
    try:
        m = _load("rc_multi_round_collab", POLICY_WAKE / "rc_multi_round_collab.py")
        assert (
            m.should_emit_return_notify(
                operator="hermes",
                assigner="grok",
                room_type="c",
                lead_done=True,
                reply_body="More work.",
                env={"RC_MULTI_ROUND_COLLAB": "1"},
            )
            is False
        )
        assert m.should_suppress_return_notify_for_lead_done(lead_done=True) is True
        assert m.should_suppress_return_notify_for_lead_done(lead_done=False) is False
        # Lead never emits return-notify
        assert (
            m.should_emit_return_notify(
                operator="grok",
                assigner="principal",
                room_type="p",
                lead_done=False,
                reply_body="Here is synthesis @hermes do X",
                env={"RC_MULTI_ROUND_COLLAB": "1"},
            )
            is False
        )
        # Plain-language DONE detection (whole-collab closure)
        assert m.reply_declares_lead_done(
            "This concludes the collab: residual honesty is the schedule driver."
        )
        assert m.reply_declares_lead_done("We're done — final conclusion: goal met.")
        assert m.reply_declares_lead_done("Goal met. No further handoffs.")
        # Close-out with incidental peer @tag still counts as DONE (anti-loop state)
        assert m.reply_declares_lead_done(
            "Collaboration complete. Copy @agy. No further handoffs."
        )
        assert not m.reply_declares_lead_done(
            "Here is more analysis; @hermes please continue."
        )
        # Mid-collab English must NOT mark DONE (open assign)
        assert not m.reply_declares_lead_done(
            "We're done with inventory; @hermes dig residuals"
        )
        assert not m.reply_declares_lead_done(
            "This concludes my analysis of section 1; @agy continue"
        )
        assert not m.reply_declares_lead_done(
            "We're done with the first pass on the note."
        )
        # Peer standing-by must not return-notify
        assert (
            m.should_emit_return_notify(
                operator="agy",
                assigner="grok",
                room_type="p",
                lead_done=False,
                reply_body="Acknowledged @grok. Standing by for the next goal.",
                env={"RC_MULTI_ROUND_COLLAB": "1"},
            )
            is False
        )
        # Lead skips LLM on collab-return after DONE
        assert (
            m.should_skip_lead_llm_on_collab_return(
                operator="grok",
                trigger_text="@grok collab-return from `agy` · mid=x",
                lead_done=True,
            )
            is True
        )
        assert (
            m.should_skip_lead_llm_on_collab_return(
                operator="grok",
                trigger_text="@grok collab-return from `agy` · mid=x",
                lead_done=False,
            )
            is False
        )
        record("lead_done_suppresses_return_notify", True)
    except Exception as e:
        record(
            "lead_done_suppresses_return_notify",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_collab_return_trigger_does_not_emit_return_notify() -> None:
    """Peer wake on collab-return must not re-post return-notify (no peer↔peer ping-pong)."""
    try:
        m = _load("rc_multi_round_collab", POLICY_WAKE / "rc_multi_round_collab.py")
        trigger = (
            "@hermes collab-return from `agy` · mid=`abc123` room=Prime-Gap-Structure. "
            "Peer finished a collab wake — continue."
        )
        assert m.message_is_collab_return(trigger) is True
        assert (
            m.should_emit_return_notify(
                operator="hermes",
                assigner="agy",
                room_type="c",
                lead_done=False,
                reply_body="Acknowledged return; no further peer ping.",
                trigger_text=trigger,
                env={"RC_MULTI_ROUND_COLLAB": "1"},
            )
            is False
        )
        # Real work tag (not collab-return) still emits
        assert (
            m.should_emit_return_notify(
                operator="hermes",
                assigner="grok",
                room_type="c",
                lead_done=False,
                reply_body="Finished dig on residuals.",
                trigger_text="@hermes dig deeper on residual honesty",
                env={"RC_MULTI_ROUND_COLLAB": "1"},
            )
            is True
        )
        # Case-insensitive marker in longer body
        assert (
            m.should_emit_return_notify(
                operator="agy",
                assigner="hermes",
                room_type="p",
                lead_done=False,
                reply_body="ok",
                trigger_text="@agy COLLAB-RETURN from hermes mid=x",
                env={"RC_MULTI_ROUND_COLLAB": "1"},
            )
            is False
        )
        record("collab_return_trigger_does_not_emit_return_notify", True)
    except Exception as e:
        record(
            "collab_return_trigger_does_not_emit_return_notify",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_shared_state_lead_done_roundtrip() -> None:
    try:
        m = _load("rc_multi_round_collab", POLICY_WAKE / "rc_multi_round_collab.py")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "multi_round_collab_state.json"
            rid = "room-test-1"
            assert m.room_lead_done(rid, path=path) is False
            m.mark_lead_done(rid, at="2026-07-14T00:00:00Z", mid="m1", path=path)
            assert m.room_lead_done(rid, path=path) is True
            # return-notify of return-notify must not clear
            cleared = m.maybe_clear_lead_done_on_new_work(
                room_id=rid,
                author="hermes",
                operator="grok",
                trigger_text="@grok collab-return from hermes · mid=x",
                path=path,
            )
            assert cleared is False
            assert m.room_lead_done(rid, path=path) is True
            # lead close-out with @peer must NOT clear (loop bug)
            cleared_lead = m.maybe_clear_lead_done_on_new_work(
                room_id=rid,
                author="grok",
                operator="grok",
                trigger_text="Collaboration complete. Copy @agy. Goal met.",
                path=path,
            )
            assert cleared_lead is False
            assert m.room_lead_done(rid, path=path) is True
            # principal loop diagnostic must not clear
            cleared_diag = m.maybe_clear_lead_done_on_new_work(
                room_id=rid,
                author="principal",
                operator="grok",
                trigger_text="@grok Is your collab stuck in a loop?",
                path=path,
            )
            assert cleared_diag is False
            # principal new work clears
            cleared2 = m.maybe_clear_lead_done_on_new_work(
                room_id=rid,
                author="principal",
                operator="grok",
                trigger_text="@grok new goal: reverse the analysis",
                path=path,
            )
            assert cleared2 is True
            assert m.room_lead_done(rid, path=path) is False
        record("shared_state_lead_done_roundtrip", True)
    except Exception as e:
        record(
            "shared_state_lead_done_roundtrip",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_skip_return_notify_when_reply_already_tags_target() -> None:
    try:
        m = _load("rc_multi_round_collab", POLICY_WAKE / "rc_multi_round_collab.py")
        assert (
            m.should_emit_return_notify(
                operator="agy",
                assigner="grok",
                room_type="c",
                lead_done=False,
                reply_body="Done. @grok synthesis ready when you are.",
                env={"RC_MULTI_ROUND_COLLAB": "1"},
            )
            is False
        )
        record("skip_return_notify_when_reply_already_tags_target", True)
    except Exception as e:
        record(
            "skip_return_notify_when_reply_already_tags_target",
            False,
            repr(e) + traceback.format_exc(),
        )


# ---------------------------------------------------------------------------
# Playbook wired into all four reply surfaces
# ---------------------------------------------------------------------------


def test_playbook_wired_all_four_reply_surfaces() -> None:
    try:
        m = _load("rc_multi_round_collab", POLICY_WAKE / "rc_multi_round_collab.py")
        pb_path = m.playbook_path(wake_dir=POLICY_WAKE)
        assert pb_path.is_file(), f"missing playbook {pb_path}"
        body = pb_path.read_text(encoding="utf-8")
        assert "Grok" in body or "grok" in body
        assert "return-notify" in body.lower() or "return-notify" in body
        assert "lead" in body.lower()

        inject = m.playbook_inject_block(
            env={"RC_MULTI_ROUND_COLLAB": "1"}, wake_dir=POLICY_WAKE
        )
        assert "Multi-round Rocket.Chat collab playbook" in inject
        assert len(inject) > 200

        # Disabled master flag → empty inject
        assert (
            m.playbook_inject_block(
                env={"RC_MULTI_ROUND_COLLAB": "0"}, wake_dir=POLICY_WAKE
            )
            == ""
        )

        # Reply-prompt surfaces + skill live only in runtime ops
        if RC_TEST_RUNTIME and RUNTIME_WAKE.is_dir():
            marker = "Multi-round Rocket.Chat collab"
            for name in (
                "reply_prompt.txt",
                "hermes_reply_prompt.txt",
                "agy_reply_prompt.txt",
                "claude_reply_prompt.txt",
            ):
                p = RUNTIME_WAKE / name
                assert p.is_file(), name
                text = p.read_text(encoding="utf-8")
                assert marker in text, f"{name} missing collab section"
                assert "return-notify" in text or "playbook" in text.lower(), name

            skill = (
                Path.home() / ".grok" / "skills" / "rc-multi-round-collab" / "SKILL.md"
            )
            assert skill.is_file(), skill
            skill_txt = skill.read_text(encoding="utf-8")
            assert "RC_MULTI_ROUND_COLLAB_PLAYBOOK.md" in skill_txt
        record("playbook_wired_all_four_reply_surfaces", True)
    except Exception as e:
        record(
            "playbook_wired_all_four_reply_surfaces",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_dm_no_return_notify() -> None:
    try:
        m = _load("rc_multi_round_collab", POLICY_WAKE / "rc_multi_round_collab.py")
        assert (
            m.should_emit_return_notify(
                operator="hermes",
                assigner="principal",
                room_type="d",
                lead_done=False,
                reply_body="DM answer",
                env={"RC_MULTI_ROUND_COLLAB": "1"},
            )
            is False
        )
        record("dm_no_return_notify", True)
    except Exception as e:
        record("dm_no_return_notify", False, repr(e) + traceback.format_exc())


# ---------------------------------------------------------------------------
# Issue #2 P0/P1 hardening
# ---------------------------------------------------------------------------


def test_principal_multi_mention_lead_only() -> None:
    """Principal @grok+peers → only lead enqueues; direct @peer still wakes peer."""
    try:
        m = _load("rc_multi_round_collab", POLICY_WAKE / "rc_multi_round_collab.py")
        env = {"RC_MULTI_ROUND_COLLAB": "1", "RC_MULTI_ROUND_PRINCIPAL_LEAD_ONLY": "1"}
        multi = (
            "@grok @hermes @agy @claude four-agent collab: each report readiness"
        )
        # Peers must skip when principal multi-@ includes lead
        for peer in ("hermes", "agy", "claude"):
            assert (
                m.principal_multi_mention_lead_only(
                    author="principal",
                    operator=peer,
                    text=multi,
                    room_type="c",
                    env=env,
                )
                is True
            ), peer
        # Lead may enqueue
        assert (
            m.principal_multi_mention_lead_only(
                author="principal",
                operator="grok",
                text=multi,
                room_type="c",
                env=env,
            )
            is False
        )
        # Direct principal → single peer (no @grok) still allowed
        assert (
            m.principal_multi_mention_lead_only(
                author="principal",
                operator="hermes",
                text="@hermes dig residual honesty alone",
                room_type="c",
                env=env,
            )
            is False
        )
        # Peer-authored tags unchanged
        assert (
            m.principal_multi_mention_lead_only(
                author="grok",
                operator="hermes",
                text="@hermes dig residuals",
                room_type="c",
                env=env,
            )
            is False
        )
        # Kill-switch off restores concurrent peer wakes
        assert (
            m.principal_multi_mention_lead_only(
                author="principal",
                operator="hermes",
                text=multi,
                room_type="c",
                env={"RC_MULTI_ROUND_COLLAB": "1", "RC_MULTI_ROUND_PRINCIPAL_LEAD_ONLY": "0"},
            )
            is False
        )
        # DM out of scope
        assert (
            m.principal_multi_mention_lead_only(
                author="principal",
                operator="hermes",
                text=multi,
                room_type="d",
                env=env,
            )
            is False
        )
        record("principal_multi_mention_lead_only", True)
    except Exception as e:
        record(
            "principal_multi_mention_lead_only",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_quality_gate_empty_failure_no_return_notify() -> None:
    """Open-collab empty/error templates must not spam lead with collab-return."""
    try:
        m = _load("rc_multi_round_collab", POLICY_WAKE / "rc_multi_round_collab.py")
        env = {"RC_MULTI_ROUND_COLLAB": "1"}
        empty_templates = [
            "Could not complete this reply. Send another message to retry.",
            "Wake did not produce a reply file (rc: 1).",
            "Wake failed. stopReason: unknown (first attempt ended incomplete).",
            "",
            "ok",  # too short
        ]
        for body in empty_templates:
            assert (
                m.should_emit_return_notify(
                    operator="claude",
                    assigner="grok",
                    room_type="c",
                    lead_done=False,
                    reply_body=body,
                    trigger_text="@claude pressure-test falsifiability",
                    phase="FINAL_ERR",
                    rc=1,
                    env=env,
                )
                is False
            ), repr(body[:40])
        # Useful delivery still emits
        assert (
            m.should_emit_return_notify(
                operator="claude",
                assigner="grok",
                room_type="c",
                lead_done=False,
                reply_body=(
                    "Falsifiability pressure-test complete. "
                    "Three residual claims remain open; see checklist."
                ),
                trigger_text="@claude pressure-test falsifiability",
                phase="FINAL",
                rc=0,
                env=env,
            )
            is True
        )
        # Structured blocked failure may still notify (diagnostics present)
        assert m.reply_body_useful_for_return_notify(
            "Blocked because quota exhausted. Reassign to hermes next. What failed: API 429.",
            phase="FINAL_ERR",
            rc=1,
        )
        record("quality_gate_empty_failure_no_return_notify", True)
    except Exception as e:
        record(
            "quality_gate_empty_failure_no_return_notify",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_epoch_lifecycle_and_footer() -> None:
    """Collab epoch open/deliver + optional peer footer parse."""
    try:
        m = _load("rc_multi_round_collab", POLICY_WAKE / "rc_multi_round_collab.py")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "multi_round_collab_state.json"
            rid = "room-epoch-1"
            ep = m.open_collab_epoch(
                rid,
                assignees=["hermes", "agy", "claude"],
                opened_by="grok",
                mid="kickoff-1",
                path=path,
            )
            assert ep and ep.startswith("e")
            assert m.room_epoch(rid, path=path) == ep
            assert m.room_lead_done(rid, path=path) is False
            assert m.assignee_already_delivered(rid, "hermes", path=path) is False
            m.record_assignee_delivered(rid, "hermes", mid="h1", path=path)
            assert m.assignee_already_delivered(rid, "hermes", path=path) is True
            assert m.assignee_already_delivered(rid, "agy", path=path) is False
            text = m.build_return_notify_text(
                target="grok",
                completing_operator="hermes",
                source_mid="h1",
                room_name="general",
                summary="Inventory done.",
                epoch=ep,
            )
            assert f"epoch=`{ep}`" in text
            assert m.COLLAB_RETURN_MARKER in text
            # Soft footer
            footer = m.parse_peer_delivery_footer(
                "Delivery complete.\n\nSTATUS: done\nFOR: @grok\nEPOCH: " + ep
            )
            assert footer is not None
            assert footer.get("status", "").lower().startswith("done")
            assert "grok" in footer.get("for", "").lower()
            assert footer.get("epoch") == ep
            # Health snapshot
            snap = m.health_multi_round_fields(rid, path=path)
            assert snap["multi_round_enabled"] is True
            assert snap["room"]["epoch"] == ep
            assert "hermes" in snap["room"]["delivered"]
        record("epoch_lifecycle_and_footer", True)
    except Exception as e:
        record(
            "epoch_lifecycle_and_footer",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_playbook_opening_collab_section() -> None:
    """Playbook documents principal open = @grok only (issue #2 Phase 1)."""
    try:
        m = _load("rc_multi_round_collab", POLICY_WAKE / "rc_multi_round_collab.py")
        body = m.playbook_path(wake_dir=POLICY_WAKE).read_text(encoding="utf-8")
        assert "Opening a collab" in body or "opening a collab" in body.lower()
        assert "@grok" in body
        assert "lead only" in body.lower() or "only the lead" in body.lower() or "tag only" in body.lower()
        record("playbook_opening_collab_section", True)
    except Exception as e:
        record(
            "playbook_opening_collab_section",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_message_is_collab_return_template_only() -> None:
    """Prose mentioning collab-return must not match operator template matcher."""
    try:
        m = _load("rc_multi_round_collab", POLICY_WAKE / "rc_multi_round_collab.py")
        assert m.message_is_collab_return(
            "@grok collab-return from `hermes` · mid=`abc` room=general."
        )
        assert m.message_is_collab_return(
            "@agy COLLAB-RETURN from hermes mid=x"
        )
        assert not m.message_is_collab_return(
            "Do not emit collab-return until the peer delivers real work."
        )
        assert not m.message_is_collab_return(
            "The collab-return marker is used by the operator."
        )
        assert not m.message_is_collab_return("@hermes dig residuals")
        record("message_is_collab_return_template_only", True)
    except Exception as e:
        record(
            "message_is_collab_return_template_only",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_shared_state_rmw_atomic_concurrent() -> None:
    """Two concurrent delivered stamps both survive (flock critical section)."""
    try:
        m = _load("rc_multi_round_collab", POLICY_WAKE / "rc_multi_round_collab.py")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "multi_round_collab_state.json"
            rid = "room-rmw-1"
            m.open_collab_epoch(
                rid, assignees=["hermes", "agy"], opened_by="grok", path=path
            )
            barrier = threading.Barrier(2)
            errors: list[BaseException] = []

            def stamp(who: str, mid: str) -> None:
                try:
                    barrier.wait(timeout=5)
                    m.record_assignee_delivered(rid, who, mid=mid, path=path)
                except BaseException as e:  # noqa: BLE001 — surface in assert
                    errors.append(e)

            t1 = threading.Thread(target=stamp, args=("hermes", "h1"))
            t2 = threading.Thread(target=stamp, args=("agy", "a1"))
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)
            assert not errors, errors
            assert m.assignee_already_delivered(rid, "hermes", path=path)
            assert m.assignee_already_delivered(rid, "agy", path=path)
            # Reuse epoch without wipe
            ep1 = m.room_epoch(rid, path=path)
            ep2 = m.open_collab_epoch(
                rid, assignees=["claude"], opened_by="grok", path=path
            )
            assert ep2 == ep1
            assert m.assignee_already_delivered(rid, "hermes", path=path)
            # force opens new epoch and clears delivered
            ep3 = m.open_collab_epoch(
                rid, assignees=["hermes"], force=True, path=path
            )
            assert ep3 != ep1
            assert not m.assignee_already_delivered(rid, "hermes", path=path)
        record("shared_state_rmw_atomic_concurrent", True)
    except Exception as e:
        record(
            "shared_state_rmw_atomic_concurrent",
            False,
            repr(e) + traceback.format_exc(),
        )


def main() -> int:
    print("=== test_multi_round_collab ===")
    print(f"POLICY_WAKE={POLICY_WAKE}")
    print(f"RUNTIME_WAKE={RUNTIME_WAKE}")
    print(f"RC_TEST_RUNTIME={RC_TEST_RUNTIME}")
    print(f"SCRATCH={SCRATCH}")
    tests = [
        test_untagged_channel_no_enqueue,
        test_peer_tag_enqueues_target,
        test_return_notify_targets_assigner,
        test_return_notify_unknown_assigner_targets_grok,
        test_principal_direct_peer_no_return_notify,
        test_lead_done_suppresses_return_notify,
        test_collab_return_trigger_does_not_emit_return_notify,
        test_shared_state_lead_done_roundtrip,
        test_skip_return_notify_when_reply_already_tags_target,
        test_playbook_wired_all_four_reply_surfaces,
        test_dm_no_return_notify,
        test_principal_multi_mention_lead_only,
        test_quality_gate_empty_failure_no_return_notify,
        test_epoch_lifecycle_and_footer,
        test_playbook_opening_collab_section,
        test_message_is_collab_return_template_only,
        test_shared_state_rmw_atomic_concurrent,
    ]
    for t in tests:
        t()
    failed = [r for r in RESULTS if r[1] != "PASS"]
    lines = [f"{s}\t{n}\t{d}" for n, s, d in RESULTS]
    out = SCRATCH / "collab-tests-results.tsv"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    if failed:
        print("FAILED:", ", ".join(n for n, _, _ in failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
