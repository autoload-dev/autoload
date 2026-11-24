"""Engine modules and patches of a project sit under its engine/ directory."""

import unittest

from tools.conventions.rules.rg014 import EngineLayout
from tools.conventions.test_support import RepositoryTest

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

    def test_compliant_project_with_modules_and_patches_has_no_findings(self) -> None:
        root = "e2e/rules_godot/projects/patched"
        self.assertEqual(
            [],
            self.evaluate(
                *self.project(root),
                *self.module(root + "/engine/modules/bazel_probe"),
                *self.module(root + "/engine/modules/other", "config.py", "SCsub"),
                root + "/engine/modules/bazel_probe/BUILD.bazel",
                root + "/engine/patches/BUILD.bazel",
                root + "/engine/patches/engine-name.patch",
                root + "/engine/patches/renderer.diff",
            ),
        )

    def test_project_without_engine_directory_has_no_findings(self) -> None:
        self.assertEqual([], self.evaluate(*self.project("examples/projects/game")))

    def test_module_outside_engine_modules_is_reported_once_at_its_config(self) -> None:
        root = "examples/projects/game"
        findings = self.evaluate(
            *self.project(root),
            *self.module(root + "/modules/reaction_diffusion"),
            *self.module(root + "/main/native", "config.py", "register_types.cpp"),
            *self.module(root + "/engine/modules/ok", "config.py", "SCsub"),
        )
        self.assertEqual(
            findings,
            [
                (
                    f"{root}/main/native/config.py: engine module must live under "
                    f"engine/modules/ of its project: {root}/main/native"
                ),
                (
                    f"{root}/modules/reaction_diffusion/config.py: engine module must live "
                    f"under engine/modules/ of its project: {root}/modules/reaction_diffusion"
                ),
            ],
        )

    def test_config_without_scsub_or_register_types_is_not_a_module(self) -> None:
        root = "examples/projects/game"
        self.assertEqual(
            [],
            self.evaluate(
                *self.project(root),
                root + "/tools/config.py",
                root + "/tools/SCsub.txt",
                root + "/main/native/register_types.cc",
            ),
        )

    def test_patch_outside_engine_patches_is_reported(self) -> None:
        root = "e2e/rules_godot/projects/patched"
        findings = self.evaluate(
            *self.project(root),
            root + "/patches/engine-name.patch",
            root + "/main/fix.diff",
            root + "/engine/patches/ok.patch",
        )
        self.assertEqual(
            findings,
            [
                (
                    f"{root}/main/fix.diff: engine patch must live under engine/patches/ "
                    "of its project"
                ),
                (
                    f"{root}/patches/engine-name.patch: engine patch must live under "
                    "engine/patches/ of its project"
                ),
            ],
        )

    def test_stray_entries_in_engine_are_reported_once_per_entry(self) -> None:
        root = "e2e/rules_godot/projects/patched"
        findings = self.evaluate(
            *self.project(root),
            root + "/engine/BUILD.bazel",
            root + "/engine/notes.md",
            root + "/engine/scripts/a.py",
            root + "/engine/scripts/b.py",
            root + "/engine/patches/ok.patch",
        )
        self.assertEqual(
            findings,
            [
                (
                    f"{root}/engine/BUILD.bazel: engine/ holds only modules/ and patches/; "
                    "unexpected entry: engine/BUILD.bazel"
                ),
                (
                    f"{root}/engine/notes.md: engine/ holds only modules/ and patches/; "
                    "unexpected entry: engine/notes.md"
                ),
                (
                    f"{root}/engine/scripts/a.py: engine/ holds only modules/ and patches/; "
                    "unexpected entry: engine/scripts/"
                ),
            ],
        )

    def test_non_module_directory_and_files_in_engine_modules_are_reported(self) -> None:
        root = "examples/projects/petri"
        findings = self.evaluate(
            *self.project(root),
            *self.module(root + "/engine/modules/reaction_diffusion"),
            root + "/engine/modules/shared/util.h",
            root + "/engine/modules/shared/util.cpp",
            root + "/engine/modules/half/config.py",
            root + "/engine/modules/half/register_types.cpp",
            root + "/engine/modules/BUILD.bazel",
        )
        self.assertEqual(
            findings,
            [
                (
                    f"{root}/engine/modules/BUILD.bazel: engine/modules/ holds only engine "
                    "module directories; unexpected entry: engine/modules/BUILD.bazel"
                ),
                (
                    f"{root}/engine/modules/half/config.py: engine module directory must "
                    f"own config.py and SCsub: {root}/engine/modules/half"
                ),
                (
                    f"{root}/engine/modules/shared/util.cpp: engine module directory must "
                    f"own config.py and SCsub: {root}/engine/modules/shared"
                ),
            ],
        )

    def test_engine_patches_holds_only_patch_files_and_a_build_file(self) -> None:
        root = "e2e/rules_godot/projects/patched"
        findings = self.evaluate(
            *self.project(root),
            root + "/engine/patches/BUILD.bazel",
            root + "/engine/patches/ok.patch",
            root + "/engine/patches/README.md",
            root + "/engine/patches/nested/deep.patch",
        )
        self.assertEqual(
            findings,
            [
                (
                    f"{root}/engine/patches/README.md: engine/patches/ holds only .patch "
                    "and .diff files and a BUILD file; unexpected entry: "
                    "engine/patches/README.md"
                ),
                (
                    f"{root}/engine/patches/nested/deep.patch: engine/patches/ holds only "
                    ".patch and .diff files and a BUILD file; unexpected entry: "
                    "engine/patches/nested/"
                ),
            ],
        )

    def test_nested_projects_own_their_files_and_other_areas_are_outside(self) -> None:
        addon = "examples/addons/widget"
        findings = self.evaluate(
            *self.project(addon + "/demo"),
            *self.project(addon + "/tests"),
            *self.module(addon + "/demo/engine/modules/ok", "config.py", "SCsub"),
            *self.module(addon + "/tests/modules/stray", "config.py", "SCsub"),
            *self.module(addon + "/native", "config.py", "SCsub"),
            "examples/deps/godot_simulator.patch",
            "e2e/rules_godot/unit/engine/fix.patch",
            *self.module("godot/private/probe", "config.py", "SCsub"),
            *self.project("e2e/rules_godot/projects/mobile/android"),
            *self.project("e2e/rules_godot/projects/mobile/ios"),
            "e2e/rules_godot/projects/mobile/BUILD.bazel",
            "e2e/rules_godot/projects/mobile/shared.patch",
            "e2e/rules_godot/projects/mobile/android/engine/stray.txt",
        )
        self.assertEqual(
            findings,
            [
                (
                    "e2e/rules_godot/projects/mobile/android/engine/stray.txt: engine/ holds only "
                    "modules/ and patches/; unexpected entry: engine/stray.txt"
                ),
                (
                    f"{addon}/tests/modules/stray/config.py: engine module must live under "
                    f"engine/modules/ of its project: {addon}/tests/modules/stray"
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
