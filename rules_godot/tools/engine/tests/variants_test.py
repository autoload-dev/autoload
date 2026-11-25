import unittest

from tools.engine.build_file import Plus, Ref, Rule, Select, rule_text
from tools.engine.variants import merge, presence_scopes, unpinned_variants


def _library(name: str, **attrs: object) -> Rule:
    return Rule("cc_library", name, dict(attrs))


def _texts(rules: list[Rule]) -> list[str]:
    return [rule_text(rule) for rule in rules]


class MergeTest(unittest.TestCase):
    def test_a_target_the_variants_declare_alike_is_declared_once(self) -> None:
        rule = _library("a", srcs=["a.cpp"], copts=Ref("_COPTS_0"))
        self.assertEqual(merge([rule], {":_variant_0": [rule]}), [rule])

    def test_a_differing_attribute_selects_on_the_variant(self) -> None:
        merged = merge(
            [_library("a", srcs=["a.cpp"], deps=[":b"])],
            {":_variant_0": [_library("a", srcs=["a.cpp"], deps=[":c"])]},
        )
        self.assertEqual(
            _texts(merged),
            [
                "cc_library(name = 'a', srcs = ['a.cpp'], deps = select({"
                + "':_variant_0': [':c'], '//conditions:default': [':b']}))"
            ],
        )

    def test_a_rule_only_a_variant_declares_keeps_its_values(self) -> None:
        only = _library("b", copts=Plus((Ref("_COPTS_1"), ["-x"])))
        merged = merge([_library("a")], {":_variant_0": [_library("a"), only]})
        self.assertEqual(merged, [_library("a"), only])

    def test_an_attribute_one_variant_leaves_unset_defaults_to_empty(self) -> None:
        merged = merge(
            [_library("a", local_defines=["X"])], {":_variant_0": [_library("a")]}
        )
        self.assertEqual(
            merged[0].attrs["local_defines"],
            Select(((":_variant_0", []), ("//conditions:default", ["X"]))),
        )

    def test_attributes_bazel_cannot_select_must_agree(self) -> None:
        def generator(outs: list[str]) -> Rule:
            return Rule(
                "godot_source_generator",
                "_generate__a.h",
                {"outs": outs},
                fixed=frozenset({"outs"}),
            )

        with self.assertRaisesRegex(ValueError, "_generate__a.h.*outs"):
            merge([generator(["a.h"])], {":_variant_0": [generator(["a.h", "b.h"])]})

    def test_several_variants_select_their_own_values(self) -> None:
        merged = merge(
            [_library("a", deps=[":b"])],
            {
                ":_variant_0": [_library("a", deps=[":b"])],
                ":_variant_1": [_library("a", deps=[":c"])],
            },
        )
        self.assertEqual(
            merged[0].attrs["deps"],
            Select(((":_variant_1", [":c"]), ("//conditions:default", [":b"]))),
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
        rules = unpinned_variants(
            [
                _library("engine_library", deps=[":x"]),
                Rule("godot_source_binary", "godot", {"deps": [":engine_library"]}),
            ],
            ["engine_library", "godot"],
            {":_variant_1": "no pin for runtime profile //:p.gdbuild"},
        )
        texts = _texts(rules)
        self.assertIn("cc_library(name = '_pinned_engine_library', deps = [':x'])", texts)
        self.assertIn(
            "godot_source_binary(name = '_pinned_godot', "
            + "deps = [':_pinned_engine_library'])",
            texts,
        )
        self.assertIn(
            "godot_unpinned_recipe(name = '_unpinned_1_godot', "
            + "message = 'no pin for runtime profile //:p.gdbuild')",
            texts,
        )
        self.assertIn(
            "alias(name = 'godot', actual = select({"
            + "':_variant_1': ':_unpinned_1_godot', "
            + "'//conditions:default': ':_pinned_godot'}))",
            texts,
        )


if __name__ == "__main__":
    unittest.main()
