"""
snake-case-package-paths regressions for strict spelling and module-relative package
ownership.
"""

import unittest

from tools.conventions.rules.snake_case_package_paths import PackageNames
from tools.conventions.test_support import RepositoryTest


class PackageNamesTest(RepositoryTest):
    def test_all_package_segments_follow_strict_spelling_in_the_nearest_module(
        self,
    ) -> None:
        files = (
            "MODULE.bazel",
            "BUILD.bazel",
            "good_name/a1/BUILD",
            "bad-name/leaf/BUILD.bazel",
            "x-y/x-y/BUILD.bazel",
            "a__b/BUILD.bazel",
            "_leading/BUILD.bazel",
            "trailing_/BUILD.bazel",
            "1number/BUILD.bazel",
            "café/BUILD.bazel",
            "Consumer-Module/MODULE.bazel",
            "Consumer-Module/good/BUILD.bazel",
        )
        for name in files:
            self.write(name, "")
        context = self.context(files=files)
        findings = list(PackageNames().evaluate(context))
        self.assertEqual(7, len(findings))
        self.assertNotIn(
            "Consumer-Module/good/BUILD.bazel", [f.location.path for f in findings]
        )
        self.assertEqual((0, 0), (self.tools.call_requests, self.tools.rule_requests))

    def test_one_build_file_is_judged_by_the_modules_on_disk(self) -> None:
        for name in ("MODULE.bazel", "Sub-Module/MODULE.bazel", "fixtures/REPO.bazel"):
            self.write(name, "")
        for name in ("Sub-Module/ok/BUILD", "fixtures/Bad-Name/BUILD", "x-y/BUILD"):
            self.write(name, "")
        context = self.file_context(
            ("Sub-Module/ok/BUILD", "fixtures/Bad-Name/BUILD", "x-y/BUILD")
        )
        self.assertEqual(
            ["x-y/BUILD"],
            [f.location.path for f in PackageNames().evaluate(context)],
        )


if __name__ == "__main__":
    unittest.main()
