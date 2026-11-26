"""RG026: a test that starts a Godot process carries the godot_process tag."""

from collections.abc import Iterable

from tools.conventions.context import Context, Module, Target
from tools.conventions.framework import Finding, RuleInfo
from tools.setup.modules import is_registry_test_module

# The tag that keeps a test out of the fast tests, `--config=fast`.
TAG = "godot_process"

# The toolchain types through which a build or a test starts the Godot editor or runtime.
TOOLCHAIN_TYPES = (
    "@autoload_rules_godot//godot:editor_toolchain_type",
    "@autoload_rules_godot//godot:runtime_toolchain_type",
    "@autoload_rules_godot//godot/private/config:target_execution_toolchain_type",
)

# Analysis tests run no action; manual tests run only when named.
EXEMPT = frozenset({"manual", "starlark_analysis_test"})


class GodotProcessTests:
    info = RuleInfo(
        "RG026",
        "Tests that start a Godot process carry the godot_process tag",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        for module in context.workspace.modules:
            if not is_registry_test_module(module.path):
                yield from self.module(context, module)

    def module(self, context: Context, module: Module) -> Iterable[Finding]:
        tests = context.bazel.module_tests(module)
        godot = context.bazel.dependent_tests(module, TOOLCHAIN_TYPES)
        for target in context.bazel.rules(module):
            if target.label in tests:
                message = self.problem(target, target.label in godot)
                if message:
                    yield Finding(target.origin, f"{target.label} {message}")

    @staticmethod
    def problem(target: Target, starts_godot: bool) -> str | None:
        tags = frozenset(target.string_lists.get("tags", ()))
        if tags & EXEMPT:
            return None
        if "smoke" in tags:
            if TAG in tags:
                return f"is a smoke test, which runs with the fast tests: remove {TAG}"
            return None
        if starts_godot and TAG not in tags:
            return f"starts a Godot process: tag it {TAG}"
        if not starts_godot and TAG in tags:
            return f"starts no Godot process: remove {TAG}"
        return None
