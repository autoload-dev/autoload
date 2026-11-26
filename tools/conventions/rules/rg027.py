"""RG027: the add-on modules' Python targets carry `lint-genfiles`."""

from collections.abc import Iterable

from tools.conventions.context import Context
from tools.conventions.framework import Finding, RuleInfo
from tools.setup.modules import is_addon_module

# The kinds rules_lint's Ruff and ty aspects visit by default, as
# tools/lint/linters.bzl keeps them.
PYTHON = frozenset({"py_binary", "py_library", "py_test"})

# The tag that has rules_lint lint the sources of a target outside the main repository.
TAG = "lint-genfiles"


class LintedAddonPython:
    info = RuleInfo("RG027", "The add-on modules' Python targets carry lint-genfiles")

    def evaluate(self, context: Context) -> Iterable[Finding]:
        addons = (m for m in context.workspace.modules if is_addon_module(m.path))
        for module in addons:
            for target in context.bazel.rules(module):
                tags = target.string_lists.get("tags", ())
                if target.kind in PYTHON and TAG not in tags:
                    yield Finding(
                        target.origin,
                        f"{target.kind} is linted from the root module, which sees an "
                        f'add-on module\'s sources only with tags = ["{TAG}"]',
                    )
