"""Repository interfaces must remain complete despite metadata-only API defaults."""

import json
import unittest
from dataclasses import replace
from types import MappingProxyType, SimpleNamespace

from tools.docs.evidence import Evidence, Labels, decode_configured, decode_loading
from tools.docs.output_contracts import ConfiguredTarget, Contract
from tools.docs.repository_contracts import check_repository, repository_errors

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


def evidence(loading: str, *configurations: tuple[dict, list[str]]) -> Evidence:
    """Evidence of a genquery's XML and configurations of Java libraries."""
    return Evidence(
        decode_loading(loading, Labels({})),
        tuple(
            decode_configured(
                json.dumps(
                    {
                        "settings": settings,
                        "facts": [
                            {
                                "label": label,
                                "files": 1,
                                "runfiles": 0,
                                "executable": False,
                                "providers": ["CcInfo", "JavaInfo"],
                                "groups": [],
                            }
                            for label in labels
                        ],
                    }
                )
            )
            for settings, labels in configurations
        ),
    )


HUB = """<query version="2">
    <rule class="cc_library" location="BUILD.bazel:1:1" name="@cpp//:godot_cpp">
        <list name="visibility"><label value="//visibility:public"/></list>
    </rule>
    <rule class="cc_library" location="BUILD.bazel:2:1" name="@other//:godot_cpp">
        <list name="visibility"><label value="//visibility:public"/></list>
    </rule>
</query>"""


class CheckRepositoryTest(unittest.TestCase):
    def test_only_the_case_s_repositories_and_configuration_count(self) -> None:
        settings = {"//command_line_option:platforms": "//:android"}
        case = CASE | {"settings": settings}
        self.assertEqual(
            [],
            check_repository(evidence(HUB, (settings, [LABEL])), case, contract()),
        )


if __name__ == "__main__":
    unittest.main()
