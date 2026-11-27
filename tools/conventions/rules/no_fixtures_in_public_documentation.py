"""
no-fixtures-in-public-documentation: public documentation uses runnable examples, not
regression fixtures.
"""

import re
from collections.abc import Iterable

from tools.conventions.context import Context, Location
from tools.conventions.documents import internal_document
from tools.conventions.framework import Finding, RuleInfo


class FixtureReferences:
    info = RuleInfo(
        "no-fixtures-in-public-documentation",
        "Public documentation does not reference test fixtures",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        for name in context.workspace.documents:
            # Internal documentation may name the regression projects and add-ons it describes.
            if internal_document(name):
                continue
            for number, line in enumerate(context.workspace.text(name).splitlines(), 1):
                # A concrete path into a consumer scenario, such as tests/smoke/linux; layout
                # schemas with placeholders, such as tests/smoke/<operating_system>/, are not.
                if re.search(
                    r"(?:(?<=//)|(?<![\w/.-]))tests/[A-Za-z0-9_][A-Za-z0-9_.-]*/[A-Za-z0-9_][A-Za-z0-9_.-]*",
                    line,
                ):
                    yield Finding(
                        Location(name, number),
                        "use a runnable example instead of a named regression project or add-on",
                    )
