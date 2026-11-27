"""
exported-files-declare-visibility: every exports_files call states who may see the files.
"""

from collections.abc import Iterable

from tools.conventions.context import Context
from tools.conventions.framework import Finding, RuleInfo


class ExportedFilesDeclareVisibility:
    info = RuleInfo(
        "exported-files-declare-visibility",
        "Every exports_files call states who may see the files",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        for module in context.workspace.modules:
            for call in context.starlark.calls(module):
                if call.kind == "exports_files" and "visibility" not in call.attrs:
                    yield Finding(
                        call.location,
                        "exports_files without visibility makes the files public, whatever "
                        "the package's default_visibility; name who may see them",
                    )
