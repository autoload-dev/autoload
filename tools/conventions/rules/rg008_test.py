"""The directory of a project or add-on determines application resource ownership."""

import unittest

from tools.conventions.rules.rg008 import ApplicationContent
from tools.conventions.test_support import Record, RepositoryTest

APP = "tests/game"


def resources(srcs: list[str], resource_paths: dict[str, str] | None = None) -> Record:
    return {
        "name": "//:resources",
        "path": "BUILD.bazel",
        "kind": "godot_resources",
        "booleans": {"testonly": False},
        "label_lists": {"srcs": srcs},
        "label_keyed_strings": {"resource_paths": resource_paths or {}},
    }


class ApplicationContentTest(RepositoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.write_consumer_modules()

    def evaluate(self, records: list[Record], sources: dict[str, str]) -> list[str]:
        for name in sources.values():
            self.write(name, "")
        context = self.context(records=records, sources=sources)
        return [item.location.path for item in ApplicationContent().evaluate(context)]

    def test_physical_paths_are_checked_independently_of_resource_paths(self) -> None:
        self.assertEqual(
            [APP + "/content/game.gd"],
            self.evaluate(
                [resources([], {"//:bad": "main/game.gd", "//:good": "data.json"})],
                {"//:bad": APP + "/content/game.gd", "//:good": APP + "/main/data.json"},
            ),
        )

    def test_shared_resources_check_each_authored_source_once_and_skip_generated_outputs(
        self,
    ) -> None:
        other = resources(["//:game.gd"])
        other["name"] = "//:other_resources"
        records: list[Record] = [
            resources(["//:game.gd"], {"//:generated": "data.gd"}),
            other,
            {
                "name": "//:generated",
                "path": "BUILD.bazel",
                "kind": "genrule",
                "outputs": ["//:data.gd"],
            },
        ]
        self.assertEqual(
            [APP + "/game.gd"], self.evaluate(records, {"//:game.gd": APP + "/game.gd"})
        )

    def test_addon_namespace_cannot_exempt_a_project_owned_source(self) -> None:
        unit = resources(["//:counter.gd"])
        unit["strings"] = {"prefix": "addons/counter"}
        self.assertEqual(
            [APP + "/counter.gd"],
            self.evaluate([unit], {"//:counter.gd": APP + "/counter.gd"}),
        )

    def test_typed_addon_implementation_does_not_belong_to_its_consumer(self) -> None:
        self.assertEqual(
            [],
            self.evaluate(
                [resources(["//:counter.gd"])],
                {"//:counter.gd": "tests/shared_addon/runtime/counter.gd"},
            ),
        )

    def test_test_only_or_generated_project_contexts_do_not_exempt_application_content(
        self,
    ) -> None:
        for test_only in (True, False):
            project: Record = {
                "name": "//:project",
                "path": "BUILD.bazel",
                "kind": "godot_project",
                "booleans": {"testonly": test_only},
            }
            if not test_only:
                project["strings"] = {"generator_function": "godot_test"}
            self.assertEqual(
                [APP + "/game.gd"],
                self.evaluate(
                    [project, resources(["//:game.gd"])], {"//:game.gd": APP + "/game.gd"}
                ),
            )
        suite = resources(["//:suite.gd"])
        suite["booleans"] = {"testonly": True}
        self.assertEqual(
            [], self.evaluate([suite], {"//:suite.gd": APP + "/tests/unit/Suite.gd"})
        )
        self.assertEqual(
            [APP + "/game.gd"],
            self.evaluate([suite], {"//:suite.gd": APP + "/game.gd"}),
        )

    def test_nested_operating_system_contexts_and_addon_demo_have_their_own_main(
        self,
    ) -> None:
        sources = {
            "//:config": APP + "/android/project.godot",
            "//:good": APP + "/android/main/game.gd",
            "//:bad": "examples/addons/counter/demo/game.gd",
        }
        self.assertEqual(
            ["examples/addons/counter/demo/game.gd"],
            self.evaluate([resources(["//:good", "//:bad"])], sources),
        )

    def test_test_scope_requires_every_resources_target_to_be_test_only(self) -> None:
        for path in (
            APP + "/tests/Suite.gd",
            "tests/shared_addon/tests/unit/Suite.gd",
            "examples/addons/counter/tests/integration/Suite.gd",
        ):
            with self.subTest(path=path):
                suite = resources(["//:suite"])
                suite["booleans"] = {"testonly": True}
                self.assertEqual([], self.evaluate([suite], {"//:suite": path}))
                production = resources(["//:suite"])
                production["name"] = "//:production"
                self.assertEqual(
                    [path],
                    self.evaluate([suite, production], {"//:suite": path}),
                )

    def test_sources_can_be_owned_by_another_module(self) -> None:
        self.write("consumer/MODULE.bazel", "")
        self.write("consumer/BUILD.bazel", "")
        self.write(APP + "/content/game.gd", "")
        unit = resources([], {"@fixture//:game.gd": "game.gd"})
        unit["path"] = "consumer/BUILD.bazel"
        context = self.context(
            records=[unit],
            sources={"@fixture//:game.gd": APP + "/content/game.gd"},
        )
        self.assertEqual(
            [APP + "/content/game.gd"],
            [item.location.path for item in ApplicationContent().evaluate(context)],
        )

    def test_shared_application_inputs_need_main_without_a_configuration_whitelist(
        self,
    ) -> None:
        self.assertEqual(
            [APP + "/bootstrap.gd"],
            self.evaluate(
                [resources(["//:bootstrap"])], {"//:bootstrap": APP + "/bootstrap.gd"}
            ),
        )

    def test_unknown_membership_and_aggregate_inputs_are_not_compliance_results(
        self,
    ) -> None:
        unit = resources([])
        del unit["label_lists"]
        context = self.context(records=[unit])
        self.assertEqual(
            ["not_checked"],
            [item.status for item in ApplicationContent().evaluate(context)],
        )
        group: Record = {
            "name": "//:configuration",
            "path": "BUILD.bazel",
            "kind": "filegroup",
        }
        context = self.context(records=[resources(["//:configuration"]), group])
        self.assertEqual(
            ["not_checked"],
            [item.status for item in ApplicationContent().evaluate(context)],
        )


if __name__ == "__main__":
    unittest.main()
