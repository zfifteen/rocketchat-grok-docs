#!/usr/bin/env python3
"""
Structural tests for the new-features technical specifications (per-feature bundles).

Exercises real on-disk specs under new-features/<slug>/spec.md.
Fails if specs are missing, shallow, mis-scoped, or unlinked from research.
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

MIN_SPEC_BYTES = 8_000

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
    "integration": re.compile(
        r"(?im)^#{1,3}\s+.*integrat",
    ),
    "risks_or_dependencies": re.compile(
        r"(?im)^#{1,3}\s+.*(risk|dependenc)",
    ),
    "acceptance_or_phases": re.compile(
        r"(?im)^#{1,3}\s+.*(acceptance|phased delivery|phase)",
    ),
}

SHALL_RE = re.compile(r"\bshall\b", re.I)

SUBJECTS = {
    "01-true-voice-in-rc-call": [
        re.compile(r"voice", re.I),
        re.compile(r"(Call|VideoConf|LiveKit|media.?plane)", re.I),
        re.compile(r"Grok Voice|Realtime|IVideoConfProvider", re.I),
        re.compile(r"NF-SPEC-01"),
    ],
    "02-streaming-thinking-telemetry": [
        re.compile(r"stream", re.I),
        re.compile(r"Thinking", re.I),
        re.compile(r"chat\.update|stopReason|telemetry", re.I),
        re.compile(r"NF-SPEC-02"),
    ],
    "03-phone-control-plane": [
        re.compile(r"control plane|slash", re.I),
        re.compile(r"/status|/admin once|elevation", re.I),
        re.compile(r"mission control", re.I),
        re.compile(r"NF-SPEC-03"),
    ],
}

GROUNDING_TERMS = (
    "rc_operator_agent",
    "chat.update",
    "Thinking",
    "reply file",
    "approval",
    "LiveKit",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _spec(slug: str) -> Path:
    return NEW_FEATURES / slug / "spec.md"


def _bundle_readme(slug: str) -> Path:
    return NEW_FEATURES / slug / "README.md"


class TestNewFeaturesSpecsPackage(unittest.TestCase):
    def test_each_bundle_has_spec_and_hub(self) -> None:
        for slug in FEATURE_BUNDLES:
            path = _spec(slug)
            self.assertTrue(path.is_file(), f"missing {path}")
            self.assertTrue(
                _bundle_readme(slug).is_file(),
                f"missing bundle hub {slug}/README.md",
            )
            size = path.stat().st_size
            self.assertGreaterEqual(
                size,
                MIN_SPEC_BYTES,
                f"{slug}/spec.md too small ({size} B)",
            )

    def test_bundle_hubs_and_index_describe_specs(self) -> None:
        index = _read(NEW_FEATURES / "README.md")
        self.assertRegex(index, r"(?i)specification|spec\.md")
        self.assertRegex(
            index,
            r"(?i)no runtime|documentation only|out of scope",
        )
        self.assertRegex(index, r"(?i)voice")
        self.assertRegex(index, r"(?i)stream")
        self.assertRegex(index, r"(?i)control plane|slash")
        for slug in FEATURE_BUNDLES:
            self.assertIn(slug, index)
            hub = _read(_bundle_readme(slug))
            self.assertIn("spec.md", hub)
            self.assertRegex(hub, r"(?i)documentation only|no runtime")

    def test_each_spec_has_required_section_classes(self) -> None:
        for slug in FEATURE_BUNDLES:
            text = _read(_spec(slug))
            for label, pat in SECTION_PATTERNS.items():
                self.assertIsNotNone(
                    pat.search(text),
                    f"{slug}/spec.md missing section class: {label}",
                )
            self.assertGreaterEqual(
                len(SHALL_RE.findall(text)),
                5,
                f"{slug}/spec.md should use normative 'shall' requirements",
            )

    def test_subjects_match_three_features(self) -> None:
        for slug, patterns in SUBJECTS.items():
            text = _read(_spec(slug))
            for pat in patterns:
                self.assertIsNotNone(
                    pat.search(text),
                    f"{slug}/spec.md missing subject pattern {pat.pattern}",
                )

    def test_specs_link_matching_research(self) -> None:
        for slug in FEATURE_BUNDLES:
            research = NEW_FEATURES / slug / "research.md"
            self.assertTrue(research.is_file(), f"research missing {slug}")
            text = _read(_spec(slug))
            self.assertIn(
                "research.md",
                text,
                f"{slug}/spec.md should reference research.md",
            )
            self.assertRegex(text, r"(?i)prior research|builds on|research")

    def test_package_grounded_in_live_stack(self) -> None:
        blob = "\n".join(_read(_spec(s)) for s in FEATURE_BUNDLES)
        blob += "\n" + _read(NEW_FEATURES / "README.md")
        missing = [t for t in GROUNDING_TERMS if t.lower() not in blob.lower()]
        self.assertEqual(missing, [], f"missing grounding terms: {missing}")

    def test_parent_index_links_feature_specs(self) -> None:
        parent = _read(NEW_FEATURES / "README.md")
        for slug in FEATURE_BUNDLES:
            self.assertIn(f"{slug}/spec.md", parent.replace("](./", "/").replace("](", "/"))
            # robust: either relative path appears
            self.assertTrue(
                f"{slug}/spec.md" in parent or f"{slug}/" in parent,
                f"index must navigate to {slug} spec",
            )
            self.assertIn("spec.md", parent)

    def test_research_docs_still_present(self) -> None:
        """Specs must not replace research (plan non-goal)."""
        for slug in FEATURE_BUNDLES:
            self.assertTrue(
                (NEW_FEATURES / slug / "research.md").is_file(),
                f"research must remain: {slug}/research.md",
            )

    def test_specs_link_test_plan_and_impl_plan(self) -> None:
        """Each spec header should point to matching sibling NF-TP and NF-IP docs."""
        for slug in FEATURE_BUNDLES:
            text = _read(_spec(slug))
            self.assertIn(
                "test-plan.md",
                text,
                f"{slug}/spec.md missing test-plan link",
            )
            self.assertIn(
                "implementation-plan.md",
                text,
                f"{slug}/spec.md missing impl-plan link",
            )
            self.assertTrue((NEW_FEATURES / slug / "test-plan.md").is_file())
            self.assertTrue(
                (NEW_FEATURES / slug / "implementation-plan.md").is_file()
            )


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        TestNewFeaturesSpecsPackage
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
