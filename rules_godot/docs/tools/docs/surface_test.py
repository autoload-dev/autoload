"""Regression tests for unique public entrypoints and internal boundaries."""

import unittest
from typing import Any

from tools.docs.coverage import ModuleInfo, parse_module
from tools.docs.surface import assign_surface

PUBLIC = "//godot:defs.bzl"
OTHER = "//godot/platforms:linux.bzl"
INTERNAL = "//godot/private:helper.bzl"


def manifest() -> dict[str, Any]:
    return {
        "PUBLIC_APIS": {
            PUBLIC: ["thing"],
            OTHER: ["other_thing"],
        },
        "CROSS_REPOSITORY_MODULES": {},
        "PUBLIC_TARGETS": {},
    }


def metadata(
    name: str,
    origin: str = "thing",
    file: str = "@autoload_rules_godot//godot/private:impl.bzl",
) -> ModuleInfo:
    return parse_module(f'''module_docstring: "A module."
      rule_info {{ rule_name: "{name}" doc_string: "Build a thing."
        origin_key {{ name: "{origin}" file: "{file}" }}
      }}''')


def inputs() -> dict[str, ModuleInfo]:
    return {
        PUBLIC: metadata("thing"),
        OTHER: metadata("other_thing", origin="other_thing"),
    }


class SurfaceTest(unittest.TestCase):
    def test_identically_named_independent_rules_do_not_collapse(self) -> None:
        config = manifest()
        config["PUBLIC_APIS"][OTHER] = ["thing"]
        modules = inputs()
        modules[OTHER] = metadata("thing", file="//godot/private:another.bzl")
        owners = assign_surface(config, modules)
        self.assertEqual(len(owners), 2)

    def test_renamed_duplicate_primary_is_rejected(self) -> None:
        modules = inputs()
        modules[OTHER] = metadata(
            "other_thing", file="@@autoload_rules_godot//godot/private:impl.bzl"
        )
        with self.assertRaisesRegex(ValueError, "duplicate primary reference"):
            assign_surface(manifest(), modules)

    def test_second_public_load_is_rejected_even_if_not_selected(self) -> None:
        modules = inputs()
        modules[OTHER].rule_info.add().CopyFrom(metadata("extra_name").rule_info[0])
        with self.assertRaisesRegex(
            ValueError, "extra_name: additional public load path"
        ):
            assign_surface(manifest(), modules)

    def test_new_export_cannot_hide_behind_the_primary_selection(self) -> None:
        modules = inputs()
        modules[PUBLIC].rule_info.add().CopyFrom(
            metadata("new_api", origin="new_api").rule_info[0]
        )
        with self.assertRaisesRegex(
            ValueError, "new_api: public export has no primary reference"
        ):
            assign_surface(manifest(), modules)

    def test_removed_primary_symbol_is_rejected(self) -> None:
        config = manifest()
        config["PUBLIC_APIS"][PUBLIC].append("removed")
        with self.assertRaisesRegex(ValueError, "removed: primary symbol does not exist"):
            assign_surface(config, inputs())

    def test_generated_repository_helpers_cannot_be_public_exports(self) -> None:
        for category, name_field in (
            ("rule_info", "rule_name"),
            ("func_info", "function_name"),
        ):
            for selected in (False, True):
                with self.subTest(category=category, explicitly_selected=selected):
                    config = manifest()
                    config["CROSS_REPOSITORY_MODULES"][INTERNAL] = (
                        "Used by generated BUILD files."
                    )
                    modules = inputs()
                    helper = parse_module(f"""{category} {{ {name_field}: "helper" doc_string: "Generate files."
                        origin_key {{ name: "implementation_helper" file: "@autoload_rules_godot{INTERNAL}" }}
                    }}""")
                    getattr(modules[PUBLIC], category).add().CopyFrom(
                        getattr(helper, category)[0]
                    )
                    if selected:
                        config["PUBLIC_APIS"][PUBLIC].append("helper")
                    with self.assertRaisesRegex(
                        ValueError, "cross-repository module leaked"
                    ):
                        assign_surface(config, modules)


if __name__ == "__main__":
    unittest.main()
