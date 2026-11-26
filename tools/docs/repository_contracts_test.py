"""Repository interfaces must remain complete despite metadata-only API defaults."""

import unittest
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

from tools.conventions.context import Module
from tools.docs.evidence import EvaluatedBazel
from tools.docs.output_contracts import ConfiguredTarget, Contract
from tools.docs.repository_contracts import (
    check_public_libraries,
    library_errors,
    library_lane_errors,
    repository_errors,
    toolchain_bound,
)

LABEL = "@cpp//:godot_cpp"


def contract(kind: str = "library", testonly: str = "false") -> Contract:
    row = {
        "name": "@{repository}//:godot_cpp",
        "kind": kind,
        "visibility": "public",
        "testonly": testonly,
        "availability": "always",
    }
    return Contract(
        ({"kind": "repository", "cardinality": "none", "availability": "always"},),
        (),
        (row,),
    )


def rule(kind: str = "cc_library", **booleans: bool) -> SimpleNamespace:
    return SimpleNamespace(
        kind=kind,
        is_test=kind.endswith("_test"),
        booleans=MappingProxyType(booleans),
        label_lists=MappingProxyType({"visibility": ("//visibility:public",)}),
    )


def replace_visibility(
    target: SimpleNamespace, grants: tuple[str, ...]
) -> SimpleNamespace:
    return SimpleNamespace(
        **vars(target) | {"label_lists": MappingProxyType({"visibility": grants})}
    )


CASE = {"conditions": [], "entrypoints": {"@{repository}//:godot_cpp": [LABEL]}}
LIBRARY = ConfiguredTarget(LABEL, 1, 0, False, frozenset({"CcInfo"}), frozenset())


class RepositoryContractsTest(unittest.TestCase):
    def errors(
        self, contract: Contract, rules: dict, observed: dict, case: dict = CASE
    ) -> list[str]:
        return repository_errors(contract, case, rules, set(), observed)

    def test_matching_repository(self) -> None:
        self.assertEqual([], self.errors(contract(), {LABEL: rule()}, {LABEL: LIBRARY}))

    def test_new_public_helper_cannot_hide_in_repository_default(self) -> None:
        rules = {LABEL: rule(), "@cpp//:bindings.headers": rule("filegroup")}
        errors = self.errors(contract(), rules, {LABEL: LIBRARY})
        self.assertIn(
            "undocumented public repository rule: @cpp//:bindings.headers", errors
        )

    def test_grants_within_the_repository_are_not_consumer_access(self) -> None:
        def granted(*grants: str) -> SimpleNamespace:
            return replace_visibility(rule("aar_import"), grants)

        internal = "@cpp//android:release_tuned"
        rules = {LABEL: rule(), internal: granted("@cpp//toolchains:__pkg__")}
        self.assertEqual([], self.errors(contract(), rules, {LABEL: LIBRARY}))
        # A grant to a package of another repository still reaches consumers.
        rules[internal] = granted("@cpp//toolchains:__pkg__", "@app//:__pkg__")
        errors = self.errors(contract(), rules, {LABEL: LIBRARY})
        self.assertIn(f"undocumented public repository rule: {internal}", errors)

    def test_undocumented_entrypoint_and_default_kind_are_rejected(self) -> None:
        errors = self.errors(
            Contract(({"kind": "metadata", "cardinality": "none"},)),
            {LABEL: rule()},
            {LABEL: LIBRARY},
        )
        self.assertIn(
            "evaluated repository API must declare repository default kind", errors
        )
        self.assertIn(
            "undocumented repository entrypoint: @{repository}//:godot_cpp", errors
        )

    def test_entrypoints_use_shared_kind_semantics(self) -> None:
        executable = replace(LIBRARY, executable=True, runfiles=1)
        cases = [
            ("library", rule(), executable, "undocumented executable behavior"),
            ("library", rule("cc_binary", linkshared=True), executable, None),
            ("test", rule(), executable, "promised test is not an evaluated Bazel test"),
            (
                "files",
                rule("sh_test"),
                executable,
                "undocumented evaluated test behavior",
            ),
            ("metadata", rule(), LIBRARY, "metadata must not produce default files"),
        ]
        for kind, evaluated, target, expected in cases:
            with self.subTest(kind=kind, evaluated=evaluated.kind):
                errors = self.errors(contract(kind), {LABEL: evaluated}, {LABEL: target})
                if expected is None:
                    self.assertEqual([], errors)
                else:
                    self.assertIn(f"{LABEL}: {expected}", errors)

    def test_testonly_follows_evaluated_facts(self) -> None:
        errors = self.errors(contract(testonly="true"), {LABEL: rule()}, {LABEL: LIBRARY})
        self.assertIn(f"{LABEL}: source testonly differs from evaluated loading", errors)

    def test_inactive_conditional_rows_scope_discovery(self) -> None:
        mobile = {
            "name": "@{repository}//toolchains:runtime_android_{cpu}_{variant}",
            "kind": "files",
            "visibility": "public",
            "testonly": "false",
            "availability": "android_shell",
        }
        base = contract()
        scoped = replace(base, companions=(*base.companions, mobile))
        android = "@cpp//toolchains:runtime_android_arm64_release"
        rules = {LABEL: rule(), android: rule("filegroup")}
        # A case without the condition does not observe that row's targets.
        self.assertEqual([], self.errors(scoped, rules, {LABEL: LIBRARY}))
        # Placeholders stay within one name segment: an unrelated target is still reported.
        stray = "@cpp//toolchains:runtime_android_arm64_release/extra"
        errors = self.errors(scoped, rules | {stray: rule("filegroup")}, {LABEL: LIBRARY})
        self.assertEqual([f"undocumented public repository rule: {stray}"], errors)

    def test_missing_dataset_and_configured_entrypoint_fail(self) -> None:
        case = {
            "conditions": [],
            "entrypoints": {
                "@{repository}//:godot_cpp": [],
                "@{repository}//:extra": [LABEL],
            },
        }
        errors = self.errors(contract(), {}, {}, case)
        self.assertIn("missing acquired dataset: @{repository}//:godot_cpp", errors)
        self.assertIn(f"missing public repository target: {LABEL}", errors)
        self.assertIn(f"missing configured repository entrypoint: {LABEL}", errors)


