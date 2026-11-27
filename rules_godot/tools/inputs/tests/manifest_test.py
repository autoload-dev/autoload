import json
import tempfile
import unittest
from pathlib import Path

from tools.inputs.manifest import add_resource_path_manifests, resource_path
from tools.inputs.mapped_paths import resolver


class ManifestTest(unittest.TestCase):
    def test_resource_identities_reject_escaping_paths(self) -> None:
        for path in ["../x", "/x", "a/../b", "a//b", "res://x", "a\\b", ""]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                resource_path(path)
        self.assertEqual(resource_path("generated/a.tres"), "generated/a.tres")

    def test_resource_path_manifests_merge_unless_they_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            for name, resource_paths in [
                ("one", {"a.gd": "x/a.gd"}),
                ("two", {"a.gd": "x/a.gd", "b.gd": "x/b.gd"}),
                ("other", {"a.gd": "y/a.gd"}),
            ]:
                (base / name).write_text(json.dumps(resource_paths))
            manifest = {"project_file": "project.godot"}
            add_resource_path_manifests(
                manifest, [base / "one", base / "two"], resolver([])
            )
            self.assertEqual(
                {"a.gd": "x/a.gd", "b.gd": "x/b.gd"}, manifest["member_resource_paths"]
            )
            with self.assertRaisesRegex(
                ValueError, "Conflicting staged sources for a.gd"
            ):
                add_resource_path_manifests(manifest, [base / "other"], resolver([]))


if __name__ == "__main__":
    unittest.main()
