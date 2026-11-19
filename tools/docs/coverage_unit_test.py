"""Regression tests for gaps that generation alone does not reject."""

import unittest

from google.protobuf import text_format

from tools.docs.coverage import documentation_errors, module_apis, parse_module


class CoverageTest(unittest.TestCase):
    def errors(self, text: str, source: str = "") -> list[str]:
        return documentation_errors(
            parse_module('module_docstring: "Module."\n' + text), source
        )

    def test_other_evaluated_exports_cannot_bypass_output_contract_coverage(self) -> None:
        module = parse_module(
            'starlark_other_symbol_info { name: "new_constant" doc: "Meaning." }'
        )
        self.assertIn("unsupported evaluated API kind", module_apis(module)[1][0])

    def test_new_evaluated_api_requires_output_contract_sections(self) -> None:
        module = parse_module(
            'rule_info { rule_name: "new_rule" doc_string: "Purpose." }'
        )
        self.assertIn("Default outputs: missing section", module_apis(module)[1][0])

    def test_providers_need_no_output_contract(self) -> None:
        module = parse_module(
            'provider_info { provider_name: "ThingInfo" doc_string: "A provider." }'
        )
        self.assertEqual([], module_apis(module)[1])

    def test_missing_rule_attribute_in_reexport_is_rejected(self) -> None:
        errors = self.errors(
            """rule_info {
          rule_name: "alias" doc_string: "A rule."
          attribute { name: "inherited" }
        }""",
            "alias = _original",
        )
        self.assertEqual(errors, ["alias.inherited: missing documentation"])

    def test_bazel_common_attribute_uses_bazel_documentation(self) -> None:
        errors = self.errors(
            """macro_info {
          macro_name: "pack" doc_string: "A macro."
          attribute { name: "testonly" natively_defined: true }
        }""",
            "pack = macro()",
        )
        self.assertEqual(errors, [])

    def test_provider_field_needs_description(self) -> None:
        errors = self.errors(
            """provider_info {
          provider_name: "ThingInfo" doc_string: "A provider."
          field_info { name: "files" }
        }""",
            "ThingInfo = provider()",
        )
        self.assertEqual(errors, ["ThingInfo.files: missing documentation"])

    def test_extension_tags_and_their_attributes_are_checked(self) -> None:
        errors = self.errors(
            """module_extension_info {
          extension_name: "engine" doc_string: "An extension."
          tag_class { tag_name: "pin" attribute { name: "version" } }
        }""",
            "engine = module_extension()",
        )
        self.assertEqual(
            errors,
            [
                "engine.pin: missing documentation",
                "engine.pin.version: missing documentation",
            ],
        )

    def test_short_function_parameters_are_checked(self) -> None:
        errors = self.errors(
            """func_info {
          function_name: "tiny" doc_string: "A helper."
          parameter { name: "value" }
        }""",
            "def tiny(value):\n    return value\n",
        )
        self.assertEqual(errors, ["tiny(value): missing documentation"])

    def test_symbolic_macro_and_aspect_attributes_are_checked(self) -> None:
        errors = self.errors(
            """macro_info {
          macro_name: "make" doc_string: "A macro." attribute { name: "srcs" }
        }
        aspect_info {
          aspect_name: "scan" doc_string: "An aspect." attribute { name: "mode" }
        }""",
            "make = macro()\nscan = aspect()",
        )
        self.assertEqual(
            errors,
            ["make.srcs: missing documentation", "scan.mode: missing documentation"],
        )

    def test_unextracted_constant_is_not_silently_ignored(self) -> None:
        self.assertIn(
            "ANSWER: exported symbol missing", self.errors("", "ANSWER = 42")[0]
        )

    def test_documented_constant_and_namespaced_function_pass(self) -> None:
        self.assertEqual(
            self.errors(
                """starlark_other_symbol_info { name: "ANSWER" doc: "The answer." }
          func_info { function_name: "api.helper" doc_string: "A helper." }
        """,
                "ANSWER = 42\napi = struct(helper = _helper)",
            ),
            [],
        )

    def test_unknown_schema_field_fails_closed(self) -> None:
        with self.assertRaises(text_format.ParseError):
            parse_module('new_kind_of_api { name: "unhandled" }')


if __name__ == "__main__":
    unittest.main()
