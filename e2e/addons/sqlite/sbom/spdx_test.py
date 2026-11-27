"""Check the packages that an SPDX document of a pack with the SQLite add-on names."""

import json
import sys
import unittest
from pathlib import Path

DOCUMENT = Path(sys.argv[1])
sys.argv = sys.argv[:1]


def packages() -> dict[str, dict]:
    """The document's packages by the name part of their package URL, without the version."""
    found = {}
    for package in json.loads(DOCUMENT.read_text())["packages"]:
        for reference in package.get("externalRefs", []):
            if reference["referenceType"] == "purl":
                found[reference["referenceLocator"].partition("@")[0]] = package
    return found


class SpdxTest(unittest.TestCase):
    def test_the_add_on_module_and_its_library_carry_their_licenses(self) -> None:
        found = packages()
        for purl, license in (
            ("pkg:bazel/autoload_sqlite", "MPL-2.0"),
            ("pkg:bazel/sqlite3", "blessing"),
        ):
            with self.subTest(purl=purl):
                self.assertIn(purl, found, sorted(found))
                self.assertEqual(license, found[purl]["licenseDeclared"])


if __name__ == "__main__":
    unittest.main()
