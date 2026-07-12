#!/usr/bin/env python3
"""
Tests for principal→grok DM wake probe helpers.

- Unit tests always run: they load the **shipped** wake_telemetry formatter and
  assert our FINAL_ERR classifier / streaming-meta filters match real operator
  text (not a reimplemented stub).
- Live REST probe is opt-in via RC_LIVE_DM_PROBE=1 (posts as principal, waits
  for a non-FINAL_ERR grok final). Default off to avoid production wake spam.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import rc_live_dm_probe_lib as probe  # noqa: E402


class TestShippedFinalErrClassification(unittest.TestCase):
    def test_shipped_format_final_err_emits_cancelled_shell(self) -> None:
        text = probe.final_err_template_text()
        self.assertIn("stopReason: Cancelled", text)
        self.assertIn("Wake ended without a reply file", text)
        self.assertIn("approval_mode: restricted", text)
        self.assertTrue(probe.is_final_err_body(text))

    def test_probe_ok_is_not_final_err(self) -> None:
        self.assertFalse(probe.is_final_err_body("PROBE_OK"))
        self.assertFalse(probe.is_final_err_body("Yes, I'm here."))

    def test_streaming_meta_filtered(self) -> None:
        meta = (
            "Working…\n"
            "• room: dm:principal\n"
            "• cwd: agency\n"
            "• mode: restricted\n"
            "• phase: running\n"
            "• elapsed: 15s\n"
            "• session: 019f48a5"
        )
        self.assertTrue(probe.is_streaming_meta_body(meta))
        self.assertTrue(probe.is_streaming_meta_body("Thinking…"))
        self.assertFalse(probe.is_streaming_meta_body("PROBE_OK"))


@unittest.skipUnless(
    os.environ.get("RC_LIVE_DM_PROBE", "").strip().lower() in ("1", "true", "yes"),
    "set RC_LIVE_DM_PROBE=1 to post a real principal DM (wakes production Grok)",
)
class TestLivePrincipalDmProbe(unittest.TestCase):
    def test_live_dm_probe_final_ok(self) -> None:
        self.assertTrue(
            probe.rc_reachable(),
            "Rocket.Chat not reachable at http://127.0.0.1:3000",
        )
        secrets = probe.DEFAULT_SECRETS
        self.assertTrue(secrets.is_file(), f"missing secrets: {secrets}")
        result = probe.run_live_dm_probe(timeout_s=300)
        send = result["send"]
        reply = result["reply"]
        self.assertTrue(send.get("success"))
        self.assertTrue(send.get("principal_message_id"))
        self.assertTrue(
            str(send.get("marker", "")).startswith("RC_PROBE_"),
            send.get("marker"),
        )
        self.assertFalse(reply.get("timed_out"), "timed out waiting for grok final")
        self.assertFalse(
            reply.get("is_final_err"),
            f"got FINAL_ERR shell: {reply.get('final_body')!r}",
        )
        self.assertTrue(reply.get("ok"), reply)
        body = (reply.get("final_body") or "").strip()
        self.assertTrue(body, "empty final body")
        # Prefer exact PROBE_OK; allow non-empty success if model paraphrases
        self.assertNotIn("stopReason: Cancelled", body)


if __name__ == "__main__":
    unittest.main()
