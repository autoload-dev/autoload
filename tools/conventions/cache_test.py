"""Regressions for what the result cache's key covers and how entries round-trip."""

import unittest
from pathlib import Path

from tools.conventions.cache import ReportCache, evidence_key
from tools.conventions.context import Location
from tools.conventions.framework import Diagnostic, Finding, RuleInfo
from tools.conventions.test_support import RepositoryTest


class Evaluated:
    info = RuleInfo("RG900", "An evaluated rule", evaluated=True)

    def evaluate(self, context):  # noqa: ANN001, ANN201 - unused by the cache
        return ()


RULES = (Evaluated(),)


class CacheTest(RepositoryTest):
    def key(self) -> str:
        return evidence_key(self.workspace(), RULES, ())

    def test_loading_inputs_change_the_key_but_compiled_sources_do_not(self) -> None:
        self.write("lib/BUILD.bazel", "")
        self.write("lib/tool.py", "print(1)")
        before = self.key()
        self.write("lib/tool.py", "print(2)")
        self.assertEqual(before, self.key())
        self.write("lib/BUILD.bazel", "filegroup(name = 'all')")
        self.assertNotEqual(before, self.key())

    def test_added_files_and_the_checker_change_the_key(self) -> None:
        before = self.key()
        self.write("lib/tool.py", "")
        self.assertNotEqual(before, self.key())
        checker = self.root / "rule.py"
        checker.write_text("A = 1")
        self.assertNotEqual(
            evidence_key(self.workspace(), RULES, ()),
            evidence_key(self.workspace(), RULES, (checker,)),
        )

    def test_entries_round_trip_and_unknown_keys_miss(self) -> None:
        cache = ReportCache(self.root / "cache")
        diagnostic = Diagnostic(
            Evaluated.info,
            Finding(Location("BUILD.bazel", 3), "bad", "not_checked", True),
        )
        self.assertIsNone(cache.load("ab12", RULES))
        cache.store("ab12", (diagnostic,))
        self.assertEqual((diagnostic,), cache.load("ab12", RULES))
        self.assertTrue(
            all(Path(p).suffix == ".json" for p in (self.root / "cache").rglob("*.*"))
        )


if __name__ == "__main__":
    unittest.main()
