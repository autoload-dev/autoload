import unittest

from tools.engine.variants import merge, presence_scopes, unpinned_variants


def _merged(base: list[str], variant: list[str]) -> list[str]:
    return merge(base, {":_variant_0": variant})


class MergeTest(unittest.TestCase):
    def test_a_target_the_variants_declare_alike_is_declared_once(self) -> None:
        rule = "cc_library(name = 'a', srcs = ['a.cpp'], copts = _COPTS_0)"
        merged = _merged(["_COPTS_0 = ['-O2']", rule], ["_COPTS_0 = ['-O2']", rule])
        self.assertEqual(merged, ["_COPTS_0 = ['-O2']", rule])

    def test_a_differing_attribute_selects_on_the_variant(self) -> None:
        merged = _merged(
            ["cc_library(name = 'a', srcs = ['a.cpp'], deps = [':b'])"],
            ["cc_library(name = 'a', srcs = ['a.cpp'], deps = [':c'])"],
        )
        self.assertEqual(
            merged,
            [
                (
                    "cc_library(name = 'a', srcs = ['a.cpp'], deps = select({"
                    "':_variant_0': [':c'], '//conditions:default': [':b']}))"
                )
            ],
        )

    def test_constants_merge_by_value_and_keep_their_references(self) -> None:
        merged = _merged(
            ["_COPTS_0 = ['-O2']", "cc_library(name = 'a', copts = _COPTS_0)"],
            [
                "_COPTS_0 = ['-Os']",
                "_COPTS_1 = ['-O2']",
                "cc_library(name = 'a', copts = _COPTS_1)",
                "cc_library(name = 'b', copts = _COPTS_0 + ['-x'])",
            ],
        )
        self.assertEqual(
            merged,
            [
                "_COPTS_0 = ['-O2']",
                "_V0_COPTS_0 = ['-Os']",
                # The variant's _COPTS_1 has the value of the base's _COPTS_0.
                "cc_library(name = 'a', copts = _COPTS_0)",
                "cc_library(name = 'b', copts = _V0_COPTS_0 + ['-x'])",
            ],
        )

    def test_constants_of_one_value_compare_alike(self) -> None:
        base = [
            "_COPTS_0 = ['-O2']",
            "_COPTS_1 = ['-O2']",
            "cc_library(name = 'a', copts = _COPTS_1)",
        ]
        merged = _merged(
            base, ["_COPTS_0 = ['-O2']", "cc_library(name = 'a', copts = _COPTS_0)"]
        )
        self.assertEqual(merged, base)

    def test_an_attribute_one_variant_leaves_unset_defaults_to_empty(self) -> None:
        merged = _merged(
            ["cc_library(name = 'a', local_defines = ['X'])"],
            ["cc_library(name = 'a')"],
        )
        self.assertEqual(
            merged,
            [
                (
                    "cc_library(name = 'a', local_defines = select({"
                    "':_variant_0': [], '//conditions:default': ['X']}))"
                )
            ],
        )

    def test_attributes_bazel_cannot_select_must_agree(self) -> None:
        with self.assertRaisesRegex(ValueError, "_generate__a.h.*outs"):
            _merged(
                ["godot_source_generator(name = '_generate__a.h', outs = ['a.h'])"],
                [
                    (
                        "godot_source_generator(name = '_generate__a.h', "
                        "outs = ['a.h', 'b.h'])"
                    )
                ],
            )

    def test_loads_and_package_statements_are_declared_once(self) -> None:
        load = 'load("@rules_cc//cc:cc_library.bzl", "cc_library")'
        swift = 'load("@rules_swift//swift:swift_library.bzl", "swift_library")'
        merged = _merged(["# Generated.", load], [load, swift])
        self.assertEqual(merged, ["# Generated.", load, swift])

    def test_several_variants_select_their_own_values(self) -> None:
        merged = merge(
            ["cc_library(name = 'a', deps = [':b'])"],
            {
                ":_variant_0": ["cc_library(name = 'a', deps = [':b'])"],
                ":_variant_1": ["cc_library(name = 'a', deps = [':c'])"],
            },
        )
        self.assertEqual(
            merged,
            [
                (
                    "cc_library(name = 'a', deps = select({"
                    "':_variant_1': [':c'], '//conditions:default': [':b']}))"
                )
            ],
        )


class AnalysisScopeTest(unittest.TestCase):
    def test_libraries_shard_with_those_every_same_variant_compiles(self) -> None:
        scopes = presence_scopes(
            {
                "": ["a", "b"],
                ":_variant_0": ["a", "c"],
                ":_variant_1": ["a", "c", "d"],
            }
        )
        self.assertEqual(scopes["a"], "")
        self.assertEqual(
            len({scopes[name] for name in "bcd"}), 3, "b, c and d compile in other sets"
        )
        self.assertNotIn("", {scopes[name] for name in "bcd"})


class UnpinnedVariantTest(unittest.TestCase):
    def test_an_unpinned_variant_routes_the_engine_targets_to_its_error(self) -> None:
        statements = unpinned_variants(
            [
                "cc_library(name = 'engine_library', deps = [':x'])",
                "godot_source_binary(name = 'godot', deps = [':engine_library'])",
            ],
            ["engine_library", "godot"],
            {":_variant_1": "no pin for runtime profile //:p.gdbuild"},
        )
        self.assertIn(
            "cc_library(name = '_pinned_engine_library', deps = [':x'])", statements
        )
        self.assertIn(
            "godot_source_binary(name = '_pinned_godot', "
            "deps = [':_pinned_engine_library'])",
            statements,
        )
        self.assertIn(
            "godot_unpinned_recipe(name = '_unpinned_1_godot', "
            "message = 'no pin for runtime profile //:p.gdbuild')",
            statements,
        )
        self.assertIn(
            "alias(name = 'godot', actual = select({"
            "':_variant_1': ':_unpinned_1_godot', "
            "'//conditions:default': ':_pinned_godot'}))",
            statements,
        )


if __name__ == "__main__":
    unittest.main()
