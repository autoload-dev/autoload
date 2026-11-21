"""Repository interfaces must remain complete despite metadata-only API defaults."""

import unittest
from dataclasses import replace
from types import MappingProxyType, SimpleNamespace

from tools.docs.output_contracts import ConfiguredTarget, Contract
from tools.docs.repository_contracts import repository_errors, toolchain_bound

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
        booleans=MappingProxyType(booleans),
        label_lists=MappingProxyType({"visibility": ("//visibility:public",)}),
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


if __name__ == "__main__":
    unittest.main()
