"""
The convention rules that judge each file on its own. The file lint runs them on the files it
selects (tools/conventions/files.py); the conventions tool runs them only when named. They
read files alone, so their library needs no Bazel.
"""

from tools.conventions.framework import Rule
from tools.conventions.rules.fixture_references import FixtureReferences
from tools.conventions.rules.public_documentation_links import PublicDocumentationLinks
from tools.conventions.rules.reading_order import ReadingOrder
from tools.conventions.rules.region_headers import RegionHeaders
from tools.conventions.rules.rg001 import PackageNames
from tools.conventions.rules.rg017 import AgentInstructions
from tools.conventions.rules.shared_module_files import SharedModuleFiles

RULES: tuple[Rule, ...] = (
    PackageNames(),
    AgentInstructions(),
    FixtureReferences(),
    PublicDocumentationLinks(),
    RegionHeaders(),
    ReadingOrder(),
    SharedModuleFiles(),
)
