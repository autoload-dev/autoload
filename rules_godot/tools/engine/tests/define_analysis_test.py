import unittest

from tools.engine.build_file import Constants, Ref, Rule, rule_text
from tools.engine.define_analysis import Library, analysis_rules, is_definition
from tools.engine.render import Includes, object_rules


def _rules(rules: list[Rule], kind: str) -> dict[str, str]:
    return {rule.name: rule_text(rule) for rule in rules if rule.kind == kind}


class DefineAnalysisTest(unittest.TestCase):
    def test_only_macro_options_are_definitions(self) -> None:
        self.assertTrue(is_definition("-DXR_DISABLED"))
        self.assertTrue(is_definition('-DMBEDTLS_CONFIG_FILE=\\"x.h\\"'))
        self.assertTrue(is_definition("-UNDEBUG"))
        self.assertFalse(is_definition("-Wall"))
        self.assertFalse(is_definition("-fdebug-compilation-dir=."))

    def test_c_and_cpp_sources_compile_with_their_analysed_header(self) -> None:
        graph = {"core/a.cpp": set(), "platform/ios/b.mm": set(), "core/c.S": set()}
        groups = [
            (
                "cc",
                ("-Wall", "-DXR_DISABLED", "-U", "NDEBUG"),
                (".",),
                ["core/a.cpp", "core/c.S"],
            ),
            ("objc", ("-Wall", "-DXR_DISABLED"), (".",), ["platform/ios/b.mm"]),
        ]
        constants = Constants()
        objects = object_rules(groups, Includes(graph, {}, {"core/a.cpp"}), constants)
        lines = objects.rules
        self.assertEqual(constants.values["_COPTS_0"], ["-Wall"])
        # The separate form of an option, -U NDEBUG, stays one definition.
        self.assertEqual(constants.values["_DEFINES_0"], ["-DXR_DISABLED", "-UNDEBUG"])
        # Objective-C imports implicit modules, which see only the command line's macros.
        self.assertEqual(constants.values["_COPTS_1"], ["-Wall", "-DXR_DISABLED"])
        self.assertNotIn("_DEFINES_1", constants.values)
        library = _rules(lines, "cc_library")["_objects__core__a.cpp"]
        self.assertIn(
            "srcs = ['core/a.cpp', '_macros/_objects__core__a.cpp.h'], "
            "copts = _COPTS_0 + ['-include', '_macros/_objects__core__a.cpp.h']",
            library,
        )
        self.assertNotIn("local_defines", library)
        defines = _rules(lines, "godot_source_defines")["_objects__core__a.cpp__defines"]
        self.assertIn("copts = _COPTS_0, defines = _DEFINES_0", defines)
        self.assertIn("local_defines = ['GODOT_DECLARES_BUILD_PROFILE']", defines)
        self.assertIn(
            "sources = [':_objects__core__a.cpp__defines'], "
            "outs = ['_macros/_objects__core__a.cpp.h']",
            _rules(analysis_rules(objects.analyzed), "godot_define_analysis")[
                "_macros__core"
            ],
        )
        # Assembly keeps its options, after the others.
        assembly = _rules(lines, "cc_library")["_objects__core__c.S"]
        self.assertIn("srcs = ['core/c.S'], copts = _COPTS_0 + _DEFINES_0,", assembly)
        self.assertNotIn("_objects__core__c.S__defines", [rule.name for rule in lines])
        objc = _rules(lines, "objc_library")["_objects__platform__ios__b.mm"]
        self.assertIn("srcs = ['platform/ios/b.mm'], copts = _COPTS_1,", objc)
        self.assertEqual(objects.readers, {":_objects__core__a.cpp"})
        self.assertEqual(
            objects.labels,
            [
                ":_objects__core__a.cpp",
                ":_objects__core__c.S",
                ":_objects__platform__ios__b.mm",
            ],
        )

    def test_shards_split_by_scope_and_directory_and_size(self) -> None:
        def library(group: int, source: str) -> Library:
            copts = Ref(f"_COPTS_{group}")
            name = "_objects__" + source.replace("/", "__")
            return Library(source, name, copts, copts, copts, [], [])

        sources = [library(0, f"scene/{name}.cpp") for name in "abcde"] + [
            library(0, "thirdparty/zlib/a.c"),
            library(0, "thirdparty/zstd/a.c"),
            # Compile groups share shards: a variant may compile a source in another.
            library(1, "scene/f.cpp"),
            library(0, "main.cpp"),
            library(0, "scene/g.cpp"),
        ]
        scopes = {"_objects__scene__g.cpp": "p1__"}
        rules = _rules(
            analysis_rules(sources, size=2, scopes=scopes), "godot_define_analysis"
        )
        self.assertEqual(
            sorted(rules),
            [
                "_macros___root",
                "_macros__p1__scene",
                "_macros__scene__0",
                "_macros__scene__1",
                "_macros__scene__2",
                "_macros__thirdparty__zlib",
                "_macros__thirdparty__zstd",
            ],
        )
        # Sorted runs of nearly even size keep neighbouring sources together.
        self.assertIn(
            "outs = ['_macros/_objects__scene__a.cpp.h', '_macros/_objects__scene__b.cpp.h']",
            rules["_macros__scene__0"],
        )
        self.assertIn(
            "outs = ['_macros/_objects__scene__e.cpp.h', '_macros/_objects__scene__f.cpp.h']",
            rules["_macros__scene__2"],
        )


if __name__ == "__main__":
    unittest.main()
