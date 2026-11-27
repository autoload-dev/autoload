"""
Check that an SPDX document names packages with their declared licenses.

Usage: inspect_spdx.py <document.json> <purl>=<license>...

A package is named by its package URL without the version and qualifiers, such as
pkg:bazel/sqlite3; every package of that name must declare the license as its SPDX
`licenseDeclared`. Exits 1 with what the document lacks.
"""

import json
import sys
from pathlib import Path


def licenses(document: dict) -> dict[str, set[str]]:
    """
    The declared licenses of the document's packages, by the name part of their package URL:
    without the version and qualifiers, which tell one build of a package from another. The
    same package URL twice is an error.
    """
    purls = [
        (reference["referenceLocator"], package.get("licenseDeclared", ""))
        for package in document["packages"]
        for reference in package.get("externalRefs", [])
        if reference["referenceType"] == "purl"
    ]
    if len({purl for purl, _ in purls}) != len(purls):
        raise ValueError(
            f"the document names a package twice: {sorted(p for p, _ in purls)}"
        )
    found: dict[str, set[str]] = {}
    for purl, license in purls:
        found.setdefault(purl.partition("@")[0].partition("?")[0], set()).add(license)
    return found


def problems(found: dict[str, set[str]], expected: dict[str, str]) -> list[str]:
    """What the found packages lack of the expected licenses by package URL."""
    lacking = []
    for purl, license in sorted(expected.items()):
        if purl not in found:
            lacking.append(f"{purl} is missing; the document names {sorted(found)}")
        elif found[purl] != {license}:
            lacking.append(f"{purl} declares {sorted(found[purl])}, not {license}")
    return lacking


def main(arguments: list[str]) -> int:
    document, *pairs = arguments
    expected = dict(pair.split("=", 1) for pair in pairs)
    lacking = problems(licenses(json.loads(Path(document).read_text())), expected)
    for problem in lacking:
        print(problem, file=sys.stderr)
    return 1 if lacking else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
