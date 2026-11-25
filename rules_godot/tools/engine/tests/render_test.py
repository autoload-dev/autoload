import argparse
import unittest

from tools.engine.render import (
    include_rules,
    object_groups,
    object_library_name,
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
