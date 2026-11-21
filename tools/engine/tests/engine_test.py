import argparse
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from tools.engine.configure import (
    check_options,
    customizations,
    deployment_target,
    engine_link_options,
    generated_include_directories,
    include_closure,
    included_sources,
    inputs_hash,
    is_directory_action,
    merge_swift_module_options,
    normalize_command,
    normalize_value,
    object_groups,
    pin_digest,
    pinned_graph,
    platform_compile_options,
    prepare_custom_modules,
    render_unpinned,
    require_expected_version,
    require_host_platform,
    scalar_environment,
    source_build_facts,
    source_version,
    stand_in_host,
    swift_module_options,
    target_constraints,
    version_name,
    write_json,
)
from tools.engine.generator import File, run, safe_relative
from tools.engine.module_graph import module_closure, module_dependencies
from tools.engine.pin import copy_tree, extract, merge
from tools.engine.revision import revision


def recipe_args(
    platform: str,
    cpu: str,
    build_target: str = "template_release",
    environment: str = "",
) -> argparse.Namespace:
    """Return the arguments of a recipe, with the defaults of configure's command line."""
    return argparse.Namespace(
        platform=platform,
        cpu=cpu,
        build_target=build_target,
        version="4.7.2",
        options=[],
        environment=environment,
        platforms_repository="@platforms",
        apple_repository="@apple_support",
    )


