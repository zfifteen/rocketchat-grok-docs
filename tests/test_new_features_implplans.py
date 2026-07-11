#!/usr/bin/env python3
"""
Structural tests for the new-features implementation-plan layer (per-feature bundles).
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEW_FEATURES = ROOT / "new-features"

FEATURE_BUNDLES = (
    "01-true-voice-in-rc-call",
    "02-streaming-thinking-telemetry",
    "03-phone-control-plane",
)

MIN_BYTES = 7_000

SECTION_PATTERNS = {
    "overview_or_goals": re.compile(
        r"(?im)^#{1,3}\s+.*(overview|goal)",
    ),
    "phased_work": re.compile(
        r"(?im)^#{1,3}\s+.*(phased work|phase |implementation phase)",
    ),
    "integration_or_deps": re.compile(
        r"(?im)^#{1,3}\s+.*(integrat|dependenc|file and integration)",
    ),
    "rollout_or_flags": re.compile(
        r"(?im)^#{1,3}\s+.*(rollout|feature flag|rollback)",
    ),
    "validation": re.compile(
        r"(?im)^#{1,3}\s+.*(validation|test-plan mapping|NF-TP)",
    ),
    "risks": re.compile(
        r"(?im)^#{1,3}\s+.*(risk|ops impact)",
    ),
}

SUBJECTS = {
    "01-true-voice-in-rc-call": [
        re.compile(r"voice|LiveKit|Call", re.I),
        re.compile(r"NF-IP-01|NF-SPEC-01|NF-TP-01"),
        re.compile(r"RC_CALL_MEDIA_BACKEND|rollback|Playwright", re.I),
    ],
    "02-streaming-thinking-telemetry": [
        re.compile(r"stream|Thinking", re.I),
        re.compile(r"NF-IP-02|NF-SPEC-02|NF-TP-02"),
        re.compile(r"RC_WAKE_STREAM|stopReason|chat\.update", re.I),
    ],
    "03-phone-control-plane": [
        re.compile(r"control plane|/status|slash", re.I),
        re.compile(r"NF-IP-03|NF-SPEC-03|NF-TP-03"),
        re.compile(r"elevation|/admin once|RC_CONTROL_PLANE", re.I),
    ],
}

GROUNDING = (
    "rc_operator_agent",
    "wake_lib",
    "approval",
    "rollout",
    "rollback",
)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _ip(slug: str) -> Path:
    return NEW_FEATURES / slug / "implementation-plan.md"


class TestNewFeaturesImplPlansPackage(unittest.TestCase):
    def test_three_plans_depth_in_bundles(self) -> None:
        for slug in FEATURE_BUNDLES:
            path = _ip(slug)
            self.assertTrue(path.is_file(), f"missing {path}")
            self.assertGreaterEqual(
                path.stat().st_size,
                MIN_BYTES,
                f"{slug}/implementation-plan.md too small",
            )

    def test_index_and_hubs_describe_impl_plans(self) -> None:
        index = _read(NEW_FEATURES / "README.md")
        self.assertRegex(index, r"(?i)implementation.?plan")
        self.assertRegex(
            index,
            r"(?i)out of scope|documentation only|no runtime",
        )
        self.assertRegex(index, r"(?i)ship order|cross-feature|2.*3.*1|2 → 3 → 1")
        self.assertRegex(index, r"(?i)voice")
        self.assertRegex(index, r"(?i)stream")
        self.assertRegex(index, r"(?i)control plane")
        for slug in FEATURE_BUNDLES:
            self.assertIn(slug, index)
            hub = _read(NEW_FEATURES / slug / "README.md")
            self.assertIn("implementation-plan.md", hub)

    def test_section_classes(self) -> None:
        for slug in FEATURE_BUNDLES:
            text = _read(_ip(slug))
            for label, pat in SECTION_PATTERNS.items():
                self.assertIsNotNone(
                    pat.search(text),
                    f"{slug}/implementation-plan.md missing {label}",
                )
            self.assertRegex(text, r"(?i)effort|eng-day")

    def test_subjects(self) -> None:
        for slug, pats in SUBJECTS.items():
            text = _read(_ip(slug))
            for pat in pats:
                self.assertIsNotNone(
                    pat.search(text),
                    f"{slug}/implementation-plan.md missing {pat.pattern}",
                )

    def test_links_research_spec_testplan(self) -> None:
        for slug in FEATURE_BUNDLES:
            self.assertTrue((NEW_FEATURES / slug / "spec.md").is_file())
            self.assertTrue((NEW_FEATURES / slug / "test-plan.md").is_file())
            self.assertTrue((NEW_FEATURES / slug / "research.md").is_file())
            text = _read(_ip(slug))
            self.assertIn("spec.md", text)
            self.assertIn("test-plan.md", text)
            self.assertIn("research.md", text)

    def test_grounding(self) -> None:
        blob = "\n".join(_read(_ip(s)) for s in FEATURE_BUNDLES)
        blob += "\n" + _read(NEW_FEATURES / "README.md")
        missing = [t for t in GROUNDING if t.lower() not in blob.lower()]
        self.assertEqual(missing, [], missing)

    def test_parent_readme_links_impl_plans(self) -> None:
        parent = _read(NEW_FEATURES / "README.md")
        self.assertIn("implementation-plan.md", parent)
        for slug in FEATURE_BUNDLES:
            self.assertIn(slug, parent)

    def test_prior_artifacts_remain(self) -> None:
        for slug in FEATURE_BUNDLES:
            self.assertTrue((NEW_FEATURES / slug / "research.md").is_file())
            self.assertTrue((NEW_FEATURES / slug / "spec.md").is_file())
            self.assertTrue((NEW_FEATURES / slug / "test-plan.md").is_file())


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        TestNewFeaturesImplPlansPackage
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
