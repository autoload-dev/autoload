"""
The convention rules that judge each file on its own. The lint check runs them per package on
the filegroups that Gazelle declares (tools/conventions/files.py); the conventions tool runs
them only when named. They read files alone, so their library needs no Bazel.
"""

from tools.conventions.framework import Rule
from tools.conventions.rules.rg004 import FixtureReferences
from tools.conventions.rules.rg013 import PublicDocumentationLinks
from tools.conventions.rules.rg024 import RegionHeaders
from tools.conventions.rules.rg025 import ReadingOrder

RULES: tuple[Rule, ...] = (
    FixtureReferences(),
    PublicDocumentationLinks(),
    RegionHeaders(),
    ReadingOrder(),
)
