import argparse
import json
import tempfile
import unittest
from pathlib import Path

from tools.engine.generators import generator_attributes
from tools.engine.render import (
    Variant,
    engine_dependencies,
    header_rules,
    include_rules,
    object_groups,
    object_library_name,
    object_rules,
    render,
    source_build_facts,
    target_constraints,
)


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


class RenderTest(unittest.TestCase):
    def test_generated_sibling_headers_resolve_from_separate_bazel_output_tree(
        self,
    ) -> None:
        groups = object_groups(
            {
                ("cc", (), ()): [
                    "core/extension/gdextension_interface.cpp",
                    "unrelated/file.cpp",
                    "modules/register.gen.cpp",
                ]
            },
            ["core/extension/gdextension_interface.gen.h"],
            {"modules/register.gen.cpp"},
        )
        self.assertEqual(
            groups,
            [
                ("cc", (), (), ["unrelated/file.cpp"]),
                (
                    "cc",
                    (),
                    ("core/extension",),
                    ["core/extension/gdextension_interface.cpp"],
                ),
                ("cc", (), ("modules",), ["modules/register.gen.cpp"]),
            ],
        )

    def test_generated_headers_below_a_source_resolve_by_relative_path(self) -> None:
        # gdscript_editor.cpp includes "editor/script_templates/templates.gen.h".
        groups = object_groups(
            {
                ("cc", (), ()): [
                    "modules/gdscript/gdscript_editor.cpp",
                    "modules/other/file.cpp",
                ]
            },
            ["modules/gdscript/editor/script_templates/templates.gen.h"],
            set(),
        )
        self.assertEqual(
            groups,
            [
                ("cc", (), (), ["modules/other/file.cpp"]),
                (
                    "cc",
                    (),
                    ("modules/gdscript",),
                    ["modules/gdscript/gdscript_editor.cpp"],
                ),
            ],
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

    def test_object_libraries_are_named_after_their_source_without_slashes(
        self,
    ) -> None:
        # objc_library rejects names with a slash.
        self.assertEqual(
            object_library_name("platform/ios/os_ios.mm", 3, set()),
            "_objects__platform__ios__os_ios.mm",
        )
        # A source that two compile groups compile gets a library per group.
        self.assertEqual(
            object_library_name("core/a.cpp", 3, {"_objects__core__a.cpp"}),
            "_objects__core__a.cpp__3",
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

    def test_each_set_of_included_files_becomes_one_header_target(self) -> None:
        lines, targets = include_rules(
            {
                "main.cpp": {"a.h"},
                "a.h": {"b.h", "c.h"},
                "b.h": {"a.h"},
                "c.h": set(),
            }
        )
        self.assertEqual(
            lines,
            [
                "godot_source_headers(name = '_includes/c.h', hdrs = ['c.h'], deps = [])",
                (
                    "godot_source_headers(name = '_includes/a.h', hdrs = ['a.h', 'b.h'], "
                    "deps = [':_includes/c.h'])"
                ),
            ],
        )
        self.assertNotIn("main.cpp", targets)
        self.assertEqual(targets["b.h"], ":_includes/a.h")


if __name__ == "__main__":
    unittest.main()


class ClassProfileRenderTest(unittest.TestCase):
    def test_the_class_generator_reads_the_class_profile(self) -> None:
        spec = {
            "code_file": "core/core_builders.py",
            "function": "disabled_class_builder",
            "targets": ["core/disabled_classes.gen.h"],
            "sources": [{"value": []}],
        }

        def profile_args(recipe_profile: str) -> argparse.Namespace:
            return argparse.Namespace(
                recipe_profile=recipe_profile, runtime_profiles=[], engine=""
            )

        attributes = generator_attributes(
            "_generate_0001", spec, {}, profile_args("_build_profile.gdbuild")
        )
        self.assertIs(attributes["class_profile"], True)
        self.assertEqual(attributes["recipe_profile"], "_build_profile.gdbuild")
        self.assertNotIn(
            "recipe_profile",
            generator_attributes("_generate_0001", spec, {}, profile_args("")),
        )
        other = generator_attributes(
            "_generate_0002",
            spec | {"function": "make_authors_header"},
            {},
            profile_args("x"),
        )
        self.assertNotIn("class_profile", other)

    def test_objects_that_read_no_class_profile_share_one_configuration(self) -> None:
        deps, rules = engine_dependencies(
            [":a", ":register", ":b"], {":register"}, scoped=True
        )
        self.assertEqual(deps, [":register", ":_profile_independent_objects"])
        self.assertEqual(len(rules), 1)
        self.assertIn(
            "godot_profile_independent(name = '_profile_independent_objects'", rules[0]
        )
        self.assertIn("deps = [':a', ':b']", rules[0])
        # A fork whose class_db.h gives the profile to every source normalizes nothing.
        self.assertEqual(
            engine_dependencies([":a", ":b"], set(), scoped=False), ([":a", ":b"], [])
        )


class PathMappingTest(unittest.TestCase):
    def test_native_rules_support_path_mapping(self) -> None:
        graph = {"core/a.cpp": set(), "platform/ios/b.mm": set()}
        groups = [
            ("cc", ("-Wall",), (".",), ["core/a.cpp"]),
            ("objc", ("-Wall",), (".",), ["platform/ios/b.mm"]),
        ]
        lines, _, _ = object_rules(groups, graph, {}, set())
        libraries = [
            line for line in lines if line.startswith(("cc_library(", "objc_library("))
        ]
        self.assertEqual(len(libraries), 2)
        for library in libraries:
            self.assertIn("tags = ['supports-path-mapping']", library)

    def test_the_package_compiles_without_module_maps(self) -> None:
        args = argparse.Namespace(
            cc_repository="@rules_cc",
            swift_repository="@rules_swift",
            generator_bzl="@autoload_rules_godot//godot/engine/private:generator.bzl",
            build_name="custom",
            inputs_hash="0",
        )
        package = [
            line for line in header_rules(args, False) if line.startswith("package(")
        ]
        self.assertEqual(len(package), 1)
        self.assertIn('features = ["-module_maps", "-layering_check"]', package[0])


def _variant_args(**changes: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "platform": "macos",
        "cpu": "arm64",
        "environment": "",
        "build_target": "template_release",
        "version": "4.7.2",
        "modules": [],
        "options": [],
        "platforms_repository": "@platforms",
        "apple_repository": "@apple_support",
        "cc_repository": "@rules_cc",
        "swift_repository": "@rules_swift",
        "generator_bzl": "@rules_godot//godot/engine/private:generator.bzl",
        "pin_bzl": "@rules_godot//godot/engine/private:pin.bzl",
        "build_name": "custom",
        "inputs_hash": "base",
        "source_sha256": "",
        "customizations": {},
        "renderers": [],
        "engine_renderers": [],
        "recipe_profile": "",
        "runtime_profiles": ["@@//app:small.gdbuild", "@@//app:new.gdbuild"],
        "engine": "",
        "build_profile_label": "@rules_godot//godot/private:build_profile_label",
    }
    return argparse.Namespace(**(values | changes))


def _graph(groups: list[object]) -> dict[str, object]:
    return {
        "groups": groups,
        "generators": [],
        "swift_sources": [],
        "swift_options": None,
        "version": "4.7.2",
        "linkopts": [],
        "minimum_os": "",
        "modules": [],
    }


class RuntimeVariantRenderTest(unittest.TestCase):
    def test_variants_share_one_package_and_select_on_the_build_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "core").mkdir()
            for name in ["a.cpp", "b.cpp"]:
                (root / "core" / name).write_text("int x;\n")
            base = _graph([["cc", ["-DX"], ["."], ["core/a.cpp"]]])
            small = _graph([["cc", ["-DX", "-DY"], ["."], ["core/a.cpp", "core/b.cpp"]]])
            render(
                _variant_args(),
                base,
                root,
                [
                    Variant(
                        "@@//app:small.gdbuild", _variant_args(inputs_hash="v"), small
                    ),
                    Variant("@@//app:new.gdbuild", _variant_args(), None, "no pin"),
                ],
            )
            build = (root / "BUILD.bazel").read_text()
            self.assertIn(
                "config_setting(name = '_variant_0', visibility = ['//visibility:private'], "
                "flag_values = {'@rules_godot//godot/private:build_profile_label': "
                "'@@//app:small.gdbuild'})",
                build,
            )
            # Each object keeps one name; what differs selects on the variant.
            self.assertEqual(build.count("cc_library(name = '_objects__core__a.cpp'"), 1)
            self.assertIn("cc_library(name = '_objects__core__b.cpp'", build)
            self.assertIn("inputs_hash = select({':_variant_0': 'v'", build)
            # Only the small variant compiles b.cpp, so its analysis is a shard of its own.
            self.assertIn("name = '_macros__core'", build)
            self.assertRegex(build, r"name = '_macros__p\d__core'")
            # The variant without a pin fails with its message.
            self.assertIn(
                "alias(name = 'godot', actual = select({':_variant_1': ':_unpinned_1_godot'",
                build,
            )
            self.assertIn("godot_unpinned_recipe(name = '_unpinned_1_godot'", build)
            manifest = json.loads((root / "engine_manifest.json").read_text())
            self.assertEqual(
                manifest["runtime_variants"],
                {"@@//app:small.gdbuild": "configured", "@@//app:new.gdbuild": "no pin"},
            )
