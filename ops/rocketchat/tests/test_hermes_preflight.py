#!/usr/bin/env python3
"""Unit tests for hermes_preflight (no network, no RC)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

WAKE = Path(__file__).resolve().parents[1] / "wake"
sys.path.insert(0, str(WAKE))

import hermes_preflight as hp  # noqa: E402


class HermesPreflightTests(unittest.TestCase):
    def test_extract_revenue_paths(self):
        text = "Refresh revenue-day1-thread-watch.md and revenue-aug1-countdown-residual.md"
        toks = hp.extract_path_tokens(text)
        self.assertIn("revenue-day1-thread-watch.md", toks)
        self.assertIn("revenue-aug1-countdown-residual.md", toks)

    def test_secret_paths_blocked(self):
        p = Path("/Users/velocityworks/.grok/agency/secrets/rocketchat.env")
        self.assertTrue(hp.is_secret_path(p))

    def test_build_block_with_temp_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = root / "revenue-test-file.md"
            f.write_text("# Hello test\n\nbody\n", encoding="utf-8")
            logd = root / "logs"
            logd.mkdir()
            (logd / "wake-reply-1.txt").write_text("STATUS: done\nPASS\n", encoding="utf-8")

            # Monkeypatch home allowlist by using absolute path token + project_cwd
            block = hp.build_preflight_block(
                f"Please check {f.name}",
                project_cwd=str(root),
                room_id="rid",
                room_name="Agency",
                log_dir=logd,
                enabled=True,
            )
            self.assertIn("Hermes preflight pack", block)
            self.assertIn("revenue-test-file.md", block)
            self.assertIn("Hello test", block)
            self.assertIn("wake-reply-1.txt", block)

    def test_disabled_env(self):
        block = hp.build_preflight_block(
            "revenue-day1-thread-watch.md",
            enabled=False,
        )
        self.assertEqual(block, "")

    def test_hermes_enable_detection(self):
        self.assertTrue(
            hp.hermes_preflight_enabled_for_process(
                operator="hermes",
                wake_backend="hermes",
            )
        )
        self.assertFalse(
            hp.hermes_preflight_enabled_for_process(
                operator="grok",
                wake_backend="grok",
                prompt_template="reply_prompt.txt",
            )
        )


if __name__ == "__main__":
    unittest.main()
