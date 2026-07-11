#!/usr/bin/env python3
"""
Structural tests for Feature 4 technical specification (NF-SPEC-04).

Drives the real shipped file:
  new-features/04-agy-rocketchat-collab/spec.md
plus index/research/profile linkage — not a re-implemented copy.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEW_FEATURES = ROOT / "new-features"
BUNDLE = NEW_FEATURES / "04-agy-rocketchat-collab"
SPEC = BUNDLE / "spec.md"
BUNDLE_README = BUNDLE / "README.md"
PARENT_INDEX = NEW_FEATURES / "README.md"
RESEARCH = BUNDLE / "research.md"
PROFILES = BUNDLE / "profiles"

MIN_SPEC_BYTES = 10_000
SHALL_RE = re.compile(r"\bshall\b", re.I)

SECTION_PATTERNS = {
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
    "open_decisions": re.compile(
        r"(?im)^#{1,3}\s+.*open decision",
    ),
    "traceability": re.compile(
        r"(?im)^#{1,3}\s+.*traceab",
    ),
}

PRODUCT_PATTERNS = (
    re.compile(r"NF-SPEC-04"),
    re.compile(r"\bagy\b", re.I),
    re.compile(r"\bgrok\b", re.I),
    re.compile(r"@agy|@grok|@mention|mention", re.I),
    re.compile(r"long[- ]horizon|many turns|multi-turn", re.I),
    re.compile(r"CLI-only|never MCP|MCP `?agy_", re.I),
    re.compile(r"chat\.update|Thinking", re.I),
    re.compile(r"profile|L2|rc_collab|inject", re.I),
    re.compile(r"principal", re.I),
)

GROUNDING_TERMS = (
    "rc_operator_agent",
    "agy-cli-collab",
    "principal-only",
    "NO_DUPLICATE",
    "research.md",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestFeature4AgyCollabSpec(unittest.TestCase):
    def test_spec_file_exists_with_depth(self) -> None:
        self.assertTrue(SPEC.is_file(), f"missing {SPEC}")
        size = SPEC.stat().st_size
        self.assertGreaterEqual(
            size,
            MIN_SPEC_BYTES,
            f"spec too small ({size} B)",
        )

    def test_spec_only_no_runtime_declared(self) -> None:
        text = _read(SPEC)
        self.assertRegex(
            text,
            r"(?i)specification.*(out of scope|documentation only)|"
            r"implementation.*out of scope|"
            r"no runtime implementation|"
            r"documentation only",
        )

    def test_indexes_link_nf_spec_04(self) -> None:
        parent = _read(PARENT_INDEX)
        bundle = _read(BUNDLE_README)
        self.assertIn("04-agy-rocketchat-collab", parent)
        self.assertRegex(parent, r"NF-SPEC-04|spec\.md")
        self.assertIn("spec.md", parent)
        self.assertIn("spec.md", bundle)
        self.assertRegex(bundle, r"NF-SPEC-04")

    def test_required_section_classes(self) -> None:
        text = _read(SPEC)
        for label, pat in SECTION_PATTERNS.items():
            self.assertIsNotNone(
                pat.search(text),
                f"spec missing section class: {label}",
            )

    def test_normative_shall_density(self) -> None:
        text = _read(SPEC)
        count = len(SHALL_RE.findall(text))
        self.assertGreaterEqual(
            count,
            20,
            f"expected rich shall-language, found {count}",
        )

    def test_preferred_product_model_normative(self) -> None:
        text = _read(SPEC)
        for pat in PRODUCT_PATTERNS:
            self.assertIsNotNone(
                pat.search(text),
                f"spec missing product pattern {pat.pattern}",
            )
        self.assertRegex(text, r"FR-A\d+")
        self.assertRegex(
            text,
            r"(?i)shall not.*MCP|never MCP|MCP.*shall not|forbids MCP",
        )

    def test_live_stack_and_research_grounding(self) -> None:
        text = _read(SPEC)
        missing = [t for t in GROUNDING_TERMS if t.lower() not in text.lower()]
        self.assertEqual(missing, [], f"missing grounding: {missing}")
        self.assertTrue(RESEARCH.is_file(), "research must remain")
        self.assertRegex(text, r"(?i)prior research|builds on|\./research")
        self.assertRegex(text, r"profiles/")
        self.assertTrue(PROFILES.is_dir())

    def test_research_and_profiles_still_present(self) -> None:
        self.assertTrue(RESEARCH.is_file())
        self.assertTrue((PROFILES / "agy-rc-collab.agent.md").is_file())
        self.assertTrue((PROFILES / "grok-rc-collab.inject.md").is_file())
        self.assertTrue((PROFILES / "agy-rc-collab.AGENTS.md").is_file())


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        TestFeature4AgyCollabSpec
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
