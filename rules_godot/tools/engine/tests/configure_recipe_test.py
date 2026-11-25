import argparse
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tools.engine.configure import (
    check_options,
    customizations,
    inputs_hash,
    requested_modules,
    require_consistent_profile,
    require_expected_version,
    require_host_platform,
    require_one_text_server,
    source_version,
    version_name,
)


class ConfigureRecipeTest(unittest.TestCase):
    def test_recipes_without_a_module_list_take_the_default_of_their_start(
        self,
    ) -> None:
        self.assertEqual(requested_modules("", False), ["gdscript", "text_server_fb"])
        # Godot's defaults already hold GDScript and text_server_adv.
        self.assertEqual(requested_modules("", True), [])
        self.assertEqual(requested_modules("gdscript,,svg", True), ["gdscript", "svg"])

    def test_an_engine_with_both_text_servers_fails(self) -> None:
        require_one_text_server(["gdscript", "text_server_adv", "freetype"])
        require_one_text_server(["gdscript"])
        with self.assertRaisesRegex(
            ValueError, "one text server.*text_server_adv and text_server_fb"
        ):
            require_one_text_server(["text_server_fb", "gdscript", "text_server_adv"])

    def test_a_build_profile_must_agree_with_the_recipes_options(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "size.gdbuild"
            profile.write_text(
                json.dumps(
                    {
                        "type": "build_profile",
                        "disabled_classes": ["Node3D"],
                        "disabled_build_options": {"disable_3d": True, "vulkan": False},
                    }
                )
            )
            require_consistent_profile(profile, ["disable_3d=yes", "opengl3=yes"])
            require_consistent_profile(profile, [])
            with self.assertRaisesRegex(
                ValueError, r"contradicts.*vulkan=no \(build_options: yes\)"
            ):
                require_consistent_profile(profile, ["vulkan=yes"])
            profile.write_text("[]")
            with self.assertRaisesRegex(TypeError, "JSON object"):
                require_consistent_profile(profile, [])
            profile.write_text("{")
            with self.assertRaisesRegex(ValueError, "not readable JSON"):
                require_consistent_profile(profile, [])

    def test_source_archive_version_is_checked_instead_of_trusting_a_label(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for version in [(4, 7, 2), (4, 8, 0)]:
                (root / "version.py").write_text(
                    "major={}\nminor={}\npatch={}\n".format(*version)
                )
                self.assertEqual(source_version(root), ".".join(map(str, version)))
            for version in [(4, 5, 1), (4, 7, 1), (5, 0, 0)]:
                (root / "version.py").write_text(
                    "major={}\nminor={}\npatch={}\n".format(*version)
                )
                with self.assertRaisesRegex(ValueError, "4.7.2 or newer Godot 4 sources"):
                    source_version(root)

    def test_source_prereleases_preserve_their_status_and_respect_the_floor(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "version.py").write_text('major=4\nminor=8\npatch=0\nstatus="beta"\n')
            self.assertEqual(source_version(root), "4.8.0-beta")
            (root / "version.py").write_text('major=4\nminor=7\npatch=2\nstatus="rc1"\n')
            with self.assertRaisesRegex(ValueError, "4.7.2 or newer"):
                source_version(root)

    def test_inputs_hash_covers_declared_inputs_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            patch = root / "fix.patch"
            patch.write_text("one")
            modules = root / "_custom_modules"
            (modules / "probe").mkdir(parents=True)
            (modules / "probe/config.py").write_text("x = 1")
            configuration: dict[str, Any] = {
                "platform": "android",
                "build_target": "template_release",
                "modules": ["gdscript"],
                "default_modules": False,
                "options": ["a=1", "b=2"],
            }

            def hash_of(**changes: object) -> str:
                values: dict[str, Any] = (
                    {
                        "source_sha256": "1" * 64,
                        "patch": [patch],
                        "patch_strip": 1,
                        "build_profile_digest": "",
                        "custom_modules_root": modules,
                    }
                    | configuration
                    | changes
                )
                return inputs_hash(argparse.Namespace(**values))

            first = hash_of()
            self.assertRegex(first, "^[0-9a-f]{40}$")
            self.assertEqual(hash_of(), first)
            self.assertEqual(hash_of(options=["b=2", "a=1"]), first)
            for changes in [
                {"source_sha256": "2" * 64},
                {"patch_strip": 2},
                {"patch": []},
                {"custom_modules_root": None},
                {"options": ["a=1"]},
                {"modules": ["gdscript", "freetype"]},
                {"default_modules": True},
                {"build_target": "editor"},
                {"platform": "ios"},
                {"build_profile_digest": "sha256:1"},
            ]:
                with self.subTest(changes=changes):
                    self.assertNotEqual(hash_of(**changes), first)
            patch.write_text("two")
            self.assertNotEqual(hash_of(), first)
            patch.write_text("one")
            (modules / "probe/register_types.cpp").write_text("")
            self.assertNotEqual(hash_of(), first)

    def test_version_name_follows_the_android_library_manifest(self) -> None:
        info = {
            "major": 4,
            "minor": 8,
            "patch": 0,
            "status": "beta",
            "module_config": "",
            "build": "custom",
        }
        self.assertEqual(version_name(info), "4.8.0.beta")

    def test_symbol_options_bazel_does_not_replay_are_rejected(self) -> None:
        check_options(["vulkan=no", "dev_build=yes"])
        for option in ["debug_symbols=yes", "optimize=speed", "lto=thin"]:
            with (
                self.subTest(option=option),
                self.assertRaisesRegex(ValueError, "follows the build's settings"),
            ):
                check_options([option])
        for option in [
            "separate_debug_symbols=yes",
            "target=editor",
            "module_svg_enabled=no",
            # The recipe's environment attribute owns the iOS SDK axis.
            "simulator=yes",
            "ios_simulator=yes",
            "profile=/tmp/custom.py",
            "build_profile=/tmp/profile.gdbuild",
        ]:
            with (
                self.subTest(option=option),
                self.assertRaisesRegex(ValueError, "controlled by rules_godot"),
            ):
                check_options([option])

    def test_descriptor_version_must_match_the_extracted_source(self) -> None:
        require_expected_version("4.8.0-beta1", "4.8.0-beta1")
        require_expected_version("4.7.2", "")
        with self.assertRaisesRegex(
            ValueError, "declares Godot 4.7.2.*version.py is 4.8.0"
        ):
            require_expected_version("4.8.0", "4.7.2")

    def test_host_platform_follows_the_platforms_own_detection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for platform, accepted in [("macos", True), ("linuxbsd", False)]:
                (root / "platform" / platform).mkdir(parents=True)
                (root / "platform" / platform / "detect.py").write_text(
                    f"def can_build():\n    return {accepted}\n"
                )
            require_host_platform(root, "macos")
            with self.assertRaisesRegex(
                ValueError, r"platform/linuxbsd/detect\.py rejects this host"
            ):
                require_host_platform(root, "linuxbsd")

    def test_customizations_name_the_requested_inputs(self) -> None:
        args = argparse.Namespace(
            patch=[Path("/external/repo/engine-name.patch")],
            modules=["gdscript", "bazel_probe"],
            custom_module_names=["bazel_probe"],
            options=["vulkan=no", "disable_3d=yes"],
            default_modules=False,
            build_profile_digest="",
            renderers=[],
        )
        self.assertEqual(
            customizations(args),
            {
                "patches": ["engine-name.patch"],
                "modules": ["gdscript", "bazel_probe"],
                "custom_modules": ["bazel_probe"],
                "options": ["disable_3d=yes", "vulkan=no"],
            },
        )
        args.default_modules = True
        self.assertEqual(customizations(args)["default_modules"], ["yes"])


if __name__ == "__main__":
    unittest.main()
