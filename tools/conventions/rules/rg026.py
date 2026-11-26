"""RG026: a test that starts a Godot process carries the godot_process tag."""

from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor

from tools.conventions.context import Context, Target
from tools.conventions.framework import Finding, RuleInfo

# The tag that keeps a test out of the fast tests, `--config=fast`.
TAG = "godot_process"

# The toolchain types through which a build or a test starts the Godot editor or runtime.
TOOLCHAIN_TYPES = (
    "@autoload_rules_godot//godot:editor_toolchain_type",
    "@autoload_rules_godot//godot:runtime_toolchain_type",
    "@autoload_rules_godot//godot/private/config:target_execution_toolchain_type",
)

# Analysis tests run no action; manual and source-engine tests run only when named or selected
# (`--config=source-engine`), and loading the latter's graph would fetch engine sources.
EXEMPT = frozenset({"manual", "source_engine", "starlark_analysis_test"})


class GodotProcessTests:
    info = RuleInfo(
        "RG026",
        "Tests that start a Godot process carry the godot_process tag",
        evaluated=True,
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        modules = context.workspace.loaded_modules
        # The ruleset and the root module load in workspaces of their own: query concurrently.
        with ThreadPoolExecutor() as pool:
            godot = list(
                pool.map(
                    lambda module: context.bazel.dependent_tests(
                        module, TOOLCHAIN_TYPES, tuple(sorted(EXEMPT))
                    ),
                    modules,
                )
            )
        for module, tests in zip(modules, godot, strict=True):
            for target in context.bazel.rules(module):
                message = target.is_test and self.problem(target, target.label in tests)
                if message:
                    yield Finding(target.origin, f"{target.label} {message}")

    @staticmethod
    def problem(target: Target, starts_godot: bool) -> str | None:
        tags = frozenset(target.string_lists.get("tags", ()))
        if tags & EXEMPT:
            return None
        needs_tag = starts_godot and "smoke" not in tags
        if (TAG in tags) == needs_tag:
            return None
        if "smoke" in tags:
            return f"is a smoke test, which runs with the fast tests: remove {TAG}"
        if starts_godot:
            return f"starts a Godot process: tag it {TAG}"
        return f"starts no Godot process: remove {TAG}"