class ToolchainBoundTest(unittest.TestCase):
    def test_only_implementations_of_constrained_toolchains_are_bound(self) -> None:
        def toolchain(implementation: str, *constraints: str) -> SimpleNamespace:
            return SimpleNamespace(
                kind="toolchain",
                labels=MappingProxyType({"toolchain": implementation}),
                label_lists=MappingProxyType({"exec_compatible_with": constraints}),
            )

        rules: dict = {
            "@hub//toolchains:editor": rule(),
            "@hub//toolchains:macos": toolchain(
                "@@+ext+hub//toolchains:editor", "@platforms//os:macos"
            ),
            "@hub//toolchains:runtime": rule(),
            "@hub//toolchains:any": toolchain("@@+ext+hub//toolchains:runtime"),
            "@hub//toolchains:library": rule(),
        }
        self.assertEqual(
            ["@hub//toolchains:editor"], toolchain_bound(sorted(rules), rules)
        )


class LibraryErrorsTest(unittest.TestCase):
    PLUGIN_API = "//godot/platforms:android_plugin_api"

    def errors(self, *providers: str) -> list[str]:
        target = ConfiguredTarget(
            self.PLUGIN_API, 1, 0, False, frozenset(providers), frozenset()
        )
        return library_errors(self.PLUGIN_API, target, "JavaInfo")

    def test_library_with_its_provider(self) -> None:
        self.assertEqual([], self.errors("@@rules_java+//java:java_info.bzl%JavaInfo"))

    def test_library_without_its_provider(self) -> None:
        self.assertEqual(
            [self.PLUGIN_API + ": public library is missing JavaInfo"],
            self.errors("CcInfo"),
        )

    def test_incompatible_library_is_no_evidence(self) -> None:
        self.assertEqual(
            [
                self.PLUGIN_API
                + ": public library is incompatible with its lane's configuration"
            ],
            self.errors("IncompatiblePlatformProvider", "JavaInfo"),
        )


JAVA_INFO = "@@rules_java+//java:java_info.bzl%JavaInfo"
ANDROID_LIBRARY = MappingProxyType(
    {"lane": "android", "options": ("--config=android",), "provider": "JavaInfo"}
)


class RecordingBazel(EvaluatedBazel):
    """Answer every cquery with Java libraries and record its labels and options."""

    def __init__(self) -> None:
        super().__init__(Path())
        self.calls: list[tuple[list[str], tuple[str, ...]]] = []

    def configured(
        self, module: Module, labels: Iterable[str], options: Iterable[str] = ()
    ) -> dict[str, ConfiguredTarget]:
        labels = list(labels)
        self.calls.append((labels, tuple(options)))
        return {
            label: ConfiguredTarget(
                label, 1, 0, False, frozenset({JAVA_INFO}), frozenset()
            )
            for label in labels
        }


class PublicLibrariesTest(unittest.TestCase):
    def test_one_cquery_per_configuration_of_the_lane(self) -> None:
        libraries = {
            "//a:api": ANDROID_LIBRARY,
            "//b:api": ANDROID_LIBRARY,
            "//c:api": {**ANDROID_LIBRARY, "lane": "ios"},
        }
        bazel = RecordingBazel()
        self.assertEqual([], check_public_libraries(bazel, libraries, "android"))
        self.assertEqual([(["//a:api", "//b:api"], ("--config=android",))], bazel.calls)

    def test_library_of_no_contract_lane_is_rejected(self) -> None:
        self.assertEqual(
            ["//a:api: public library names no contract lane: andriod"],
            library_lane_errors({"//a:api": {**ANDROID_LIBRARY, "lane": "andriod"}}),
        )


if __name__ == "__main__":
    unittest.main()
