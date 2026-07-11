#!/usr/bin/env python3
"""
Structural tests for Feature 4 test plan (NF-TP-04).

Drives the real shipped file:
  new-features/04-agy-rocketchat-collab/test-plan.md
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEW_FEATURES = ROOT / "new-features"
BUNDLE = NEW_FEATURES / "04-agy-rocketchat-collab"
TEST_PLAN = BUNDLE / "test-plan.md"
SPEC = BUNDLE / "spec.md"
RESEARCH = BUNDLE / "research.md"
BUNDLE_README = BUNDLE / "README.md"
PARENT_INDEX = NEW_FEATURES / "README.md"

MIN_BYTES = 8_000

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

PRODUCT_PATTERNS = (
    re.compile(r"NF-TP-04"),
    re.compile(r"NF-SPEC-04"),
    re.compile(r"FR-A\d+"),
    re.compile(r"AC-A\d+"),
    re.compile(r"@agy|@grok|mention", re.I),
    re.compile(r"long[- ]horizon|hop.?budget|epoch", re.I),
    re.compile(r"CLI-only|MCP|agy_\*", re.I),
    re.compile(r"chat\.update|Thinking", re.I),
    re.compile(r"profile|inject|rc_collab", re.I),
    re.compile(r"dual|agy|grok", re.I),
)

GROUNDING = (
    "rc_operator_agent",
    "agy-cli-collab",
    "principal-only",
    "NO_DUPLICATE",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestFeature4AgyCollabTestPlan(unittest.TestCase):
    def test_test_plan_exists_with_depth(self) -> None:
        self.assertTrue(TEST_PLAN.is_file(), f"missing {TEST_PLAN}")
        size = TEST_PLAN.stat().st_size
        self.assertGreaterEqual(
            size,
            MIN_BYTES,
            f"test-plan too small ({size} B)",
        )

    def test_docs_only_declared(self) -> None:
        text = _read(TEST_PLAN)
        self.assertRegex(
            text,
            r"(?i)test-planning documentation only|no runtime implementation|"
            r"documentation only",
        )

    def test_indexes_link_test_plan(self) -> None:
        parent = _read(PARENT_INDEX)
        hub = _read(BUNDLE_README)
        self.assertIn("test-plan.md", parent)
        self.assertIn("04-agy-rocketchat-collab", parent)
        self.assertRegex(parent, r"NF-TP-04")
        self.assertIn("test-plan.md", hub)
        self.assertRegex(hub, r"NF-TP-04")

    def test_section_classes(self) -> None:
        text = _read(TEST_PLAN)
        for label, pat in SECTION_PATTERNS.items():
            self.assertIsNotNone(
                pat.search(text),
                f"test-plan missing section: {label}",
            )

    def test_requirement_traceability_and_cases(self) -> None:
        text = _read(TEST_PLAN)
        for pat in PRODUCT_PATTERNS:
            self.assertIsNotNone(
                pat.search(text),
                f"missing product/trace pattern {pat.pattern}",
            )
        case_ids = re.findall(r"\bTP-A-\d+\b", text)
        self.assertGreaterEqual(
            len(set(case_ids)),
            20,
            f"expected many TP-A cases, found {len(set(case_ids))}",
        )
        edge_ids = re.findall(r"\bE-A-[\w-]+\b", text)
        self.assertGreaterEqual(
            len(set(edge_ids)),
            12,
            f"expected many edge cases, found {len(set(edge_ids))}",
        )

    def test_links_spec_and_research(self) -> None:
        text = _read(TEST_PLAN)
        self.assertTrue(SPEC.is_file())
        self.assertTrue(RESEARCH.is_file())
        self.assertIn("spec.md", text)
        self.assertIn("research.md", text)
        self.assertRegex(text, r"profiles/")
        # Spec should point at test plan
        spec = _read(SPEC)
        self.assertIn("test-plan.md", spec)
        self.assertRegex(spec, r"NF-TP-04")

    def test_live_stack_grounding(self) -> None:
        text = _read(TEST_PLAN)
        missing = [t for t in GROUNDING if t.lower() not in text.lower()]
        self.assertEqual(missing, [], f"missing grounding: {missing}")


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        TestFeature4AgyCollabTestPlan
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