class ModuleGraphTest(unittest.TestCase):
    def test_required_transitive_dependencies_and_optional_exclusion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, body in {
                "movie": 'env.module_add_dependencies("movie", ["vorbis"])',
                "vorbis": 'env.module_add_dependencies("vorbis", ["ogg"])',
                "ogg": "",
                "gltf": 'env.module_add_dependencies("gltf", ["movie"], optional=True)',
            }.items():
                config = root / "modules" / name / "config.py"
                config.parent.mkdir(parents=True)
                config.write_text(body)
            graph = module_dependencies(root)
            self.assertEqual(module_closure(["movie"], graph), ["movie", "ogg", "vorbis"])
            self.assertEqual(module_closure(["gltf"], graph), ["gltf"])

    def test_unknown_or_cyclic_dependencies_fail(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown Godot module"):
            module_closure(["typo"], {})
        with self.assertRaisesRegex(ValueError, "dependency cycle"):
            module_closure(["a"], {"a": ["b"], "b": ["a"]})

    def test_custom_modules_override_upstream_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream = root / "modules" / "same" / "config.py"
            custom = root / "custom" / "same" / "config.py"
            for config in [upstream, custom]:
                config.parent.mkdir(parents=True)
            upstream.write_text('env.module_add_dependencies("same", ["obsolete"])')
            custom.write_text("")
            self.assertEqual(module_dependencies(root, [root / "custom"]), {"same": []})

    def test_dynamic_module_dependencies_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "modules" / "dynamic" / "config.py"
            config.parent.mkdir(parents=True)
            config.write_text(
                'env.module_add_dependencies("dynamic", calculate_dependencies())'
            )
            with self.assertRaisesRegex(ValueError, "Unsupported dependency declaration"):
                module_dependencies(directory)


class GraphTranslationTest(unittest.TestCase):
    def test_beta_swift_module_keeps_the_platform_bridge_and_interop_header(
        self,
    ) -> None:
        options = swift_module_options(
            [
                "-wmo",
                "-warnings-as-errors",
                "-cxx-interoperability-mode=default",
                "-emit-object",
                "-emit-objc-header-path",
                "/source/platform/ios/godot_swift_module-Swift.gen.h",
                "-target",
                "arm64-apple-ios15.0-simulator",
                "-sdk",
                "/Applications/Xcode.app/SDK",
                "-import-objc-header",
                "/source/platform/ios/bridging_header_ios.h",
                "-swift-version",
                "6",
                "-parse-as-library",
                "-module-name",
                "godot_swift_module",
                "-I./",
                "-Onone",
                "-g",
            ],
            Path("/source"),
        )
        self.assertEqual(options["bridging_header"], "platform/ios/bridging_header_ios.h")
        self.assertEqual(
            options["generated_header"], "platform/ios/godot_swift_module-Swift.gen.h"
        )
        self.assertEqual(options["module_name"], "godot_swift_module")
        self.assertEqual(
            options["copts"],
            [
                "-warnings-as-errors",
                "-cxx-interoperability-mode=default",
                "-swift-version",
                "6",
                "-parse-as-library",
            ],
        )

    def test_unknown_swift_options_and_undeclared_header_paths_fail(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "Unsupported upstream Swift compiler option"
        ):
            swift_module_options(["-new-upstream-feature"], Path("/source"))
        with self.assertRaisesRegex(ValueError, "outside engine source"):
            swift_module_options(
                ["-import-objc-header", "/host/undeclared.h"], Path("/source")
            )

    def test_overlapping_swift_declarations_require_a_shared_bridge_superset(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "shared.h").write_text("")
            (root / "ios.h").write_text('#import "shared.h"\n')
            (root / "unrelated.h").write_text("")
            base = {
                "module_name": "godot_swift_module",
                "copts": ["-swift-version", "6"],
                "generated_header": None,
            }
            shared = dict(base, bridging_header="shared.h")
            ios = dict(base, bridging_header="ios.h")
            self.assertEqual(merge_swift_module_options(shared, ios, root), ios)
            self.assertEqual(merge_swift_module_options(ios, shared, root), ios)
            with self.assertRaisesRegex(ValueError, "no common declared superset"):
                merge_swift_module_options(
                    ios, dict(base, bridging_header="unrelated.h"), root
                )
            with self.assertRaisesRegex(
                ValueError, "Incompatible upstream Swift modules"
            ):
                merge_swift_module_options(
                    ios, dict(shared, module_name="different"), root
                )

    def test_merging_swift_declarations_preserves_required_generated_headers(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bridge.h").write_text("")
            base = {
                "module_name": "Godot",
                "copts": [],
                "bridging_header": "bridge.h",
                "generated_header": None,
            }
            emitted = dict(base, generated_header="Godot-Swift.h")
            self.assertEqual(merge_swift_module_options(base, emitted, root), emitted)
            self.assertEqual(merge_swift_module_options(emitted, base, root), emitted)
            with self.assertRaisesRegex(
                ValueError, "Incompatible upstream Swift generated header names"
            ):
                merge_swift_module_options(
                    emitted, dict(base, generated_header="Different-Swift.h"), root
                )

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

    def test_bazel_owns_dependency_files_and_their_target_names(self) -> None:
        flags, includes = normalize_command(
            [
                "clang++",
                "-MD",
                "-MMD",
                "-MP",
                "-MF",
                "/host/obj.d",
                "-MT",
                "old.o",
                "-MQquoted.o",
                "-MFother.d",
                "-std=c++17",
                "-c",
                "file.cpp",
            ],
            "file.cpp",
            Path("/source"),
        )
        self.assertEqual(flags, ["-std=c++17"])
        self.assertEqual(includes, [])

    def test_deployment_target_is_captured_from_scons_and_not_replayed(self) -> None:
        flags = ["-arch", "arm64", "-mmacosx-version-min=11.0", "-Wl,-dead_strip"]
        self.assertEqual(deployment_target(flags), "11.0")
        self.assertEqual(deployment_target(["-miphoneos-version-min=12.0"]), "12.0")
        self.assertEqual(deployment_target(["-mios-simulator-version-min=12.0"]), "12.0")
        self.assertEqual(deployment_target(["-O2"]), "")
        replayed, _ = normalize_command(["clang++", *flags], "", Path("/source"))
        self.assertEqual(replayed, ["-Wl,-dead_strip"])

    def test_generated_sibling_headers_resolve_from_separate_bazel_output_tree(
        self,
    ) -> None:
        self.assertEqual(
            generated_include_directories(
                [
                    "core/extension/gdextension_interface.cpp",
                    "unrelated/file.cpp",
                    "modules/register.gen.cpp",
                ],
                ["core/extension/gdextension_interface.gen.h"],
                {"modules/register.gen.cpp"},
            ),
            ["core/extension", "modules"],
        )

    def test_generated_headers_below_a_source_resolve_by_relative_path(self) -> None:
        # gdscript_editor.cpp includes "editor/script_templates/templates.gen.h".
        self.assertEqual(
            generated_include_directories(
                ["modules/gdscript/gdscript_editor.cpp", "modules/other/file.cpp"],
                ["modules/gdscript/editor/script_templates/templates.gen.h"],
                set(),
            ),
            ["modules/gdscript"],
        )

    def test_same_named_generated_headers_stay_with_their_sources(self) -> None:
        groups = object_groups(
            {
                ("cpp", ("-O2",), ("core",)): [
                    "platform/ios/export/export_plugin.cpp",
                    "platform/macos/export/export_plugin.cpp",
                    "core/object.cpp",
                ]
            },
            [
                "platform/ios/export/logo_svg.gen.h",
                "platform/macos/export/logo_svg.gen.h",
            ],
            set(),
        )
        self.assertEqual(
            groups,
            [
                ("cpp", ("-O2",), ("core",), ["core/object.cpp"]),
                (
                    "cpp",
                    ("-O2",),
                    ("core", "platform/ios/export"),
                    ["platform/ios/export/export_plugin.cpp"],
                ),
                (
                    "cpp",
                    ("-O2",),
                    ("core", "platform/macos/export"),
                    ["platform/macos/export/export_plugin.cpp"],
                ),
            ],
        )

    def test_ios_class_name_does_not_collide_with_apple_toolchain_macro(self) -> None:
        upstream = ["-DIOS_ENABLED"]
        self.assertEqual(
            platform_compile_options("ios", upstream)[-2:], [*upstream, "-UOS_IOS"]
        )
        self.assertNotIn("-UOS_IOS", platform_compile_options("macos", upstream))

    def test_toolchain_only_warnings_are_disabled_before_upstream_flags(self) -> None:
        upstream = ["-Wall", "-Wthread-safety", "-w"]
        for platform, disabled in [
            (
                "android",
                ["-Wno-variadic-macro-arguments-omitted", "-Wno-c++20-designator"],
            ),
            (
                "macos",
                [
                    "-Wno-thread-safety",
                    "-Wno-shorten-64-to-32",
                    "-Wno-undeclared-selector",
                ],
            ),
        ]:
            with self.subTest(platform=platform):
                # Later flags win, so an upstream or patched -W flag stays enabled.
                self.assertEqual(
                    platform_compile_options(platform, upstream)[
                        : len(disabled) + len(upstream)
                    ],
                    [*disabled, *upstream],
                )
        self.assertEqual(
            platform_compile_options("ios", [])[:-1],
            platform_compile_options("macos", []),
        )
        self.assertEqual(platform_compile_options("linuxbsd", upstream), upstream)

    def test_bazel_flags_decide_optimization_debug_information_and_stripping(
        self,
    ) -> None:
        upstream = ["-O3", "-Os", "-Og", "-g2", "-gdwarf-4", "-ffast-math", "-DNDEBUG"]
        self.assertEqual(
            platform_compile_options("linuxbsd", upstream), ["-ffast-math", "-DNDEBUG"]
        )
        apple = ["-Wl,-S", "-Wl,-x", "-Wl,-dead_strip", "-ObjC", "-framework", "Metal"]
        self.assertEqual(
            engine_link_options("macos", [*apple, "-O2"]),
            ["-Wl,-dead_strip", "-ObjC", "-framework", "Metal"],
        )
        self.assertEqual(engine_link_options("android", ["-s", "-llog"]), ["-llog"])
        # The iOS application still drops the engine objects it never reaches.
        self.assertEqual(engine_link_options("ios", ["-O2"]), ["-Wl,-dead_strip"])

    def test_debug_symbol_flags_keep_their_relative_paths(self) -> None:
        flags, _includes = normalize_command(
            [
                "clang++",
                "-gdwarf-4",
                "-g2",
                "-ffile-prefix-map=/source=.",
                "-c",
                "core/object.cpp",
            ],
            "core/object.cpp",
            Path("/source"),
        )
        self.assertEqual(flags, ["-gdwarf-4", "-g2"])

    def test_symbol_options_bazel_does_not_replay_are_rejected(self) -> None:
        check_options(["vulkan=no", "dev_build=yes"])
        for option in ["debug_symbols=yes", "optimize=speed"]:
            with (
                self.subTest(option=option),
                self.assertRaisesRegex(ValueError, "follows Bazel's flags"),
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

    def test_android_debug_info_names_no_sandbox_directory(self) -> None:
        # Bazel's flags decide whether there is debug information.
        self.assertEqual(
            platform_compile_options("android", ["-DNDEBUG"])[-1],
            "-fdebug-compilation-dir=.",
        )
        self.assertNotIn(
            "-fdebug-compilation-dir=.", platform_compile_options("ios", ["-DNDEBUG"])
        )

    def test_apple_sdk_includes_come_from_cc_toolchain(self) -> None:
        flags, includes = normalize_command(
            [
                "clang++",
                "-I/SDK/usr/include",
                "-I/SDK/System/Library/Frameworks/OpenGLES.framework/Headers",
                "-Iplatform/ios",
                "-c",
                "file.mm",
            ],
            "file.mm",
            Path("/source"),
            ["/SDK"],
        )
        self.assertEqual(
            flags,
            [
                "-I__BAZEL_XCODE_SDKROOT__/usr/include",
                "-I__BAZEL_XCODE_SDKROOT__/System/Library/Frameworks/OpenGLES.framework/Headers",
            ],
        )
        self.assertEqual(includes, ["platform/ios"])
        with self.assertRaisesRegex(ValueError, "outside engine source"):
            normalize_command(
                ["clang++", "-I/undeclared/include", "file.mm"],
                "file.mm",
                Path("/source"),
                ["/SDK"],
            )

    def test_source_producer_records_template_and_sdk_facts(self) -> None:
        beta = recipe_args("ios", "arm64", "template_debug", "simulator")
        beta.version = "4.8.0-beta1"
        self.assertEqual(
            {
                "canonical_version": "4.8.0-beta1",
                "platform": "ios",
                "cpu": "arm64",
                "environment": "simulator",
                "role": "runtime",
                "variant": "debug",
            },
            source_build_facts(beta),
        )
        facts = source_build_facts(recipe_args("linuxbsd", "x86_64", "template_release"))
        self.assertEqual("linux", facts["platform"])
        self.assertEqual("release", facts["variant"])
        self.assertEqual("", facts["environment"])
        with self.assertRaisesRegex(ValueError, "template"):
            source_build_facts(recipe_args("ios", "arm64", "guessed_release"))

    def test_engine_targets_are_fixed_to_configured_platform_and_cpu(
        self,
    ) -> None:
        android = recipe_args("android", "arm64")
        android.platforms_repository = "@@platforms"
        android.apple_repository = "@@apple_support+"
        self.assertEqual(
            target_constraints(android),
            ["@@platforms//os:android", "@@platforms//cpu:aarch64"],
        )
        simulator = recipe_args("ios", "arm64", environment="simulator")
        self.assertEqual(
            target_constraints(simulator)[-1], "@apple_support//constraints:simulator"
        )
        self.assertEqual(
            target_constraints(recipe_args("ios", "arm64", environment="device"))[-1],
            "@apple_support//constraints:device",
        )
        with self.assertRaisesRegex(ValueError, "constraint mapping"):
            target_constraints(recipe_args("android", "unknown"))

    def test_scons_callable_actions_need_no_function_name(self) -> None:
        # SCons' Android Copy/Move actions use ActionCaller objects rather than
        # Python functions. They must reach platform staging classification.
        class ActionCaller:
            def __call__(self) -> None:
                pass

        self.assertFalse(
            is_directory_action([SimpleNamespace(execfunction=ActionCaller())])
        )

    def test_generator_environment_excludes_unused_build_options(self) -> None:
        env = {"used": True, "unrelated_module_enabled": True}
        self.assertEqual(
            scalar_environment(env, 'def build(env):\n    return env["used"]'),
            {"used": True},
        )

    def test_generator_environment_follows_helpers_without_capturing_unrelated_options(
        self,
    ) -> None:
        class Env(dict):
            dev_build = False

        def compress(buffer: bytes, env: Env) -> bytes | None:
            return buffer if env["production"] or env.dev_build else None

        env = Env(production=True, unrelated_module_enabled=True)
        self.assertEqual(
            scalar_environment(
                env,
                'def build(env):\n    return compress(b"", env)',
                {"compress": compress},
            ),
            {"production": True, "dev_build": False},
        )

    def test_unresolved_environment_forwarding_fails_instead_of_omitting_inputs(
        self,
    ) -> None:
        def helper(env: dict[str, bool]) -> bool:
            return env.get("production", False)

        with self.assertRaisesRegex(
            ValueError, "Unsupported generator helper receiving env: callback"
        ):
            scalar_environment(
                {"production": True},
                "def build(env):\n    callback = helper\n    return callback(env)",
                {"helper": helper},
            )
        with self.assertRaisesRegex(ValueError, "environment alias or escape"):
            scalar_environment(
                {"production": True},
                "def build(env):\n    settings = env\n    return helper(settings)",
                {"helper": helper},
            )
        with self.assertRaisesRegex(
            ValueError, "Unsupported generator helper receiving env: helper"
        ):
            scalar_environment(
                {"production": True},
                "def build(env):\n    helper = replacement\n    return helper(env)",
                {"helper": helper},
            )
        with self.assertRaisesRegex(
            ValueError, "Unsupported generator helper receiving env: helper"
        ):
            scalar_environment(
                {"production": True},
                "def build(env):\n    from local_helpers import helper\n    return helper(env)",
                {"helper": helper},
            )

        def renamed(settings: dict[str, bool]) -> bool:
            return settings.get("production", False)

        with self.assertRaisesRegex(ValueError, "parameter named env"):
            scalar_environment(
                {"production": True},
                "def build(env):\n    return renamed(env)",
                {"renamed": renamed},
            )

        def keywords(**settings: dict[str, bool]) -> bool:
            return settings.get("env", {}).get("production", False)

        with self.assertRaisesRegex(ValueError, "parameter named env"):
            scalar_environment(
                {"production": True},
                "def build(env):\n    return keywords(env=env)",
                {"keywords": keywords},
            )
        with self.assertRaisesRegex(ValueError, "environment method: env.copy"):
            scalar_environment(
                {"production": True},
                "def build(env):\n    settings = env.copy()\n    return settings.get('production', False)",
                {},
            )

    def test_missing_environment_keys_preserve_get_defaults(self) -> None:
        self.assertEqual(
            scalar_environment(
                {}, 'def build(env):\n    return env.get("optional", True)'
            ),
            {},
        )

    def test_module_value_paths_are_repository_relative(self) -> None:
        root = Path("/engine/source")
        self.assertEqual(
            normalize_value({"custom": "/engine/source/_custom_modules/demo"}, root),
            {"custom": "_custom_modules/demo"},
        )

    def test_cc_toolchain_owns_compiler_cpu_and_sdk(self) -> None:
        flags, includes = normalize_command(
            [
                "host-clang++",
                "-o",
                "out.o",
                "-c",
                "-arch",
                "arm64",
                "-isysroot",
                "/host/SDK",
                "-std=gnu++17",
                "-Icore",
                "-DMODULE=yes",
                "core/file.cpp",
            ],
            "core/file.cpp",
            Path("/source"),
        )
        self.assertEqual(flags, ["-std=gnu++17", "-DMODULE=yes"])
        self.assertEqual(includes, ["core"])

    def test_shader_dependencies_follow_relative_and_root_includes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "shaders").mkdir()
            (root / "thirdparty").mkdir()
            (root / "shaders/main.glsl").write_text(
                '#include "common.inc"\n#include "thirdparty/shared.h"'
            )
            (root / "shaders/common.inc").write_text("")
            (root / "thirdparty/shared.h").write_text("")
            self.assertEqual(
                include_closure(root, ["shaders/main.glsl"]),
                {"shaders/main.glsl", "shaders/common.inc", "thirdparty/shared.h"},
            )


class IncludedSourcesTest(unittest.TestCase):
    def test_sources_that_other_sources_include_become_textual_headers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kernels = root / "thirdparty/embree/kernels/bvh"
            kernels.mkdir(parents=True)
            (kernels / "hybrid4.cpp").write_text('#include "bvh_intersector_hybrid.cpp"\n')
            (kernels / "bvh_intersector_hybrid.cpp").write_text(
                '#include "../common/shared.cpp"\n#include "bvh.h"\n'
            )
            (root / "thirdparty/embree/kernels/common").mkdir()
            (root / "thirdparty/embree/kernels/common/shared.cpp").write_text("")
            (root / "core.cpp").write_text('#include "missing.cpp"\n')
            self.assertEqual(
                included_sources(
                    root, ["thirdparty/embree/kernels/bvh/hybrid4.cpp", "core.cpp"]
                ),
                [
                    "thirdparty/embree/kernels/bvh/bvh_intersector_hybrid.cpp",
                    "thirdparty/embree/kernels/common/shared.cpp",
                ],
            )


class PinTest(unittest.TestCase):
    def test_an_unpinned_recipe_fails_each_engine_target_with_the_reason(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for platform, targets in [
                ("linuxbsd", ["engine_library", "godot"]),
                ("android", ["engine_library", "libgodot_android.so", "godot"]),
                ("ios", ["engine_library"]),
            ]:
                args = argparse.Namespace(
                    platform=platform,
                    pin_bzl="@@autoload_rules_godot+//godot/engine/private:pin.bzl",
                    unpinned_message="recipe: the lock file {reason} it; run @godot//:pin",
                )
                render_unpinned(args, "stale", root)
                build = (root / "BUILD.bazel").read_text()
                self.assertIn(
                    'load("@@autoload_rules_godot+//godot/engine/private:pin.bzl"', build
                )
                for target in targets:
                    self.assertIn(f"godot_unpinned_recipe(name = {target!r}", build)
                self.assertEqual(build.count("godot_unpinned_recipe(name"), len(targets))
                self.assertIn("the lock file pins other sources, patches", build)
            render_unpinned(args, "missing", root)
            self.assertIn(
                "the lock file has no pin for it", (root / "BUILD.bazel").read_text()
            )

    def test_configuration_reads_stand_ins_for_the_host_probes(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ):
            root = Path(directory)
            (root / "tools").mkdir()
            stand_in_host(root, "linuxbsd", root / "tools")
            # Godot's detect.py finds the stand-ins on PATH: pkg-config knows no package.
            for command, code in [
                (["pkg-config", "--version"], 0),
                (["pkg-config", "--exists", "x11"], 1),
                (["wayland-scanner", "-v"], 1),
            ]:
                result = subprocess.run(command, capture_output=True, check=False)
                self.assertEqual(result.returncode, code, command)
            self.assertTrue(os.environ["PATH"].startswith(str(root / "tools")))
            (root / "platform/android").mkdir(parents=True)
            (root / "platform/android/detect.py").write_text(
                'def get_ndk_version():\n    return "29.0.1"\n'
            )
            stand_in_host(root, "android", root / "tools")
            self.assertEqual(os.environ["ANDROID_HOME"], str(root / "tools/android_sdk"))
            self.assertTrue((root / "tools/android_sdk/ndk/29.0.1").is_dir())

    def test_pin_actions_extract_the_archive_below_its_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "godot-4.7.2-stable/core").mkdir(parents=True)
            (root / "godot-4.7.2-stable/core/a.h").write_text("a")
            with tarfile.open(root / "source.tar.gz", "w:gz") as archive:
                archive.add(root / "godot-4.7.2-stable", arcname="godot-4.7.2-stable")
            extract(root / "source.tar.gz", "godot-4.7.2-stable", root / "out")
            self.assertEqual((root / "out/core/a.h").read_text(), "a")
            with zipfile.ZipFile(root / "source.zip", "w") as archive:
                archive.write(
                    root / "godot-4.7.2-stable/core/a.h", "godot-4.7.2-stable/core/a.h"
                )
            extract(root / "source.zip", "godot-4.7.2-stable", root / "zip")
            self.assertEqual((root / "zip/core/a.h").read_text(), "a")

    def test_digest_covers_the_recipe_and_the_capture_tools_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scons = root / "scons"
            (scons / "SCons").mkdir(parents=True)
            (scons / "SCons/__init__.py").write_text('__version__ = "4.10.1"')
            patch = root / "fix.patch"
            patch.write_text("one")
            module = root / "source/_custom_modules/probe"
            module.mkdir(parents=True)
            for name in ["config.py", "SCsub", "probe.cpp"]:
                (module / name).write_text(name)

            def digest(**changes: object) -> str:
                values: dict[str, Any] = {
                    "source_sha256": "1" * 64,
                    "patch": [patch],
                    "patch_strip": 1,
                    "custom_modules_root": module.parent,
                    "platform": "linuxbsd",
                    "cpu": "x86_64",
                    "build_target": "editor",
                    "modules": ["gdscript", "probe"],
                    "default_modules": False,
                    "options": ["vulkan=no"],
                    "build_name": "custom",
                } | changes
                return pin_digest(argparse.Namespace(**values), scons)

            first = digest()
            self.assertRegex(first, "^sha256:[0-9a-f]{64}$")
            self.assertEqual(digest(), first)
            for change in [
                {"source_sha256": "2" * 64},
                {"patch_strip": 2},
                {"cpu": "arm64"},
                {"build_target": "template_release"},
                {"modules": ["gdscript"]},
                {"default_modules": True},
                {"options": ["vulkan=yes"]},
                {"build_name": "fork"},
            ]:
                self.assertNotEqual(digest(**change), first, change)
            # Editing a module's code keeps the pin; its build scripts and file set do not.
            (module / "probe.cpp").write_text("edited")
            self.assertEqual(digest(), first)
            (module / "SCsub").write_text("edited")
            second = digest()
            self.assertNotEqual(second, first)
            (module / "extra.cpp").write_text("new")
            self.assertNotEqual(digest(), second)
            third = digest()
            patch.write_text("two")
            self.assertNotEqual(digest(), third)
            fourth = digest()
            (scons / "SCons/__init__.py").write_text('__version__ = "4.11.0"')
            self.assertNotEqual(digest(), fourth)

    def test_a_lock_entry_counts_only_for_its_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "engine.lock.json"
            self.assertEqual(
                pinned_graph(lock, "linux_x86_64_editor", "sha256:a"), ("missing", None)
            )
            lock.write_text("")
            self.assertEqual(
                pinned_graph(lock, "linux_x86_64_editor", "sha256:a"), ("missing", None)
            )
            graph = {"version": "4.7.2.stable", "generators": "sha256:g"}
            lock.write_text(
                json.dumps(
                    {
                        "generators": {"sha256:g": [{"spec": {}, "dependencies": []}]},
                        "recipes": {
                            "linux_x86_64_editor": {"digest": "sha256:a", "graph": graph}
                        },
                    }
                )
            )
            self.assertEqual(
                pinned_graph(lock, "linux_x86_64_editor", "sha256:a"),
                ("pinned", graph | {"generators": [{"spec": {}, "dependencies": []}]}),
            )
            self.assertEqual(
                pinned_graph(lock, "linux_x86_64_editor", "sha256:b"), ("stale", None)
            )
            self.assertEqual(
                pinned_graph(lock, "macos_arm64_editor", "sha256:a"), ("missing", None)
            )

    def test_custom_modules_are_copied_without_package_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = root / "workspace/modules/probe"
            (module / "__pycache__").mkdir(parents=True)
            for name in ["config.py", "SCsub", "BUILD.bazel", "__pycache__/config.pyc"]:
                (module / name).write_text(name)
            self.assertEqual(
                prepare_custom_modules(root / "source", [f"probe={module}"]), ["probe"]
            )
            self.assertEqual(
                sorted(
                    path.name
                    for path in (root / "source/_custom_modules/probe").iterdir()
                ),
                ["SCsub", "config.py"],
            )
            with self.assertRaisesRegex(ValueError, "Invalid custom module declaration"):
                prepare_custom_modules(root / "source", [f"1probe={module}"])

    def test_pin_actions_copy_their_declared_tree_and_merge_sorted_recipes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "repo/core").mkdir(parents=True)
            (root / "repo/core/a.h").write_text("a")
            copy_tree(root / "repo", [str(root / "repo/core/a.h")], root / "copy")
            self.assertEqual((root / "copy/core/a.h").read_text(), "a")
            keys = ["macos_arm64_editor", "linux_x86_64_editor"]
            for key in keys:
                # SCons Value mappings keep their order, which upstream builders depend on.
                spec = {"function": "f", "sources": [{"value": {"z": 1, "a": 2}}]}
                pin = {"digest": key, "graph": {"generators": [{"spec": spec}]}}
                (root / f"{key}.json").write_text(json.dumps(pin))
            merge(
                argparse.Namespace(
                    output=str(root / "engine.lock.json"),
                    recipe=[f"{key}={root / key}.json" for key in keys],
                )
            )
            text = (root / "engine.lock.json").read_text()
            lock = json.loads(text)
            self.assertLess(
                text.index('"linux_x86_64_editor"'), text.index('"macos_arm64_editor"')
            )
            self.assertEqual(
                lock["recipes"]["linux_x86_64_editor"]["digest"], "linux_x86_64_editor"
            )
            # Both recipes refer to one stored generator list.
            (reference,) = lock["generators"]
            for key in keys:
                self.assertEqual(lock["recipes"][key]["graph"]["generators"], reference)
                status, graph = pinned_graph(root / "engine.lock.json", key, key)
                self.assertEqual(status, "pinned")
                assert graph is not None
                (generator,) = graph["generators"]
                self.assertEqual(list(generator["spec"]), ["function", "sources"])
                self.assertEqual(
                    list(generator["spec"]["sources"][0]["value"]), ["z", "a"]
                )


class GeneratorTest(unittest.TestCase):
    def test_scons_file_node_name_matches_basename(self) -> None:
        node = File("servers/rendering/storage/make_ltc_lut.py")
        self.assertEqual(node.name, "make_ltc_lut.py")
        self.assertEqual(node.path, "servers/rendering/storage/make_ltc_lut.py")

    def test_scons_value_mapping_order_survives_manifest_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "generator.json"
            write_json(
                manifest,
                {"sources": [{"value": {"dependency": "first", "consumer": "second"}}]},
            )
            restored = json.loads(manifest.read_text())
            self.assertEqual(
                list(restored["sources"][0]["value"]), ["dependency", "consumer"]
            )

    def test_declared_file_and_value_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = root / "builder.py"
            code.write_text(
                'from pathlib import Path\ndef build(target, source, env):\n    Path(target[0]).write_text(Path(source[0]).read_text() + source[1].read()["suffix"])\n'
            )
            source = root / "input.txt"
            source.write_text("Godot")
            output = root / "output.h"
            spec = {
                "code_file": "builder.py",
                "function": "build",
                "targets": ["generated/result.h"],
                "sources": [{"path": "data.txt"}, {"value": {"suffix": " Bazel"}}],
            }
            run(
                spec,
                {"builder.py": str(code), "data.txt": str(source)},
                {"generated/result.h": str(output)},
            )
            self.assertEqual(output.read_text(), "Godot Bazel")

    def test_value_fields_come_from_declared_input_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = root / "builder.py"
            code.write_text(
                "from pathlib import Path\n"
                "def build(target, source, env):\n"
                "    value = source[0].read()\n"
                "    Path(target[0]).write_text(value['build'] + ' ' + value['git_hash'])\n"
            )
            build, hash_file = root / "build.txt", root / "hash.txt"
            build.write_text("custom-git")
            hash_file.write_text("abc1234")
            output = root / "version.h"
            spec = {
                "code_file": "builder.py",
                "function": "build",
                "targets": ["core/version.h"],
                "sources": [
                    {
                        "value": {"build": "custom", "git_hash": ""},
                        "files": {
                            "build": "_revision/build.txt",
                            "git_hash": "_revision/hash.txt",
                        },
                    }
                ],
            }
            run(
                spec,
                {
                    "builder.py": str(code),
                    "_revision/build.txt": str(build),
                    "_revision/hash.txt": str(hash_file),
                },
                {"core/version.h": str(output)},
            )
            self.assertEqual(output.read_text(), "custom-git abc1234")

    def test_stamped_builds_name_the_workspace_commit_and_its_time(self) -> None:
        commit = "0123456789abcdef0123456789abcdef01234567"
        status = f"BUILD_EMBED_LABEL \nSTABLE_GIT_COMMIT {commit}\n"
        self.assertEqual(revision(status, "inputs"), ("git", commit, "0"))
        self.assertEqual(
            revision(status + "STABLE_GIT_COMMIT_TIMESTAMP 1792922661\n", "inputs"),
            ("git", commit, "1792922661"),
        )
        # A commit time without a commit names no time stamp.
        self.assertEqual(
            revision("STABLE_GIT_COMMIT_TIMESTAMP 1792922661\n", "inputs"),
            ("bazel", "inputs", "0"),
        )
        with self.assertRaisesRegex(SystemExit, "hexadecimal commit hash"):
            revision("STABLE_GIT_COMMIT abc1234-dirty\n", "inputs")
        with self.assertRaisesRegex(SystemExit, "Unix time in seconds"):
            revision(status + "STABLE_GIT_COMMIT_TIMESTAMP 2026-10-25\n", "inputs")

    def test_missing_generator_output_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = root / "builder.py"
            code.write_text("def build(target, source, env):\n    return 0\n")
            spec = {
                "code_file": "builder.py",
                "function": "build",
                "targets": ["missing.h"],
                "sources": [],
            }
            with self.assertRaisesRegex(RuntimeError, "did not produce"):
                run(
                    spec,
                    {"builder.py": str(code)},
                    {"missing.h": str(root / "missing.h")},
                )

    def test_generator_paths_are_confined(self) -> None:
        for path in ("../escape", "/absolute/file", "dir/../../escape"):
            with self.assertRaises(ValueError):
                safe_relative(path)


if __name__ == "__main__":
    unittest.main()
