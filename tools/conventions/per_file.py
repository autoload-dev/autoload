"""
The convention rules that judge each file on its own. The file lint runs them on the files it
selects (tools/conventions/files.py); the conventions tool runs them only when named. They
read files alone, so their library needs no Bazel.
"""

from tools.conventions.framework import Rule
from tools.conventions.rules.definitions_before_callers import ReadingOrder
from tools.conventions.rules.no_claude_md import AgentInstructions
from tools.conventions.rules.no_fixtures_in_public_documentation import FixtureReferences
from tools.conventions.rules.no_internal_links_in_public_documentation import (
    PublicDocumentationLinks,
)
from tools.conventions.rules.region_headers_named_in_head import RegionHeaders
from tools.conventions.rules.shared_module_files_as_generated import SharedModuleFiles
from tools.conventions.rules.snake_case_package_paths import PackageNames

RULES: tuple[Rule, ...] = (
    PackageNames(),
    AgentInstructions(),
    FixtureReferences(),
    PublicDocumentationLinks(),
    RegionHeaders(),
    ReadingOrder(),
    SharedModuleFiles(),
)
