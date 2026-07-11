#!/usr/bin/env python3
"""
Structural tests for the new-features test-plan layer (per-feature bundles).

Exercises real on-disk artifacts under new-features/<slug>/test-plan.md.
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

MIN_PLAN_BYTES = 6_000

SECTION_PATTERNS = {
    "scope_or_traceability": re.compile(
        r"(?im)^#{1,3}\s+.*(scope|traceab)",
    ),
    "strategy_or_layers": re.compile(
        r"(?im)^#{1,3}\s+.*(strateg|layer)",
    ),
    "test_cases": re.compile(
        r"(?im)^#{1,3}\s+.*(test case|concrete test)",
    ),
    "edge_cases": re.compile(
        r"(?im)^#{1,3}\s+.*(edge case|negative|failure case)",
    ),
    "pass_fail_or_exit": re.compile(
        r"(?im)^#{1,3}\s+.*(pass\s*/\s*fail|exit criteria|pass / fail)",
    ),
}

SUBJECTS = {
    "01-true-voice-in-rc-call": [
        re.compile(r"voice|Call|LiveKit", re.I),
        re.compile(r"NF-TP-01|NF-SPEC-01"),
        re.compile(r"hangup|barge-in|spawn|media", re.I),
    ],
    "02-streaming-thinking-telemetry": [
        re.compile(r"stream|Thinking", re.I),
        re.compile(r"NF-TP-02|NF-SPEC-02"),
        re.compile(r"stopReason|chat\.update|FINAL_ERR", re.I),
    ],
    "03-phone-control-plane": [
        re.compile(r"control plane|slash|/status", re.I),
        re.compile(r"NF-TP-03|NF-SPEC-03"),
        re.compile(r"admin once|elevation|/cancel", re.I),
    ],
}

GROUNDING = (
    "rc_operator_agent",
    "chat.update",
    "Thinking",
    "approval",
    "edge",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _tp(slug: str) -> Path:
    return NEW_FEATURES / slug / "test-plan.md"


class TestNewFeaturesTestPlansPackage(unittest.TestCase):
    def test_three_plans_depth_in_bundles(self) -> None:
        for slug in FEATURE_BUNDLES:
            path = _tp(slug)
            self.assertTrue(path.is_file(), f"missing {path}")
            size = path.stat().st_size
            self.assertGreaterEqual(
                size,
                MIN_PLAN_BYTES,
                f"{slug}/test-plan.md too small ({size})",
            )

    def test_index_and_bundle_hubs_link_test_plans(self) -> None:
        index = _read(NEW_FEATURES / "README.md")
        self.assertRegex(index, r"(?i)test-plan|test plan")
        self.assertRegex(
            index,
            r"(?i)out of scope|documentation only|test-planning|no runtime",
        )
        for slug in FEATURE_BUNDLES:
            self.assertIn(slug, index)
            hub = _read(NEW_FEATURES / slug / "README.md")
            self.assertIn("test-plan.md", hub)

    def test_section_classes_including_edge_cases(self) -> None:
        for slug in FEATURE_BUNDLES:
            text = _read(_tp(slug))
            for label, pat in SECTION_PATTERNS.items():
                self.assertIsNotNone(
                    pat.search(text),
                    f"{slug}/test-plan.md missing section: {label}",
                )
            edge_ids = re.findall(r"\bE-[A-Z]+-\d+\b", text)
            self.assertGreaterEqual(
                len(edge_ids),
                8,
                f"{slug} should list many edge cases (found {len(edge_ids)})",
            )

    def test_subjects(self) -> None:
        index = _read(NEW_FEATURES / "README.md")
        self.assertRegex(index, r"(?i)voice")
        self.assertRegex(index, r"(?i)stream")
        self.assertRegex(index, r"(?i)control plane|slash")
        for slug, pats in SUBJECTS.items():
            text = _read(_tp(slug))
            for pat in pats:
                self.assertIsNotNone(
                    pat.search(text),
                    f"{slug}/test-plan.md missing {pat.pattern}",
                )

    def test_links_to_spec_and_research(self) -> None:
        for slug in FEATURE_BUNDLES:
            self.assertTrue((NEW_FEATURES / slug / "spec.md").is_file())
            self.assertTrue((NEW_FEATURES / slug / "research.md").is_file())
            text = _read(_tp(slug))
            self.assertIn("spec.md", text)
            self.assertIn("research.md", text)

    def test_grounding_terms(self) -> None:
        blob = "\n".join(_read(_tp(s)) for s in FEATURE_BUNDLES)
        blob += "\n" + _read(NEW_FEATURES / "README.md")
        missing = [t for t in GROUNDING if t.lower() not in blob.lower()]
        self.assertEqual(missing, [], missing)

    def test_parent_readme_links_test_plans(self) -> None:
        parent = _read(NEW_FEATURES / "README.md")
        self.assertIn("test-plan.md", parent)
        for slug in FEATURE_BUNDLES:
            self.assertIn(slug, parent)

    def test_research_and_specs_still_present(self) -> None:
        for slug in FEATURE_BUNDLES:
            self.assertTrue((NEW_FEATURES / slug / "research.md").is_file())
            self.assertTrue((NEW_FEATURES / slug / "spec.md").is_file())

    def test_testplans_link_implementation_plans(self) -> None:
        for slug in FEATURE_BUNDLES:
            ip = NEW_FEATURES / slug / "implementation-plan.md"
            self.assertTrue(ip.is_file(), f"missing {ip}")
            text = _read(_tp(slug))
            self.assertIn(
                "implementation-plan.md",
                text,
                f"{slug}/test-plan.md must link implementation-plan.md",
            )


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        TestNewFeaturesTestPlansPackage
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
