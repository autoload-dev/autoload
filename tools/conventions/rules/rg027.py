"""RG027: the add-on modules' Python targets carry `lint-genfiles`."""

from collections.abc import Iterable

from tools.conventions.context import Context
from tools.conventions.framework import Finding, RuleInfo
from tools.setup.modules import is_addon_module

# The kinds the lint aspects visit (tools/lint/linters.bzl).
PYTHON = frozenset({"py_binary", "py_library", "py_test"})

# The tag that has rules_lint lint the sources of a target outside the main repository.
TAG = "lint-genfiles"


class LintedAddonPython:
    info = RuleInfo("RG027", "The add-on modules' Python targets carry lint-genfiles")

    def evaluate(self, context: Context) -> Iterable[Finding]:
        for module in context.workspace.modules:
            if not is_addon_module(module.path):
                continue
            for target in context.bazel.rules(module):
                if target.kind in PYTHON and TAG not in target.string_lists.get(
                    "tags", ()
                ):
                    yield Finding(
                        target.origin,
                        f"{target.kind} is linted from the root module, which sees an "
                        f'add-on module\'s sources only with tags = ["{TAG}"]',
                    )
