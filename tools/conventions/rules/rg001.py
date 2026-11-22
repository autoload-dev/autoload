"""RG001: owned Bazel package segments use lower snake case."""

from collections.abc import Iterable

from tools.conventions.context import Context, Location
from tools.conventions.framework import Finding, RuleInfo
from tools.conventions.naming import LOWER_SNAKE_CASE


class PackageNames:
    info = RuleInfo(
        "RG001",
        "Package segments use lower snake case",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        for module in context.workspace.modules:
            for build in module.builds:
                package = build.parent.relative_to(module.path)
                # A repeated segment is one finding for this BUILD file.
                for segment in dict.fromkeys(package.parts):
                    if not LOWER_SNAKE_CASE.fullmatch(segment):
                        yield Finding(
                            Location(build.as_posix(), 1),
                            f"package segment {segment!r} must use lower_snake_case",
                        )
