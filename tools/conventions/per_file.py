"""
The convention rules that judge each file on its own. The lint check runs them per package on
the filegroups that Gazelle declares (tools/conventions/files.py); the conventions tool runs
them only when named. They read files alone, so their library needs no Bazel.
"""

from tools.conventions.framework import Rule
from tools.conventions.rules.fixture_references import FixtureReferences
from tools.conventions.rules.public_documentation_links import PublicDocumentationLinks
from tools.conventions.rules.reading_order import ReadingOrder
from tools.conventions.rules.region_headers import RegionHeaders

RULES: tuple[Rule, ...] = (
    FixtureReferences(),
    PublicDocumentationLinks(),
    RegionHeaders(),
    ReadingOrder(),
)
