"""Check actual Godot PCK membership across the fixture's packs."""

import json
import os
import re
import struct
import unittest
from pathlib import Path
from typing import Any

from tools.pck import pck_file_contents, pck_file_member

FIXTURE = "godot/private/tests/pack_membership/fixtures/project_with_pack_variants"
ROOT = Path(os.environ["TEST_SRCDIR"]) / os.environ["TEST_WORKSPACE"] / FIXTURE


def checked_report(test: unittest.TestCase, name: str) -> dict[str, Any]:
    """A pack's export report, checked against the PCK directory itself."""
    report = json.loads((ROOT / (name + ".export.json")).read_text())
    actual = pck_file_contents(ROOT / (name + ".pck"), include_paths=True)["paths"]
    test.assertEqual(sorted(actual), report["packed_paths"])
    return report


def packed(report: dict[str, Any], path: str) -> bool:
    return any(
        candidate in report["packed_paths"]
        for candidate in (path, path + ".remap", path + ".uid")
    )


def class_paths(pack: str) -> list[str]:
    """The script paths of a pack's global class list."""
    text = pck_file_member(ROOT / (pack + ".pck"), ".godot/global_script_class_cache.cfg")
    return sorted(re.findall(r'"path": "([^"]*)"', text.decode()))


def uid_paths(pack: str) -> list[str]:
    """The paths of a pack's UID cache: a count, then per entry an ID, a length and a path."""
    data = pck_file_member(ROOT / (pack + ".pck"), ".godot/uid_cache.bin")
    (count,), offset, paths = struct.unpack_from("<I", data), 4, []
    for _ in range(count):
        (length,) = struct.unpack_from("<I", data, offset + 8)
        offset += 12
        paths.append(data[offset : offset + length].decode())
        offset += length
    return sorted(paths)


class PackMembershipTest(unittest.TestCase):
    def test_extension_reachable_and_required_membership(self) -> None:
        for name in ["extension_pack", "extension_required_pack"]:
            with self.subTest(pack=name):
                report = checked_report(self, name)
                self.assertIn("native/hello.gdextension", report["packed_paths"])
                self.assertTrue(report["extension_library_paths"])
                self.assertFalse(
                    set(report["extension_library_paths"]) & set(report["selected_paths"])
                )
                if name == "extension_required_pack":
                    self.assertNotIn("main/levels/one.json", report["packed_paths"])

    def test_declared_raw_membership_variants(self) -> None:
        reports = {}
        for name in ("blue_pack", "red_pack", "data_pack"):
            with self.subTest(pack=name):
                reports[name] = report = checked_report(self, name)
                self.assertIn("main/levels/one.json", report["packed_paths"])
                self.assertIn("main/data/version.json", report["packed_paths"])
        self.assertIn("main/levels/two.json", reports["data_pack"]["packed_paths"])
        for report in reports.values():
            self.assertNotIn("tests/math_test.gd", report["packed_paths"])
        self.assertNotIn("main/shared/math.gd", reports["data_pack"]["packed_paths"])
        self.assertIn("main/shared/math.gd", reports["blue_pack"]["selected_paths"])
        self.assertIn("main/data/brand.json", reports["red_pack"]["selected_paths"])

    def test_reachable_base_and_dlc_packs_share_nothing(self) -> None:
        base, dlc = checked_report(self, "base_pack"), checked_report(self, "dlc_pack")
        base_selection, dlc_selection = (
            json.loads((ROOT / (name + ".selection.json")).read_text())
            for name in ("base_pack", "dlc_pack")
        )
        # The base pack holds what its main scene reaches; its raw data is read through
        # literal FileAccess paths.
        self.assertEqual(
            [
                "main/data/brand.json",
                "main/data/version.json",
                "main/levels/one.json",
                "main/main.gd",
                "main/main.tscn",
                "main/shared/math.gd",
            ],
            base["selected_paths"],
        )
        self.assertEqual(
            [
                "res://project.godot",
                "res://main/main.tscn",
                "res://main/main.gd",
                "res://main/levels/one.json",
            ],
            base_selection["chains"]["res://main/levels/one.json"],
        )
        self.assertFalse(packed(base, "main/levels/two.json"))
        for path in ("main/dlc/level.gd", "main/dlc/level.tscn"):
            self.assertFalse(packed(base, path))
            self.assertTrue(packed(dlc, path))
        # The DLC pack uses the shared script from the base pack.
        self.assertEqual(
            ["main/dlc/level.gd", "main/dlc/level.tscn"], dlc["selected_paths"]
        )
        self.assertEqual(
            "//" + FIXTURE + ":base_pack",
            dlc_selection["required"]["res://main/shared/math.gd"].lstrip("@"),
        )
        for path in base["selected_paths"]:
            self.assertFalse(packed(dlc, path))

    def test_class_list_and_uid_cache_hold_only_own_files(self) -> None:
        # FR-006: the DLC pack's export stages the base pack's shared script, which its
        # level preloads, but its class list and UID cache name only its own files. The
        # scripts have no authored UID: Godot's export gives them one, a written pack none.
        self.assertEqual(["res://main/shared/math.gd"], class_paths("base_pack"))
        self.assertEqual(["res://main/dlc/level.gd"], class_paths("dlc_pack"))
        for pack, own in [
            ("base_pack", ["res://main/main.gd", "res://main/shared/math.gd"]),
            ("dlc_pack", ["res://main/dlc/level.gd"]),
        ]:
            with self.subTest(pack=pack):
                written = checked_report(self, pack)["pack_conversion"] == "none"
                self.assertEqual([] if written else own, uid_paths(pack))


if __name__ == "__main__":
    unittest.main()
