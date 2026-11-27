"""The SPDX inspector's checks of the packages a document names and their licenses."""

import unittest

from tools.artifact_tests.inspect_spdx import licenses, problems


def _package(purl: str, license: str) -> dict:
    return {
        "licenseDeclared": license,
        "externalRefs": [{"referenceType": "purl", "referenceLocator": purl}],
    }


class InspectSpdxTest(unittest.TestCase):
    def test_builds_of_a_package_share_its_name(self) -> None:
        document = {
            "packages": [
                _package("pkg:generic/godot@4.7.2?checksum=sha256:00", "MIT"),
                _package("pkg:generic/godot@4.7.2", "MIT"),
                _package("pkg:generic/godot-cpp?checksum=sha256:00", "MIT"),
                {},
            ]
        }
        self.assertEqual(
            {"pkg:generic/godot": {"MIT"}, "pkg:generic/godot-cpp": {"MIT"}},
            licenses(document),
        )

    def test_missing_packages_and_other_licenses_are_problems(self) -> None:
        found = {
            "pkg:bazel/sqlite3": {"blessing"},
            "pkg:generic/godot": {"MIT", "NOASSERTION"},
        }
        self.assertEqual([], problems(found, {"pkg:bazel/sqlite3": "blessing"}))
        self.assertEqual(
            [
                "pkg:bazel/autoload_sqlite is missing; the document names "
                "['pkg:bazel/sqlite3', 'pkg:generic/godot']",
                "pkg:bazel/sqlite3 declares ['blessing'], not MIT",
                "pkg:generic/godot declares ['MIT', 'NOASSERTION'], not MIT",
            ],
            problems(
                found,
                {
                    "pkg:bazel/autoload_sqlite": "MPL-2.0",
                    "pkg:bazel/sqlite3": "MIT",
                    "pkg:generic/godot": "MIT",
                },
            ),
        )


if __name__ == "__main__":
    unittest.main()
