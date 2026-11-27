"""
no-end-to-end-tests-in-public-documentation: public documentation shows runnable examples,
not the repository's end-to-end tests.
"""

import re
from collections.abc import Iterable

from tools.conventions.context import Context, Location
from tools.conventions.documents import internal_document
from tools.conventions.framework import Finding, RuleInfo

# A concrete project in e2e/, a consumer scenario such as e2e/rules_godot/smoke or an add-on
# end-to-end test such as e2e/addons/sqlite; layout schemas with placeholders, such as
# e2e/addons/<module>/, are not.
END_TO_END_TEST = re.compile(
    r"(?:(?<=//)|(?<![\w/.-]))e2e/[A-Za-z0-9_][A-Za-z0-9_.-]*/[A-Za-z0-9_][A-Za-z0-9_.-]*"
)


class EndToEndTestReferences:
    info = RuleInfo(
        "no-end-to-end-tests-in-public-documentation",
        "Public documentation does not reference end-to-end tests",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        for name in context.workspace.documents:
            # Internal documentation may name the end-to-end tests it describes.
            if internal_document(name):
                continue
            for number, line in enumerate(context.workspace.text(name).splitlines(), 1):
                if END_TO_END_TEST.search(line):
                    yield Finding(
                        Location(name, number),
                        "show a runnable example from examples/ instead of an end-to-end test",
                    )
