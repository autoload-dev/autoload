"""The settings the ruleset fixes in the project.godot of imports and exports."""

import unittest

from godot.private.project_config import compose_project, setting_key, statement_groups


class PinnedSettingsTest(unittest.TestCase):
    def test_pinned_settings_replace_the_authored_ones_and_their_overrides(
        self,
    ) -> None:
        # An authored false would let the editor's CPU decide; an override the editor
        # applies would do the same on some execution platforms only.
        base = (
            'config_version=5\n[rendering]\nmethod="forward_plus"\n'
            "textures/vram_compression/import_etc2_astc=false\n"
            "textures/vram_compression/import_etc2_astc.linux=false\n"
            "textures/vram_compression/import_s3tc_bptc.editor=false\n"
            "textures/vram_compression/import_s3tc_bptc_extra=false\n"
        )
        pinned = {
            "rendering/textures/vram_compression/import_etc2_astc": "true",
            "rendering/textures/vram_compression/import_s3tc_bptc": "true",
        }
        configured = compose_project(
            base,
            {},
            {},
            "",
            purpose="import",
            active_features={"editor", "linux"},
            pinned=pinned,
        )
        statements = {
            setting_key(section, key): text.split("=", 1)[1].strip()
            for text, section, key in statement_groups(configured)
            if key is not None
        }
        self.assertEqual(
            {
                "config_version": "5",
                "rendering/method": '"forward_plus"',
                "rendering/textures/vram_compression/import_etc2_astc": "true",
                "rendering/textures/vram_compression/import_s3tc_bptc": "true",
                "rendering/textures/vram_compression/import_s3tc_bptc_extra": "false",
            },
            statements,
        )


if __name__ == "__main__":
    unittest.main()
