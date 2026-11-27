"""
no-end-to-end-tests-in-public-documentation: public documentation shows runnable examples,
not the repository's end-to-end tests.
"""

import re
from collections.abc import Iterable

from tools.conventions.context import Context, Location
from tools.conventions.documents import internal_document
from tools.conventions.framework import Finding, RuleInfo
from tools.conventions.layout import ADDON_E2E, REGRESSION_ROOT

# A concrete project below an end-to-end root, a consumer scenario such as
# e2e/rules_godot/smoke or an add-on end-to-end test such as e2e/addons/sqlite; layout
# schemas with placeholders, such as e2e/addons/<module>/, are not. A path counts in a label
# or a relative link too, such as //e2e/addons/sqlite or ../../e2e/addons/sqlite.
ROOTS = "|".join(re.escape(root.as_posix()) for root in (REGRESSION_ROOT, ADDON_E2E))
END_TO_END_TEST = re.compile(rf"(?<![\w.-])(?:{ROOTS})/[A-Za-z0-9_]")


def references(text: str) -> Iterable[int]:
    """The numbers of the lines that reference an end-to-end test."""
    lines = enumerate(text.splitlines(), 1)
    return (number for number, line in lines if END_TO_END_TEST.search(line))


class EndToEndTestReferences:
    info = RuleInfo(
        "no-end-to-end-tests-in-public-documentation",
        "Public documentation does not reference end-to-end tests",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        # Internal documentation may name the end-to-end tests it describes.
        public = (
            name for name in context.workspace.documents if not internal_document(name)
        )
        for name in public:
            for number in references(context.workspace.text(name)):
                yield Finding(
                    Location(name, number),
                    "show a runnable example from examples/ instead of an end-to-end test",
                )
