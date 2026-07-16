#!/usr/bin/env python3
"""Pure tests for B3/B10 proposed wake predicates (+ B1 adversarial)."""

from __future__ import annotations

import traceback
from pathlib import Path

import b3_b10_wake_predicates as p

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    extra = f" — {detail}" if detail and not ok else ""
    print(f"  {status}  {name}{extra}")


def test_b3_activity_placeholder_no_enqueue() -> None:
    try:
        for body in ("…", "Thinking...", "", "...", " "):
            msg = {
                "_id": f"act-{hash(body) & 0xFFFF}",
                "msg": body,
                "u": {"username": "grok"},
            }
            for op in ("hermes", "agy", "claude", "grok"):
                assert (
                    p.should_enqueue_llm_wake_proposed(
                        msg, operator=op, room_type="c"
                    )
                    is False
                ), (body, op)
        record("b3_activity_placeholder_no_enqueue", True)
    except Exception as e:
        record("b3_activity_placeholder_no_enqueue", False, repr(e) + traceback.format_exc())


def test_b3_stream_thoughts_with_prose_at_no_enqueue() -> None:
    try:
        msg = {
            "_id": "stream-1",
            "msg": (
                "*Thoughts*\n\nI will assign peers next. "
                "Need @hermes on B3 and @agy on B2 eventually."
            ),
            "u": {"username": "grok"},
        }
        assert (
            p.should_enqueue_llm_wake_proposed(msg, operator="hermes", room_type="c")
            is False
        )
        assert (
            p.should_enqueue_llm_wake_proposed(msg, operator="agy", room_type="c")
            is False
        )
        record("b3_stream_thoughts_with_prose_at_no_enqueue", True)
    except Exception as e:
        record(
            "b3_stream_thoughts_with_prose_at_no_enqueue",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_b10_prose_at_bot_no_enqueue() -> None:
    try:
        cases = [
            (
                "Hermes is clarifying that the principal's @hermes direct requests "
                "shouldn't trigger multi-agent collab noise via return-notify.",
                "hermes",
            ),
            (
                "Fixed. Hermes correctly stood down; peer ops restart for @claude too.",
                "claude",
            ),
            (
                "Do not emit collab-return until the peer delivers; mention of @agy is prose.",
                "agy",
            ),
        ]
        for body, op in cases:
            msg = {"_id": f"prose-{op}", "msg": body, "u": {"username": "grok"}}
            assert (
                p.should_enqueue_llm_wake_proposed(msg, operator=op, room_type="c")
                is False
            ), body
        # Literal path still true for comparison baseline
        msg = {
            "_id": "lit",
            "msg": "the principal's @hermes direct requests",
            "u": {"username": "grok"},
        }
        assert p.message_mentions_operator_literal(msg, "hermes") is True
        assert (
            p.message_mentions_operator_intentional(
                msg, "hermes", author="grok"
            )
            is False
        )
        record("b10_prose_at_bot_no_enqueue", True)
    except Exception as e:
        record("b10_prose_at_bot_no_enqueue", False, repr(e) + traceback.format_exc())


def test_b10_intentional_assign_still_enqueues() -> None:
    try:
        msg = {
            "_id": "assign-1",
            "msg": (
                "@hermes please dig **B3** and **B10**:\n"
                "1. Trace should_enqueue_llm_wake\n"
                "2. Propose minimal gate"
            ),
            "u": {"username": "grok"},
            "mentions": [{"username": "hermes"}],
        }
        assert (
            p.should_enqueue_llm_wake_proposed(msg, operator="hermes", room_type="c")
            is True
        )
        assert (
            p.should_enqueue_llm_wake_proposed(msg, operator="agy", room_type="c")
            is False
        )
        # collab-return template
        cr = {
            "_id": "cr-1",
            "msg": "@grok collab-return from `hermes` · mid=`abc` room=docs.",
            "u": {"username": "hermes"},
        }
        assert (
            p.should_enqueue_llm_wake_proposed(cr, operator="grok", room_type="c")
            is True
        )
        record("b10_intentional_assign_still_enqueues", True)
    except Exception as e:
        record(
            "b10_intentional_assign_still_enqueues",
            False,
            repr(e) + traceback.format_exc(),
        )


def test_principal_direct_and_channel_tag() -> None:
    try:
        # Principal free-wake in DM
        dm = {
            "_id": "dm1",
            "msg": "you up?",
            "u": {"username": "principal"},
        }
        assert (
            p.should_enqueue_llm_wake_proposed(dm, operator="hermes", room_type="d")
            is True
        )
        # Channel requires @ for principal
        ch = {
            "_id": "ch1",
            "msg": "you up?",
            "u": {"username": "principal"},
        }
        assert (
            p.should_enqueue_llm_wake_proposed(ch, operator="hermes", room_type="c")
            is False
        )
        ch2 = {
            "_id": "ch2",
            "msg": "@hermes you up?",
            "u": {"username": "principal"},
        }
        assert (
            p.should_enqueue_llm_wake_proposed(ch2, operator="hermes", room_type="c")
            is True
        )
        record("principal_direct_and_channel_tag", True)
    except Exception as e:
        record("principal_direct_and_channel_tag", False, repr(e) + traceback.format_exc())


def test_b1_glued_multi_mention_lead_only() -> None:
    try:
        glued = "@grok@hermes@agy four-agent collab please"
        # Text-only classic extract loses peers after first token boundary quirks
        classic = p.extract_mention_usernames(glued)
        assert "grok" in classic
        # Glued recovery sees peers
        recovered = p._extract_glued_mentions(glued)
        assert {"grok", "hermes", "agy"} <= recovered, recovered

        # Without structured mentions, proposed lead-only still suppresses *all*
        # peers when lead+any peer appear (same as live lead-only: peers wait
        # for fan-out even if not named in the multi-@ seed).
        for peer in ("hermes", "agy", "claude"):
            skip = p.principal_multi_mention_lead_only_proposed(
                author="principal",
                operator=peer,
                text=glued,
                room_type="c",
            )
            assert skip is True, peer

        # Structured mentions + spaced text (happy path)
        spaced = "@grok @hermes @claude four-agent collab"
        msg = {
            "msg": spaced,
            "mentions": [
                {"username": "grok"},
                {"username": "hermes"},
                {"username": "claude"},
            ],
        }
        assert (
            p.principal_multi_mention_lead_only_proposed(
                author="principal",
                operator="hermes",
                text=spaced,
                room_type="c",
                msg=msg,
            )
            is True
        )
        assert (
            p.principal_multi_mention_lead_only_proposed(
                author="principal",
                operator="grok",
                text=spaced,
                room_type="c",
                msg=msg,
            )
            is False
        )
        # Direct principal → peer only
        assert (
            p.principal_multi_mention_lead_only_proposed(
                author="principal",
                operator="hermes",
                text="@hermes dig residuals alone",
                room_type="c",
            )
            is False
        )
        # Hole demo: structured both, text only @grok (autocomplete dual)
        hole_msg = {
            "msg": "@grok please fan out",
            "mentions": [{"username": "grok"}, {"username": "hermes"}],
        }
        assert (
            p.principal_multi_mention_lead_only_proposed(
                author="principal",
                operator="hermes",
                text=hole_msg["msg"],
                room_type="c",
                msg=hole_msg,
            )
            is True
        ), "structured peer+lead must suppress peer"
        record("b1_glued_multi_mention_lead_only", True)
    except Exception as e:
        record("b1_glued_multi_mention_lead_only", False, repr(e) + traceback.format_exc())


def test_self_and_processed() -> None:
    try:
        msg = {
            "_id": "self1",
            "msg": "@hermes dig",
            "u": {"username": "hermes"},
        }
        assert (
            p.should_enqueue_llm_wake_proposed(msg, operator="hermes", room_type="c")
            is False
        )
        msg2 = {
            "_id": "done1",
            "msg": "@hermes dig",
            "u": {"username": "grok"},
        }
        assert (
            p.should_enqueue_llm_wake_proposed(
                msg2,
                operator="hermes",
                room_type="c",
                processed_ids=["done1"],
            )
            is False
        )
        record("self_and_processed", True)
    except Exception as e:
        record("self_and_processed", False, repr(e) + traceback.format_exc())


def main() -> int:
    print("B3/B10/B1 pure predicate tests")
    tests = [
        test_b3_activity_placeholder_no_enqueue,
        test_b3_stream_thoughts_with_prose_at_no_enqueue,
        test_b10_prose_at_bot_no_enqueue,
        test_b10_intentional_assign_still_enqueues,
        test_principal_direct_and_channel_tag,
        test_b1_glued_multi_mention_lead_only,
        test_self_and_processed,
    ]
    for t in tests:
        t()
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = sum(1 for _, ok, _ in RESULTS if not ok)
    print(f"\n{passed}/{len(RESULTS)} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
