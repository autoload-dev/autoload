"""Engine modules, patches and source build files of a consumer sit under engines/<name>/."""

import unittest

from tools.conventions.rules.rg014 import EngineLayout
from tools.conventions.test_support import RepositoryTest

ENGINE_ENTRIES = (
    "an engines/<name>/ directory holds only modules/, patches/, a BUILD file, lock files, "
    ".bzl files and a README.md"
)
MODULE = ("config.py", "SCsub", "register_types.cpp", "register_types.h", "field.cpp")


class EngineLayoutTest(RepositoryTest):
    def evaluate(self, *names: str) -> list[str]:
        self.write_consumer_modules()
        for name in names:
            self.write(name, "")
        context = self.context()
        return [
            f"{item.location.path}: {item.message}"
            for item in EngineLayout().evaluate(context)
        ]

    def project(self, root: str, *extra: str) -> tuple[str, ...]:
        return tuple(
            root + "/" + suffix
            for suffix in ("BUILD.bazel", "project.godot", "main/game.gd", *extra)
        )

    def module(self, directory: str, *files: str) -> tuple[str, ...]:
        return tuple(directory + "/" + name for name in (files or MODULE))

    def test_compliant_engine_with_modules_and_patches_has_no_findings(self) -> None:
        engine = "e2e/rules_godot/projects/patched/engines/patched"
        self.assertEqual(
            [],
            self.evaluate(
                *self.project("e2e/rules_godot/projects/patched"),
                *self.module(engine + "/modules/bazel_probe"),
                *self.module(engine + "/modules/other", "config.py", "SCsub"),
                engine + "/modules/bazel_probe/BUILD.bazel",
                engine + "/patches/BUILD.bazel",
                engine + "/patches/engine-name.patch",
                engine + "/patches/renderer.diff",
                engine + "/BUILD.bazel",
                engine + "/README.md",
                engine + "/godot_patched.lock.json",
                engine + "/source_engine.bzl",
            ),
        )

    def test_an_engine_may_lie_anywhere_and_registration_sets_sit_beside_it(self) -> None:
        self.assertEqual(
            [],
            self.evaluate(
                *self.module(
                    "examples/engines/simulation/modules/field", "config.py", "SCsub"
                ),
                "examples/engines/simulation/simulation.lock.json",
                "examples/engines/simulation/BUILD.bazel",
                "e2e/rules_godot/scenario/engines/stable/BUILD.bazel",
                "e2e/rules_godot/scenario/engines/source/components.bzl",
            ),
        )

    def test_an_engine_s_lock_file_in_a_project_is_reported(self) -> None:
        root = "examples/petri"
        self.assertEqual(
            [
                (
                    f"{root}/simulation.lock.json: an engine's lock file must live "
                    "under engines/<name>/, not in a Godot project"
                )
            ],
            self.evaluate(*self.project(root, "simulation.lock.json")),
        )

    def test_lock_files_and_patches_outside_projects_are_not_engine_files(self) -> None:
        self.assertEqual(
            [],
            self.evaluate(
                "multitool.lock.json",
                "third_party/godot_simulator.patch",
                "tools/docs/api.patch",
                *self.project("examples/game"),
            ),
        )

    def test_project_without_engine_directory_has_no_findings(self) -> None:
        self.assertEqual([], self.evaluate(*self.project("examples/game")))

    def test_module_outside_engine_modules_is_reported_once_at_its_config(self) -> None:
        root = "examples/game"
        findings = self.evaluate(
            *self.project(root),
            *self.module(root + "/modules/reaction_diffusion"),
            *self.module(root + "/main/native", "config.py", "register_types.cpp"),
            *self.module("examples/engines/ok/modules/ok", "config.py", "SCsub"),
        )
        self.assertEqual(
            findings,
            [
                (
                    f"{root}/main/native/config.py: engine module must live under "
                    f"engines/<name>/modules/: {root}/main/native"
                ),
                (
                    f"{root}/modules/reaction_diffusion/config.py: engine module must live "
                    f"under engines/<name>/modules/: {root}/modules/reaction_diffusion"
                ),
            ],
        )

    def test_module_beside_a_project_is_reported_too(self) -> None:
        self.assertEqual(
            [
                (
                    "examples/engine/modules/field/config.py: engine module must live "
                    "under engines/<name>/modules/: examples/engine/modules/field"
                )
            ],
            self.evaluate(
                *self.module("examples/engine/modules/field", "config.py", "SCsub")
            ),
        )

    def test_config_without_scsub_or_register_types_is_not_a_module(self) -> None:
        root = "examples/game"
        self.assertEqual(
            [],
            self.evaluate(
                *self.project(root),
                root + "/tools/config.py",
                root + "/tools/SCsub.txt",
                root + "/main/native/register_types.cc",
            ),
        )

    def test_patch_in_a_project_is_reported_but_a_patch_of_an_engine_is_not(self) -> None:
        root = "e2e/rules_godot/projects/patched"
        findings = self.evaluate(
            *self.project(root),
            root + "/patches/engine-name.patch",
            root + "/main/fix.diff",
            root + "/engines/patched/patches/ok.patch",
        )
        self.assertEqual(
            findings,
            [
                (
                    f"{root}/main/fix.diff: engine patch must live under "
                    "engines/<name>/patches/, not in a Godot project"
                ),
                (
                    f"{root}/patches/engine-name.patch: engine patch must live under "
                    "engines/<name>/patches/, not in a Godot project"
                ),
            ],
        )

    def test_stray_entries_in_an_engine_are_reported_once_per_entry(self) -> None:
        engine = "e2e/rules_godot/projects/patched/engines/patched"
        findings = self.evaluate(
            engine + "/BUILD.bazel",
            engine + "/notes.txt",
            engine + "/scripts/a.py",
            engine + "/scripts/b.py",
            engine + "/patches/ok.patch",
        )
        self.assertEqual(
            findings,
            [
                (
                    f"{engine}/notes.txt: {ENGINE_ENTRIES}; "
                    "unexpected entry: engines/patched/notes.txt"
                ),
                (
                    f"{engine}/scripts/a.py: {ENGINE_ENTRIES}; "
                    "unexpected entry: engines/patched/scripts/"
                ),
            ],
        )

    def test_non_module_directory_and_files_in_engine_modules_are_reported(self) -> None:
        engine = "examples/engines/simulation"
        findings = self.evaluate(
            *self.module(engine + "/modules/reaction_diffusion"),
            engine + "/modules/shared/util.h",
            engine + "/modules/shared/util.cpp",
            engine + "/modules/half/config.py",
            engine + "/modules/half/register_types.cpp",
            engine + "/modules/BUILD.bazel",
        )
        self.assertEqual(
            findings,
            [
                (
                    f"{engine}/modules/BUILD.bazel: engines/<name>/modules/ holds only "
                    "engine module directories; unexpected entry: "
                    "engines/simulation/modules/BUILD.bazel"
                ),
                (
                    f"{engine}/modules/half/config.py: engine module directory must "
                    f"own config.py and SCsub: {engine}/modules/half"
                ),
                (
                    f"{engine}/modules/shared/util.cpp: engine module directory must "
                    f"own config.py and SCsub: {engine}/modules/shared"
                ),
            ],
        )

    def test_engine_patches_holds_only_patch_files_and_a_build_file(self) -> None:
        engine = "e2e/rules_godot/projects/patched/engines/patched"
        findings = self.evaluate(
            engine + "/patches/BUILD.bazel",
            engine + "/patches/ok.patch",
            engine + "/patches/README.md",
            engine + "/patches/nested/deep.patch",
        )
        self.assertEqual(
            findings,
            [
                (
                    f"{engine}/patches/README.md: engines/<name>/patches/ holds only "
                    ".patch and .diff files and a BUILD file; unexpected entry: "
                    "engines/patched/patches/README.md"
                ),
                (
                    f"{engine}/patches/nested/deep.patch: engines/<name>/patches/ holds "
                    "only .patch and .diff files and a BUILD file; unexpected entry: "
                    "engines/patched/patches/nested/"
                ),
            ],
        )

    def test_nested_projects_own_their_files_and_other_areas_are_outside(self) -> None:
        addon = "examples/addons/widget"
        findings = self.evaluate(
            *self.project(addon + "/demo"),
            *self.project(addon + "/tests"),
            *self.module(addon + "/tests/modules/stray", "config.py", "SCsub"),
            "third_party/godot_simulator.patch",
            "e2e/rules_godot/unit/engine/fix.patch",
            *self.module("godot/private/probe", "config.py", "SCsub"),
            *self.project("e2e/rules_godot/projects/mobile/android"),
            "e2e/rules_godot/projects/mobile/BUILD.bazel",
            "e2e/rules_godot/projects/mobile/shared.patch",
            "e2e/rules_godot/projects/mobile/android/patches/stray.patch",
        )
        self.assertEqual(
            findings,
            [
                (
                    "e2e/rules_godot/projects/mobile/android/patches/stray.patch: engine "
                    "patch must live under engines/<name>/patches/, not in a Godot project"
                ),
                (
                    f"{addon}/tests/modules/stray/config.py: engine module must live under "
                    f"engines/<name>/modules/: {addon}/tests/modules/stray"
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
