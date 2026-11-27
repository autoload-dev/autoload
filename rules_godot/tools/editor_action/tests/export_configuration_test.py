"""The preset writes authored fields as Godot literals and preserves their absence."""

import unittest

from tools.editor_action import export
from tools.editor_action.export import export_presets


class ExportConfigurationTest(unittest.TestCase):
    def test_omitted_script_mode_uses_godot_default(self) -> None:
        text = export_presets({"preset_platform": "Linux"})
        self.assertNotIn("script_export_mode=", text)

    def test_excluded_paths_cannot_be_literal_export_filters(self) -> None:
        with self.assertRaisesRegex(ValueError, "literal export filter"):
            export_presets({"preset_platform": "Linux"}, ["levels/[1].json"])

    def test_preset_fields_use_godot_literal_types(self) -> None:
        text = export_presets(
            {
                "preset_platform": "Linux",
                "preset_settings": {"script_export_mode": "0"},
            }
        )
        self.assertIn("script_export_mode=0", text)

    def test_features_become_the_preset_custom_features(self) -> None:
        text = export_presets(
            {
                "preset_platform": "iOS",
                "features": ["production", "debug_tools", "simulator"],
            }
        )
        self.assertIn('custom_features="production,debug_tools,simulator"', text)
        self.assertNotIn("custom_features=", export_presets({"preset_platform": "Linux"}))

    def test_plugin_options_remain_godot_literals(self) -> None:
        text = export_presets(
            {
                "preset_platform": "Linux",
                "export_options": {
                    "game_plugin/threshold": "Vector2(1, 2)",
                    "game_plugin/enabled": "true",
                },
            }
        )
        self.assertIn("game_plugin/threshold=Vector2(1, 2)", text)
        self.assertIn("game_plugin/enabled=true", text)

    def test_hidden_registered_options_and_plugin_types_are_checked(self) -> None:
        facts = {
            "options": {
                "ssh_remote_deploy/run_script": "default",
                "game_plugin/enabled": True,
            },
            "option_types": {
                "ssh_remote_deploy/run_script": "String",
                "game_plugin/enabled": "bool",
            },
        }
        export.validate_export_facts(
            {"authored_export_options": {"game_plugin/enabled": "true"}}, facts
        )
        with self.assertRaisesRegex(ValueError, "game_plugin/enabled"):
            export.validate_export_facts(
                {"authored_export_options": {"game_plugin/enabled": '"wrong"'}},
                {
                    "options": {"game_plugin/enabled": "wrong"},
                    "option_types": {"game_plugin/enabled": "bool"},
                },
            )

    def test_unauthored_registered_options_are_not_checked(self) -> None:
        export.validate_export_facts(
            {"authored_export_options": {}},
            {
                "options": {"gradle_build/use_gradle_build": False},
                "option_types": {"gradle_build/use_gradle_build": "bool"},
            },
        )

    def test_unknown_export_option_requires_registered_plugin(self) -> None:
        with self.assertRaisesRegex(ValueError, "an extension.s export plugin"):
            export.validate_export_facts(
                {"authored_export_options": {"unknown/key": "true"}},
                {"options": {}, "option_types": {}},
            )

    def test_authored_hidden_option_is_validated_without_policy_membership(self) -> None:
        export.validate_export_facts(
            {"authored_export_options": {"capabilities/performance_a12": "true"}},
            {
                "options": {"capabilities/performance_a12": True},
                "option_types": {"capabilities/performance_a12": "bool"},
            },
        )

    def test_prelude_does_not_grant_authored_registration(self) -> None:
        manifest = {
            "preset_prelude": {"binary_format/embed_pck": "false"},
            "export_options": {"binary_format/embed_pck": "true"},
            "authored_export_options": {"binary_format/embed_pck": "true"},
        }
        with self.assertRaisesRegex(ValueError, "an extension.s export plugin"):
            export.validate_export_facts(manifest, {"options": {}, "option_types": {}})
        export.validate_export_facts(
            manifest,
            {
                "options": {"binary_format/embed_pck": True},
                "option_types": {"binary_format/embed_pck": "bool"},
            },
        )


if __name__ == "__main__":
    unittest.main()
