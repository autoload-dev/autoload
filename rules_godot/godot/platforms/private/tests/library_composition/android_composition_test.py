"""
Library permissions, resources and placeholder values reach the APKs that select them.

Library permissions merge as the Android Gradle plugin's manifest merger merges them: below
the application's manifest, the named libraries in their order, then their dependencies
breadth-first, and a library's tools:node="remove" drops the permission from the libraries
ranked below it only
(https://developer.android.com/build/manage-manifests#merge_rule_markers).
"""

import argparse
import re
import sys
import unittest
from pathlib import Path

from godot.platforms.private.tests.library_composition.android_apps import apk, dump

_ROLES = (
    "absent",
    "direct",
    "loadable",
    "overlay",
    "permissions_application_manifest",
    "permissions_breadth_first",
    "permissions_declarer_first",
    "permissions_export_options",
    "permissions_remover_first",
    "permissions_transitive_remover",
    "placeholder",
    "source",
    "transitive",
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aapt", type=Path, required=True)
    for role in _ROLES:
        parser.add_argument("--" + role, nargs="+", required=True)
    return parser.parse_args(sys.argv[1:])


class AndroidCompositionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        args = _arguments()
        cls.dumps = {role: dump(args.aapt, apk(getattr(args, role))) for role in _ROLES}

    def _assert_library_permission(self, role: str) -> None:
        manifest, _ = self.dumps[role]
        self.assertIn("org.example.composition.PERMISSION", manifest)
        self.assertIn("uses-permission-sdk-23", manifest)
        self.assertRegex(manifest, re.compile(r"usesPermissionFlags[^\n]*0x10000"))
        self.assertRegex(manifest, re.compile(r"maxSdkVersion[^\n]*0x20"))

    def test_library_reaches_the_apk_through_every_public_path(self) -> None:
        # The application's platform_deps, an add-on the project names, a loadable pack and
        # an extension's platform_deps.
        for role in ("direct", "transitive", "loadable", "source"):
            with self.subTest(role=role):
                self._assert_library_permission(role)
                self.assertTrue("library-value" in self.dumps[role][1], role)

    def test_application_resources_override_library_values(self) -> None:
        self._assert_library_permission("overlay")
        self.assertTrue("app-value" in self.dumps["overlay"][1], "app-value")

    def test_application_without_the_library_carries_none_of_its_effects(self) -> None:
        manifest, resources = self.dumps["absent"]
        self.assertNotIn("org.example.composition.PERMISSION", manifest)
        self.assertFalse("composition_value" in resources, "composition_value")

    def test_manifest_values_fill_the_library_placeholder(self) -> None:
        manifest, _ = self.dumps["placeholder"]
        self.assertIn("org.example.placeholder.SCHEME", manifest)
        self.assertIn("org.example.manifestvalues.scheme", manifest)
        self.assertNotIn("${examplePlaceholder}", manifest)

    def _boot(self, role: str) -> bool:
        return "org.example.permissions.BOOT" in self.dumps[role][0]

    def test_library_removal_reaches_lower_ranked_libraries_only(self) -> None:
        self.assertFalse(self._boot("permissions_remover_first"))
        self.assertTrue(self._boot("permissions_declarer_first"))

    def test_transitive_removal_ranks_below_a_direct_declaration(self) -> None:
        # Google's play-services-ads-api removes RECEIVE_BOOT_COMPLETED below an ad
        # adapter, as BOOT's remover does below its parent; a Gradle build of an app
        # that uses both keeps the permission of its directly used notification library.
        self.assertTrue(self._boot("permissions_transitive_remover"))

    def test_dependencies_rank_breadth_first(self) -> None:
        # The remover two levels down ranks below the declarer one level down.
        self.assertTrue(self._boot("permissions_breadth_first"))

    def test_library_removal_leaves_the_application_declaration(self) -> None:
        # The application's own manifest and its pack's permissions/* export options.
        for role in ("permissions_application_manifest", "permissions_export_options"):
            with self.subTest(role=role):
                self.assertTrue(self._boot(role))
                self.assertNotIn("tools:node", self.dumps[role][0])

    def test_library_attributes_merge_into_the_application_declaration(self) -> None:
        # The export options declare LIMITED without a limit; a library limits it to
        # Android 12L (maxSdkVersion 32, 0x20).
        manifest, _ = self.dumps["permissions_export_options"]
        self.assertRegex(
            manifest,
            re.compile(r"permissions\.LIMITED\"[^\n]*\n[^\n]*maxSdkVersion[^\n]*0x20"),
        )


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
