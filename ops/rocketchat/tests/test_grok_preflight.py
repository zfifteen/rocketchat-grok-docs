#!/usr/bin/env python3
"""Unit tests for grok_preflight (no network, no RC)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

WAKE = Path(__file__).resolve().parents[1] / "wake"
sys.path.insert(0, str(WAKE))

import grok_preflight as gp  # noqa: E402


class GrokPreflightTests(unittest.TestCase):
    def test_secret_paths_blocked(self):
        p = Path("/Users/velocityworks/.grok/agency/secrets/rocketchat.env")
        self.assertTrue(gp.is_secret_path(p))

    def test_enable_detection_lead_only(self):
        self.assertTrue(
            gp.grok_preflight_enabled_for_process(
                operator="grok",
                wake_backend="",
                prompt_template="reply_prompt.txt",
            )
        )
        self.assertFalse(
            gp.grok_preflight_enabled_for_process(
                operator="hermes",
                wake_backend="hermes",
                prompt_template="hermes_reply_prompt.txt",
            )
        )
        self.assertFalse(
            gp.grok_preflight_enabled_for_process(
                operator="feynman",
                wake_backend="hermes",
                prompt_template="feynman_reply_prompt.txt",
            )
        )

    def test_disabled_env(self):
        block = gp.build_lead_preflight_block("hello", enabled=False)
        self.assertEqual(block, "")

    def test_build_block_with_fixtures(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_md = root / "STATE.md"
            state_md.write_text(
                "# Agency STATE\n\n"
                "**Last updated:** 2026-07-17 test\n"
                "**Active milestone:** Financial OpEx break-even (Phase A)\n"
                "**Phase A dual-track:** Hold Stripe **2026-08-01**.\n\n"
                "## 4. Next session first action (OPERATOR-OWNED)\n\n"
                "**Immediate (Phase A money):** Hold public sell until Stripe.\n"
                "hermes seat BLOCKED: invalid_grant refresh token revoked.\n",
                encoding="utf-8",
            )
            residual = root / "revenue-aug1-countdown-residual.md"
            residual.write_text(
                "# residual\n\nStill open\nG1 Stripe\nG5b heat\n2026-08-01\n",
                encoding="utf-8",
            )

            collab_path = root / "multi_round_collab_state.json"
            collab_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "rooms": {
                            "room-current": {
                                "epoch": "e-test-1",
                                "lead_done": False,
                                "assignees": ["hermes", "agy", "claude"],
                                "delivered": {
                                    "agy": {
                                        "mid": "mid1",
                                        "ts": "2026-07-17T12:00:00+00:00",
                                    }
                                },
                            },
                            "room-other": {
                                "epoch": "e-test-2",
                                "lead_done": False,
                                "assignees": ["feynman", "nie"],
                                "delivered": {
                                    "feynman": {
                                        "mid": "mid2",
                                        "ts": "2026-07-17T11:00:00+00:00",
                                    }
                                },
                            },
                            "room-done": {
                                "epoch": "e-done",
                                "lead_done": True,
                                "assignees": ["agy"],
                                "delivered": {
                                    "agy": {
                                        "mid": "mid3",
                                        "ts": "2026-07-16T00:00:00+00:00",
                                    }
                                },
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            op_state = root / "state.json"
            op_state.write_text(
                json.dumps(
                    {
                        "last_wake_at": "2026-07-17T10:00:00+00:00",
                        "rooms": {
                            "room-other": {
                                "cwd": str(root / "agency-project"),
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            logd = root / "logs"
            logd.mkdir()
            (logd / "wake-reply-fixture.txt").write_text(
                "Lead synthesis complete for test.\n",
                encoding="utf-8",
            )

            hermes_logs = root / "hermes-logs"
            hermes_logs.mkdir()
            (hermes_logs / "wake-run-1.log").write_text(
                "error: invalid_grant refresh token revoked\n",
                encoding="utf-8",
            )

            # Point delta roots via monkeypatch of path helpers
            orig_agency = gp.agency_home
            orig_wake = gp.wake_dir
            orig_idea = gp.idea_agency
            orig_glog = gp.grok_log_dir
            try:
                gp.agency_home = lambda: root  # type: ignore
                gp.wake_dir = lambda: root  # type: ignore
                gp.idea_agency = lambda: root  # type: ignore
                gp.grok_log_dir = lambda: logd  # type: ignore

                block = gp.build_lead_preflight_block(
                    f"Please check {residual.name}",
                    project_cwd=str(root),
                    room_id="room-current",
                    room_name="dm:principal",
                    last_wake_at="2026-07-17T10:00:00+00:00",
                    collab_state_path=collab_path,
                    operator_state_path=op_state,
                    state_md_path=state_md,
                    log_dir=logd,
                    hermes_log_dir=hermes_logs,
                    enabled=True,
                )
            finally:
                gp.agency_home = orig_agency  # type: ignore
                gp.wake_dir = orig_wake  # type: ignore
                gp.idea_agency = orig_idea  # type: ignore
                gp.grok_log_dir = orig_glog  # type: ignore

            self.assertIn("Grok lead preflight pack", block)
            self.assertIn("Active milestone", block)
            self.assertIn("lead_done=False", block)
            self.assertIn("claude", block.lower())
            self.assertIn("agy", block)
            self.assertIn("room-other", block.lower() or block)
            # room-done should not appear as open
            self.assertNotIn("e-done", block)
            self.assertIn("revenue-aug1-countdown-residual.md", block)
            self.assertIn("hermes", block.lower())
            self.assertIn("invalid_grant", block.lower())
            self.assertIn("wake-reply-fixture.txt", block)
            self.assertLessEqual(len(block), gp.MAX_INJECT_CHARS + 50)

    def test_collab_lead_action_when_all_delivered(self):
        collab = {
            "rooms": {
                "r1": {
                    "epoch": "e1",
                    "lead_done": False,
                    "assignees": ["hermes", "agy"],
                    "delivered": {
                        "hermes": {"mid": "a", "ts": "2026-07-17T01:00:00+00:00"},
                        "agy": {"mid": "b", "ts": "2026-07-17T02:00:00+00:00"},
                    },
                }
            }
        }
        lines = gp.this_room_collab_lines("r1", "Agency", collab)
        joined = "\n".join(lines)
        self.assertIn("synthesize", joined.lower())

    def test_write_audit(self):
        with tempfile.TemporaryDirectory() as td:
            p = gp.write_preflight_audit(
                "## test\n",
                wake_id="abc123",
                log_dir=td,
            )
            self.assertIsNotNone(p)
            assert p is not None
            self.assertTrue(p.is_file())
            self.assertIn("preflight-lead", p.name)


if __name__ == "__main__":
    unittest.main()
