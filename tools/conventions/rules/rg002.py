"""RG002: authored targets use lower snake case; ruleset-owned roles use dots."""

from collections.abc import Iterable, Mapping
from dataclasses import replace

from tools.conventions.context import Context, Declaration, Location, Target
from tools.conventions.framework import Finding, RuleInfo
from tools.conventions.naming import LOWER_SNAKE_CASE

# Computed macro roots a maintainer reviewed, by BUILD file. Each entry lists the
# authored roots of one computed call, such as a comprehension. The roots are the
# emitted names without a dotted role, so a changed root set needs a new review.
REVIEWED: Mapping[str, tuple[tuple[str, ...], ...]] = {
    "godot/platforms/private/tests/app_platform_selection/BUILD.bazel": (
        (
            "linux_app_contains_selected_platform_libraries_test",
            "macos_app_contains_selected_platform_libraries_test",
        ),
        (
            "android_apk_contains_selected_platform_libraries_test",
            "android_dual_abi_bundle_contains_selected_platform_libraries_test",
        ),
        (
            "ios_dual_simulator_app_contains_selected_platform_libraries_test",
            "ios_simulator_app_contains_selected_platform_libraries_test",
            "ios_simulator_debug_app_contains_selected_platform_libraries_test",
            "ios_source_simulator_app_contains_selected_platform_libraries_test",
        ),
    ),
    "godot/engine/private/tests/fixtures/release_override/BUILD.bazel": (
        (
            "runtime_linux_arm64_release",
            "runtime_linux_x86_64_release",
            "runtime_macos_arm64_release",
            "runtime_macos_x86_64_release",
        ),
    ),
    "godot/platforms/private/tests/platform_libraries/fixtures/extension_library_declarations/BUILD.bazel": (
        ("collision_a", "collision_b"),
    ),
    "godot/private/config/tests/fixtures/desktop_runtimes_only/BUILD.bazel": (
        (
            "runtime_linux_arm64",
            "runtime_linux_x86_64",
            "runtime_macos_arm64",
            "runtime_macos_x86_64",
        ),
    ),
    "godot/private/tests/validation/BUILD.bazel": (
        (
            "validation_runs_no_project_code_authored_autoload_project_test",
            "validation_runs_no_project_code_autoload_project_test",
        ),
        (
            "validation_follows_warning_settings_addon_warnings_project_test",
            "validation_follows_warning_settings_project_test",
            "validation_follows_warning_settings_warnings_project_test",
        ),
    ),
}


def computed_roots(declaration: Declaration) -> tuple[str, ...]:
    """Return the authored roots of a macro call: emitted names without a role."""
    names = (target.label.split(":", 1)[1] for target in declaration.targets)
    return tuple(sorted({name for name in names if not set("./") & set(name)}))


def _in_namespace(root: str, name: str) -> bool:
    return name == root or name.startswith((root + ".", "lib" + root))


def _in_dotted_namespace(root: str, name: str) -> bool:
    # rules_android and rules_apple derive delivered basenames from a slash suffix, so each
    # segment after a slash restarts at the root (see godot/app.bzl).
    for index, segment in enumerate(name.split("/")):
        if index and segment == root:
            continue
        role = segment.removeprefix(root + ".")
        if role == segment or not all(
            LOWER_SNAKE_CASE.fullmatch(part) for part in role.split(".")
        ):
            return False
    return True


def _shared_library(kind: str, targets: Iterable[Target], name: str) -> bool:
    # An explicitly named shared library is an artifact identity, as allowed by
    # the naming policy. This rule owns the qualification.
    return (
        kind == "cc_binary"
        and all(target.booleans.get("linkshared", False) for target in targets)
        and "/" not in name
        and name.endswith((".so", ".dylib", ".dll"))
    )


