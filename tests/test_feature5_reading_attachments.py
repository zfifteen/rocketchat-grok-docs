#!/usr/bin/env python3
"""
Structural tests for Feature 5 documentation bundle (reading attachments).

Drives real on-disk artifacts under
new-features/05-reading-attachments/ — research, spec, test plan, impl plan.
Documentation only; no runtime operator implementation required.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEW_FEATURES = ROOT / "new-features"
BUNDLE = NEW_FEATURES / "05-reading-attachments"
RESEARCH = BUNDLE / "research.md"
SPEC = BUNDLE / "spec.md"
TEST_PLAN = BUNDLE / "test-plan.md"
IMPL = BUNDLE / "implementation-plan.md"
BUNDLE_README = BUNDLE / "README.md"
INDEX = NEW_FEATURES / "README.md"
ROOT_README = ROOT / "README.md"

MIN_RESEARCH = 8_000
MIN_SPEC = 8_000
MIN_TP = 6_000
MIN_IP = 7_000

SHALL_RE = re.compile(r"\bshall\b", re.I)

SECTION_RESEARCH = {
    "problem_or_baseline": re.compile(
        r"(?im)^#{1,3}\s+.*(problem|baseline|framing|gap)",
    ),
    "approaches_or_options": re.compile(
        r"(?im)^#{1,3}\s+.*(approach|option|candidate|architecture)",
    ),
    "integration": re.compile(r"(?im)^#{1,3}\s+.*integrat"),
    "risks": re.compile(r"(?im)^#{1,3}\s+.*(risk|failure)"),
    "recommended": re.compile(
        r"(?im)^#{1,3}\s+.*(recommend|direction|conclusion)",
    ),
    "open_questions": re.compile(r"(?im)^#{1,3}\s+.*open question"),
}

SECTION_SPEC = {
    "problem_or_goals": re.compile(
        r"(?im)^#{1,3}\s+.*(problem|context|goal)",
    ),
    "requirements": re.compile(
        r"(?im)^#{1,3}\s+.*(requirement|normative)",
    ),
    "architecture_or_design": re.compile(
        r"(?im)^#{1,3}\s+.*(architecture|design decision)",
    ),
    "integration": re.compile(r"(?im)^#{1,3}\s+.*integrat"),
    "risks_or_dependencies": re.compile(
        r"(?im)^#{1,3}\s+.*(risk|dependenc)",
    ),
    "acceptance_or_phases": re.compile(
        r"(?im)^#{1,3}\s+.*(acceptance|phased delivery|phase)",
    ),
}

SECTION_TP = {
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

SECTION_IP = {
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

SUBJECT_PATTERNS = (
    re.compile(r"attachment|attach", re.I),
    re.compile(r"image|picture|photo|JPEG|PNG", re.I),
    re.compile(r"file|document|PDF", re.I),
    re.compile(r"download_rc_file|file-upload|chat\.getMessage", re.I),
    re.compile(r"read_file", re.I),
    re.compile(r"extract_image|compose_wake_user_text|resolve_message", re.I),
    re.compile(r"NF-SPEC-05|NF-TP-05|NF-IP-05"),
)

GROUNDING = (
    "rc_operator_agent",
    "chat.update",
    "Thinking",
    "reply file",
    "read_file",
    "download_rc_file",
    "NO_DUPLICATE",
)

DOWNSTREAM = ("spec.md", "test-plan.md", "implementation-plan.md")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestFeature5ReadingAttachments(unittest.TestCase):
    def test_bundle_files_exist_with_depth(self) -> None:
        self.assertTrue(BUNDLE.is_dir(), f"missing {BUNDLE}")
        for path, minimum in (
            (RESEARCH, MIN_RESEARCH),
            (SPEC, MIN_SPEC),
            (TEST_PLAN, MIN_TP),
            (IMPL, MIN_IP),
            (BUNDLE_README, 500),
        ):
            self.assertTrue(path.is_file(), f"missing {path}")
            size = path.stat().st_size
            self.assertGreaterEqual(
                size,
                minimum,
                f"{path.name} too small ({size} bytes, need ≥{minimum})",
            )

    def test_documentation_only_declared(self) -> None:
        for path in (BUNDLE_README, RESEARCH, SPEC, INDEX):
            text = _read(path)
            self.assertRegex(
                text,
                r"(?i)documentation only|no runtime implementation|research only|implementation out of scope",
                f"{path.name} must declare docs-only / no runtime",
            )

    def test_index_and_root_link_feature5(self) -> None:
        index = _read(INDEX)
        self.assertIn("05-reading-attachments", index)
        self.assertRegex(index, r"(?i)attachment|reading attachments")
        self.assertIn("05-reading-attachments/spec.md", index.replace("](./", "/").replace("](", "/") or index)
        self.assertTrue(
            "05-reading-attachments" in index and "spec.md" in index,
            "index must navigate to feature 5 spec",
        )
        root = _read(ROOT_README)
        self.assertIn("05-reading-attachments", root)

    def test_research_sections_and_downstream_links(self) -> None:
        text = _read(RESEARCH)
        for label, pat in SECTION_RESEARCH.items():
            self.assertIsNotNone(
                pat.search(text),
                f"research.md missing section class: {label}",
            )
        for target in DOWNSTREAM:
            self.assertIn(target, text, f"research must link {target}")
            self.assertTrue((BUNDLE / target).is_file())

    def test_spec_normative_and_linked(self) -> None:
        text = _read(SPEC)
        self.assertIn("NF-SPEC-05", text)
        self.assertIn("research.md", text)
        self.assertIn("test-plan.md", text)
        self.assertIn("implementation-plan.md", text)
        for label, pat in SECTION_SPEC.items():
            self.assertIsNotNone(
                pat.search(text),
                f"spec.md missing section class: {label}",
            )
        self.assertGreaterEqual(
            len(SHALL_RE.findall(text)),
            5,
            "spec should use normative 'shall' requirements",
        )

    def test_test_plan_edges_and_links(self) -> None:
        text = _read(TEST_PLAN)
        self.assertIn("NF-TP-05", text)
        self.assertIn("spec.md", text)
        self.assertIn("research.md", text)
        self.assertIn("implementation-plan.md", text)
        for label, pat in SECTION_TP.items():
            self.assertIsNotNone(
                pat.search(text),
                f"test-plan.md missing section: {label}",
            )
        edge_ids = re.findall(r"\bE-A-\d+\b|\bE-A-[a-z]+\b", text)
        self.assertGreaterEqual(
            len(edge_ids),
            8,
            f"need many edge cases (found {len(edge_ids)})",
        )

    def test_impl_plan_phases_and_flags(self) -> None:
        text = _read(IMPL)
        self.assertIn("NF-IP-05", text)
        self.assertIn("spec.md", text)
        self.assertIn("test-plan.md", text)
        self.assertIn("research.md", text)
        self.assertRegex(text, r"(?i)effort|eng-day")
        self.assertRegex(text, r"RC_ATTACH_")
        self.assertRegex(text, r"(?i)rollback")
        for label, pat in SECTION_IP.items():
            self.assertIsNotNone(
                pat.search(text),
                f"implementation-plan.md missing {label}",
            )

    def test_subject_and_grounding(self) -> None:
        blob = "\n".join(
            _read(p) for p in (RESEARCH, SPEC, TEST_PLAN, IMPL, BUNDLE_README)
        )
        for pat in SUBJECT_PATTERNS:
            self.assertIsNotNone(
                pat.search(blob),
                f"feature 5 docs missing subject pattern {pat.pattern}",
            )
        missing = [t for t in GROUNDING if t.lower() not in blob.lower()]
        self.assertEqual(missing, [], f"missing grounding terms: {missing}")

    def test_recommended_direction_a2(self) -> None:
        text = _read(RESEARCH)
        self.assertRegex(text, r"(?i)A2|operator inbound|recommended")
        self.assertRegex(text, r"(?i)read_file")
        self.assertRegex(text, r"(?i)thumb")

    def test_bundle_hub_lists_layers(self) -> None:
        hub = _read(BUNDLE_README)
        for name in (
            "research.md",
            "spec.md",
            "test-plan.md",
            "implementation-plan.md",
        ):
            self.assertIn(name, hub)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        TestFeature5ReadingAttachments
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
