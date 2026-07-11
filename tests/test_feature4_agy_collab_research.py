#!/usr/bin/env python3
"""
Structural tests for Feature 4 research package (agy Rocket.Chat collab).

Drives the real on-disk deliverable under
new-features/04-agy-rocketchat-collab/ — not a re-implemented copy.
Research-only package: no runtime operator implementation required.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEW_FEATURES = ROOT / "new-features"
FEATURE4 = NEW_FEATURES / "04-agy-rocketchat-collab"
RESEARCH = FEATURE4 / "research.md"
FOLDER_README = FEATURE4 / "README.md"
PROFILES = FEATURE4 / "profiles"
INDEX = NEW_FEATURES / "README.md"

MIN_RESEARCH_BYTES = 12_000

SECTION_PATTERNS = {
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

# Preferred product model must appear in research body
PRODUCT_PATTERNS = (
    re.compile(r"@agy|@mention|mention", re.I),
    re.compile(r"@grok", re.I),
    re.compile(r"long[- ]horizon|many,\s*many turns|many turns", re.I),
    re.compile(r"principal", re.I),
    re.compile(r"CLI-only|never MCP|no MCP|MCP `?agy_\*?", re.I),
    re.compile(r"\bagy\b", re.I),
    re.compile(r"\bgrok\b", re.I),
)

GROUNDING_TERMS = (
    "rc_operator_agent",
    "agy-cli-collab",
    "chat.update",
    "Thinking",
    "principal-only",
    "NO_DUPLICATE",
)

PROFILE_FILES = (
    "agy-rc-collab.agent.md",
    "agy-rc-collab.AGENTS.md",
    "grok-rc-collab.inject.md",
    "README.md",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestFeature4AgyCollabResearch(unittest.TestCase):
    def test_feature4_folder_and_core_docs_exist(self) -> None:
        self.assertTrue(FEATURE4.is_dir(), f"missing {FEATURE4}")
        self.assertTrue(RESEARCH.is_file(), f"missing {RESEARCH}")
        self.assertTrue(FOLDER_README.is_file(), f"missing {FOLDER_README}")
        size = RESEARCH.stat().st_size
        self.assertGreaterEqual(
            size,
            MIN_RESEARCH_BYTES,
            f"research.md too small ({size} bytes)",
        )

    def test_research_only_declared(self) -> None:
        for path in (FOLDER_README, RESEARCH, INDEX):
            text = _read(path)
            self.assertRegex(
                text,
                r"(?i)research only|no runtime implementation|documentation only",
                f"{path.name} must declare research-only / no runtime",
            )

    def test_index_links_feature4(self) -> None:
        text = _read(INDEX)
        self.assertIn("04-agy-rocketchat-collab", text)
        self.assertRegex(text, r"(?i)agy|antigravity")
        self.assertRegex(text, r"(?i)@mention|dual account|long-horizon")

    def test_research_has_required_section_classes(self) -> None:
        text = _read(RESEARCH)
        for label, pat in SECTION_PATTERNS.items():
            self.assertIsNotNone(
                pat.search(text),
                f"research.md missing section class: {label}",
            )

    def test_research_preferred_product_model(self) -> None:
        text = _read(RESEARCH)
        for pat in PRODUCT_PATTERNS:
            self.assertIsNotNone(
                pat.search(text),
                f"research.md missing product pattern {pat.pattern}",
            )
        # Recommended dual-account direction
        self.assertRegex(text, r"(?i)preferred product|C3|dual")

    def test_research_live_stack_grounding(self) -> None:
        text = _read(RESEARCH)
        missing = [t for t in GROUNDING_TERMS if t.lower() not in text.lower()]
        self.assertEqual(
            missing,
            [],
            f"research.md missing grounding terms: {missing}",
        )

    def test_profiles_drafts_present_with_handoff_rules(self) -> None:
        self.assertTrue(PROFILES.is_dir(), f"missing {PROFILES}")
        for name in PROFILE_FILES:
            path = PROFILES / name
            self.assertTrue(path.is_file(), f"missing profile {name}")
            self.assertGreater(path.stat().st_size, 200, f"{name} too short")

        agy_agent = _read(PROFILES / "agy-rc-collab.agent.md")
        self.assertRegex(agy_agent, r"(?i)@grok")
        self.assertRegex(agy_agent, r"(?i)\bagy\b")
        self.assertRegex(agy_agent, r"(?i)read-only|handoff|principal")

        agy_agents = _read(PROFILES / "agy-rc-collab.AGENTS.md")
        self.assertRegex(agy_agents, r"(?i)@grok|tag-to-talk")

        grok_inject = _read(PROFILES / "grok-rc-collab.inject.md")
        self.assertRegex(grok_inject, r"(?i)@agy")
        self.assertRegex(grok_inject, r"(?i)do not.*agy CLI|nested|dual-account", re.I)

        profiles_readme = _read(PROFILES / "README.md")
        self.assertRegex(profiles_readme, r"(?i)L1|L2|layer")

    def test_no_feature4_spec_required(self) -> None:
        """Feature 4 is research-only; absence of full chain is intentional."""
        # Neither legacy layer path nor in-bundle full chain is required.
        legacy_spec = NEW_FEATURES / "specs" / "04-agy-rocketchat-collab-spec.md"
        bundle_spec = FEATURE4 / "spec.md"
        self.assertFalse(
            legacy_spec.is_file() and bundle_spec.is_file(),
            "feature 4 should remain research-only (no full NF-SPEC package)",
        )
        folder = _read(FOLDER_README)
        self.assertRegex(folder, r"(?i)no runtime|research only|not installed")


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        TestFeature4AgyCollabResearch
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
