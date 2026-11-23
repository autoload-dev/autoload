"""Tests of how Starlark and GDScript are presented to CodeScene."""

import contextlib
import io
import textwrap
import unittest

from tools.code_health.translation import (
    MACRO_DIRECTIVE,
    original_title,
    parameter_count,
    translate,
)


def source(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n")


class StarlarkTranslationTest(unittest.TestCase):
    def macros(self, text: str) -> list[str]:
        return translate("pkg/defs.bzl", source(text), macro_arguments=False).macros

    def test_starlark_is_analysed_as_python_under_a_virtual_name(self) -> None:
        translation = translate("pkg/defs.bzl", "x = 1\n", macro_arguments=False)
        self.assertEqual("pkg/defs.bzl.py", translation.virtual_name)
        self.assertEqual("x = 1\n", translation.source)

    def test_macro_declaring_a_target_with_its_name_is_exempt(self) -> None:
        text = source("""
            def godot_thing(name, a, b, c, d):
                native.filegroup(name = name, srcs = [a, b, c, d])
            """)
        translation = translate("pkg/defs.bzl", text, macro_arguments=False)
        self.assertEqual(["godot_thing"], translation.macros)
        self.assertEqual(MACRO_DIRECTIVE, translation.source.splitlines(keepends=True)[0])

    def test_macro_handing_its_name_to_a_declaring_function_is_exempt(self) -> None:
        self.assertEqual(
            ["godot_run"],
            self.macros("""
                def _executable(rule_, name, a, b, c):
                    rule_(name = name, a = a, b = b, c = c)

                def godot_run(name, a, b, c, d):
                    _executable(_godot_run, name, a, b, c)
                """),
        )

    def test_symbolic_macro_implementation_is_exempt(self) -> None:
        self.assertEqual(
            ["_impl"],
            self.macros("""
                def _impl(name, visibility, a, b, c):
                    _helper(a, b, c)

                thing = macro(
                    implementation = _impl,
                )
                """),
        )

    def test_documented_macro_without_a_result_is_exempt(self) -> None:
        self.assertEqual(
            ["table_macro"],
            self.macros('''
                def table_macro(name, a, b, c, d):
                    """
                    Declare the targets of a table.

                    Args:
                        name: The target name.
                    """
                    for row in _rows(a, b, c, d):
                        _RULES[row.rule](**row.attrs)
                '''),
        )

    def test_helpers_taking_a_name_are_not_macros(self) -> None:
        self.assertEqual(
            [],
            self.macros('''
                def validate(name, a, b, c, d):
                    if not a:
                        fail("%s: no a" % name)

                def declarations(name, a, b, c, d):
                    """
                    Args:
                        name: The target name.
                    """
                    return [a, b, c, d]
                '''),
        )

    def test_macros_within_the_argument_limit_are_left_alone(self) -> None:
        self.assertEqual(
            [],
            self.macros("""
                def small(name, a):
                    native.filegroup(name = name, srcs = [a])
                """),
        )

    def test_findings_map_back_to_the_original_lines(self) -> None:
        text = source("""
            x = 1

            def first(name, a, b, c, d):
                native.filegroup(name = name)

            def second(name, a, b, c, d):
                native.filegroup(name = name)
            """)
        translation = translate("pkg/defs.bzl", text, macro_arguments=False)
        virtual = translation.source.splitlines()
        for original_line in (3, 6):
            virtual_line = virtual.index(text.splitlines()[original_line - 1]) + 1
            self.assertEqual(original_line, translation.original_line(virtual_line))
        self.assertEqual("first:4", original_title("first:5", translation))

    def test_macro_arguments_can_be_counted(self) -> None:
        text = "def m(name, a, b, c, d):\n    native.filegroup(name = name)\n"
        translation = translate("pkg/defs.bzl", text, macro_arguments=True)
        self.assertEqual(text, translation.source)
        self.assertEqual([], translation.macros)

    def test_macro_naming_targets_after_a_variable_derived_from_its_name_is_exempt(
        self,
    ) -> None:
        self.assertEqual(
            ["inputs"],
            self.macros("""
                def inputs(name, a, b, c, d):
                    prefix = name.replace("/", "_") + ".inputs"
                    native.filegroup(name = prefix, srcs = [a, b, c, d])
                    native.filegroup(name = "%s.more" % prefix)
                    return struct(prefix = prefix)
                """),
        )

    def test_symbolic_macro_implementation_with_inherited_attributes_is_exempt(
        self,
    ) -> None:
        self.assertEqual(
            ["_impl"],
            self.macros("""
                def _impl(name, visibility, a, b, **kwargs):
                    _rule(name = name, visibility = visibility, a = a, b = b, **kwargs)

                thing = macro(
                    implementation = _impl,
                    inherit_attrs = _rule,
                )
                """),
        )

    def test_implementations_and_helpers_taking_a_context_are_not_macros(self) -> None:
        self.assertEqual(
            [],
            self.macros("""
                def _rule_impl(ctx):
                    return [DefaultInfo()]

                def _repository_impl(rctx):
                    rctx.file("BUILD.bazel", "")

                def _extension_impl(mctx):
                    _repository(name = "hub")

                def run_action(ctx, executable, inputs, outputs, arguments):
                    ctx.actions.run(executable = executable, inputs = inputs)
                """),
        )


class DocumentationTest(unittest.TestCase):
    def translated(self, text: str) -> str:
        return translate("pkg/defs.bzl", source(text), macro_arguments=False).source

    def test_docstrings_are_cut_to_an_empty_string(self) -> None:
        self.assertEqual(
            source("""
                ""

                def f(a):
                    ""
                    return a
                """),
            self.translated('''
                """Module documentation,
                over two lines."""

                def f(a):
                    """
                    Return a.

                    Args:
                        a: The value.
                    """
                    return a
                '''),
        )

    def test_doc_values_are_cut_however_they_are_written(self) -> None:
        self.assertEqual(
            source("""
                thing = rule(
                    doc = "",
                    attrs = {
                        "a": attr.string(doc = ""),
                        "b": attr.string(doc = "", default = "x"),
                    },
                )
                """),
            self.translated('''
                thing = rule(
                    doc = """
                    Build a thing.
                    """,
                    attrs = {
                        "a": attr.string(doc = "The first " +
                                         "attribute."),
                        "b": attr.string(doc = (
                            "The second "
                            "attribute."
                        ), default = "x"),
                    },
                )
                '''),
        )

    def test_longer_documentation_translates_the_same(self) -> None:
        short = '''
            def f(name, a):
                """Short."""
                native.filegroup(name = name, srcs = [a])

            thing = rule(
                implementation = f,
                doc = "Short.",
            )
            '''
        long = '''
            def f(name, a):
                """
                A much longer docstring.

                Args:
                    name: The target name.
                    a: The source.
                """
                native.filegroup(name = name, srcs = [a])

            thing = rule(
                implementation = f,
                doc = """
                Several lines of documentation.
                """,
            )
            '''
        self.assertEqual(
            "".join(self.translated(short).split()),
            "".join(self.translated(long).split()),
        )

    def test_strings_that_are_code_are_kept(self) -> None:
        text = source("""
            x = "a"
            def f(name, doc):
                "%s" % name
                ", ".join([name])
                fail("no %s" % name)
                _rule(doc = "%s doc" % name, other = doc)
            """)
        self.assertEqual(text, self.translated(text))

    def test_findings_after_cut_documentation_map_back_to_the_original_lines(
        self,
    ) -> None:
        text = source('''
            def big(name, a, b, c, d):
                """
                Declare a target.
                """
                native.filegroup(name = name)
            ''')
        translation = translate("pkg/defs.bzl", text, macro_arguments=False)
        virtual = translation.source.splitlines()
        self.assertEqual(MACRO_DIRECTIVE.rstrip("\n"), virtual[0])
        self.assertEqual(1, translation.original_line(1))
        self.assertEqual(1, translation.original_line(2))
        self.assertEqual(
            5,
            translation.original_line(
                virtual.index("    native.filegroup(name = name)") + 1
            ),
        )
        self.assertEqual("big:1", original_title("big:2", translation))

    def test_untokenizable_source_keeps_its_documentation(self) -> None:
        text = 'def f():\n    """Unterminated.\n'
        with contextlib.redirect_stderr(io.StringIO()) as error:
            translated = translate("pkg/defs.bzl", text, macro_arguments=False)
        self.assertEqual(text, translated.source)
        self.assertIn("documentation kept", error.getvalue())


class GDScriptTranslationTest(unittest.TestCase):
    def test_functions_and_classes_become_python_on_the_same_lines(self) -> None:
        text = source("""
            extends Node
            class Inner extends Resource:
            \tstatic func make() -> Inner:
            \t\treturn Inner.new()
            func _ready() -> void:
            \tpass
            """)
        translation = translate("main/game.gd", text, macro_arguments=False)
        self.assertEqual("main/game.gd.py", translation.virtual_name)
        self.assertEqual(
            [
                "extends Node",
                "class Inner(Resource):",
                "\tdef make() -> Inner:",
                "\t\treturn Inner.new()",
                "def _ready() -> void:",
                "\tpass",
            ],
            translation.source.splitlines(),
        )


class NativeLanguageTest(unittest.TestCase):
    def test_supported_languages_are_passed_through(self) -> None:
        translation = translate("tools/x.py", "def f(): pass\n", macro_arguments=False)
        self.assertEqual(
            ("tools/x.py", "def f(): pass\n"),
            (
                translation.virtual_name,
                translation.source,
            ),
        )


class ParameterCountTest(unittest.TestCase):
    def test_defaults_comments_and_nested_brackets_count_once(self) -> None:
        lines = source("""
            def m(
                    name,
                    deps = [],  # a comment, with a comma
                    opts = {"a": (1, 2)},
                    **kwargs):
                pass
            """).splitlines(keepends=True)
        self.assertEqual(4, parameter_count(lines, 0))


if __name__ == "__main__":
    unittest.main()
