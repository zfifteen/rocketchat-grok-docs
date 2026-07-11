#!/usr/bin/env python3
"""
Structural tests for the new-features research layer (per-feature bundles).

Drives the real on-disk deliverable under new-features/<slug>/research.md,
not a re-implemented copy of the research. Fails if the package is missing,
truncated, or loses required section coverage / subject naming.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEW_FEATURES = ROOT / "new-features"

INDEX_CANDIDATES = ("README.md", "INDEX.md")

# Features 1–3 full-chain research lives as research.md inside each bundle
FEATURE_BUNDLES = (
    "01-true-voice-in-rc-call",
    "02-streaming-thinking-telemetry",
    "03-phone-control-plane",
)

MIN_FEATURE_BYTES = 8_000

SECTION_PATTERNS = {
    "problem_or_baseline": re.compile(
        r"(?im)^#{1,3}\s+.*(problem|baseline|framing|gap)",
    ),
    "approaches_or_options": re.compile(
        r"(?im)^#{1,3}\s+.*(approach|option|candidate|architecture)",
    ),
    "integration": re.compile(
        r"(?im)^#{1,3}\s+.*integrat",
    ),
    "risks": re.compile(
        r"(?im)^#{1,3}\s+.*(risk|failure)",
    ),
    "recommended": re.compile(
        r"(?im)^#{1,3}\s+.*(recommend|direction|conclusion)",
    ),
}

SUBJECTS = {
    "01-true-voice-in-rc-call": [
        re.compile(r"voice", re.I),
        re.compile(r"(Call|VideoConf|LiveKit|media.?plane)", re.I),
        re.compile(r"rc_call_bot|voice_room|Grok Voice", re.I),
    ],
    "02-streaming-thinking-telemetry": [
        re.compile(r"stream", re.I),
        re.compile(r"Thinking", re.I),
        re.compile(r"chat\.update|telemetry|stopReason", re.I),
    ],
    "03-phone-control-plane": [
        re.compile(r"control plane|slash", re.I),
        re.compile(r"/status|approval card|mission control", re.I),
        re.compile(r"admin once|elevation", re.I),
    ],
}

GROUNDING_TERMS = (
    "rc_operator_agent",
    "chat.update",
    "Thinking",
    "reply file",
    "Path C",
    "approval",
)

# Forward chain links expected inside each research.md (sibling paths)
DOWNSTREAM = ("spec.md", "test-plan.md", "implementation-plan.md")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _index_path() -> Path:
    for name in INDEX_CANDIDATES:
        p = NEW_FEATURES / name
        if p.is_file():
            return p
    raise FileNotFoundError(
        f"No entry index among {INDEX_CANDIDATES} under {NEW_FEATURES}"
    )


def _research(slug: str) -> Path:
    return NEW_FEATURES / slug / "research.md"


class TestNewFeaturesResearchPackage(unittest.TestCase):
    def test_folder_exists_and_nonempty(self) -> None:
        self.assertTrue(NEW_FEATURES.is_dir(), f"missing {NEW_FEATURES}")
        children = list(NEW_FEATURES.iterdir())
        self.assertGreater(len(children), 0, "new-features/ is empty")

    def test_index_and_three_feature_research_docs_exist(self) -> None:
        index = _index_path()
        self.assertGreater(index.stat().st_size, 500, "index too short")
        for slug in FEATURE_BUNDLES:
            path = _research(slug)
            self.assertTrue(path.is_file(), f"missing research {path}")
            size = path.stat().st_size
            self.assertGreaterEqual(
                size,
                MIN_FEATURE_BYTES,
                f"{slug}/research.md too small ({size} bytes)",
            )

    def test_index_names_all_three_subjects_and_bundles(self) -> None:
        text = _read(_index_path())
        self.assertRegex(text, r"(?i)voice")
        self.assertRegex(text, r"(?i)stream")
        self.assertRegex(text, r"(?i)control plane|slash")
        self.assertRegex(text, r"(?i)research|documentation only")
        for slug in FEATURE_BUNDLES:
            self.assertIn(slug, text, f"index should link bundle {slug}")

    def test_each_feature_has_required_section_classes(self) -> None:
        for slug in FEATURE_BUNDLES:
            text = _read(_research(slug))
            for label, pat in SECTION_PATTERNS.items():
                self.assertIsNotNone(
                    pat.search(text),
                    f"{slug}/research.md missing section class: {label}",
                )

    def test_each_feature_matches_its_subject(self) -> None:
        for slug, patterns in SUBJECTS.items():
            text = _read(_research(slug))
            for pat in patterns:
                self.assertIsNotNone(
                    pat.search(text),
                    f"{slug}/research.md missing subject pattern {pat.pattern}",
                )

    def test_package_grounded_in_live_stack_terms(self) -> None:
        blob = "\n".join(
            _read(_research(slug)) for slug in FEATURE_BUNDLES
        ) + "\n" + _read(_index_path())
        missing = [t for t in GROUNDING_TERMS if t.lower() not in blob.lower()]
        self.assertEqual(
            missing,
            [],
            f"research package missing live-stack grounding terms: {missing}",
        )

    def test_research_only_no_runtime_tree_required(self) -> None:
        """Docs package must declare research-only scope in the index."""
        text = _read(_index_path())
        self.assertRegex(
            text,
            r"(?i)no runtime|research / documentation only|research only|documentation only",
        )

    def test_feature_research_links_full_downstream_chain(self) -> None:
        """Features 1–3 research docs must link forward to sibling layers."""
        for slug in FEATURE_BUNDLES:
            text = _read(_research(slug))
            for target in DOWNSTREAM:
                self.assertIn(
                    target,
                    text,
                    f"{slug}/research.md must link forward to {target}",
                )
            # Targets must exist on disk
            for target in DOWNSTREAM:
                self.assertTrue(
                    (NEW_FEATURES / slug / target).is_file(),
                    f"missing {slug}/{target}",
                )


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        TestNewFeaturesResearchPackage
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