class TargetNames:
    info = RuleInfo(
        "RG002",
        "Ordinary target names use lower snake case",
        "docs/public/conventions.md#rg002",
    )

    def __init__(
        self, reviewed: Mapping[str, tuple[tuple[str, ...], ...]] = REVIEWED
    ) -> None:
        self.reviewed = reviewed

    def evaluate(self, context: Context) -> Iterable[Finding]:
        used = set()
        for module in context.workspace.modules:
            for declaration in context.declarations(module):
                call = declaration.call
                macro = self._from_macro(declaration)
                owner = context.macro_owner(module, declaration) if macro else None
                if call.literal_name is None and macro:
                    # Bazel generator_name may name an internal macro helper. It is
                    # not proof of the caller's evaluated name, so a person reviews it.
                    if "name" not in call.attrs:
                        continue
                    roots = computed_roots(declaration)
                    if roots not in self.reviewed.get(call.location.path, ()):
                        yield Finding(
                            call.location,
                            f"computed macro roots {', '.join(roots) or '(none)'} need a review in RG002",
                            "not_checked",
                            required=self._owns_namespace(owner),
                        )
                        continue
                    used.add((call.location.path, roots))
                    for target in declaration.targets:
                        name = target.label.split(":", 1)[1]
                        owners = [root for root in roots if _in_namespace(root, name)]
                        if len(owners) != 1:
                            yield Finding(
                                call.location,
                                f"generated target {name!r} has unresolved reviewed ownership",
                                "not_checked",
                                required=True,
                            )
                            continue
                        rooted = replace(
                            declaration,
                            call=replace(call, literal_name=owners[0]),
                            targets=(target,),
                        )
                        yield from self._evaluate_names(rooted, owner)
                    continue
                yield from self._evaluate_names(declaration, owner)
        for path, roots in sorted(
            {
                (path, roots)
                for path, reviews in self.reviewed.items()
                for roots in reviews
            }
            - used
        ):
            yield Finding(
                Location(path, 1),
                f"reviewed roots {', '.join(roots)} match no computed macro call; remove them from RG002",
            )

    @staticmethod
    def _from_macro(declaration: Declaration) -> bool:
        return any(
            target.strings.get("generator_function") for target in declaration.targets
        )

    @staticmethod
    def _owns_namespace(owner: str | None) -> bool:
        # Evaluated source ownership covers every ruleset module, including a newly
        # inventoried producer; function spelling alone never grants ownership. Test
        # suites in a tests package are no producers: rules_testing names each test
        # after its function, as the verification architecture's naming rules expect.
        if owner is None:
            return False
        package = owner.split("%", 1)[0].split(":", 1)[0]
        if package.endswith("/tests") or "/tests/" in package:
            return False
        return package.startswith("//godot")

    def _evaluate_names(
        self, declaration: Declaration, owner: str | None
    ) -> Iterable[Finding]:
        call = declaration.call
        # The explicit invocation root is stronger evidence than generator_name,
        # which nested macros overwrite. Every emitted label belongs to this call.
        root = call.literal_name
        names = [target.label.split(":", 1)[1] for target in declaration.targets]
        macro = self._from_macro(declaration)
        if macro and not self._owns_namespace(owner):
            # Other macro APIs may use name as a factory prefix, not a target root.
            # Their authored identity retains the ordinary spelling check; Godot's
            # registered public producers own complete generated namespaces.
            names = [root] if root is not None else names
            root = None
        if root is not None and macro:
            if not LOWER_SNAKE_CASE.fullmatch(root):
                yield Finding(
                    call.location, f"target name {root!r} must use lower_snake_case"
                )
                return
            for target in declaration.targets:
                name = target.label.split(":", 1)[1]
                if name == root or _shared_library(target.kind, (target,), name):
                    continue
                if not _in_dotted_namespace(root, name):
                    yield Finding(
                        call.location,
                        f"generated target {name!r} must stay in {root!r}'s dotted namespace",
                    )
            return
        for name in names:
            if LOWER_SNAKE_CASE.fullmatch(name) or _shared_library(
                call.kind, declaration.targets, name
            ):
                continue
            yield Finding(
                call.location, f"target name {name!r} must use lower_snake_case"
            )
