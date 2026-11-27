"""Check which extension descriptors a PCK contains and lists."""

import os
import unittest
from pathlib import Path

from tools.pack.pck import pck_file_contents, pck_file_member

FIXTURE = "godot/extension/tests/staging/fixtures/extension_load_probe"
ROOT = Path(os.environ["TEST_SRCDIR"]) / os.environ["TEST_WORKSPACE"] / FIXTURE
HELLO = ROOT / "hello.gdextension"


class PackTest(unittest.TestCase):
    def test_pack_carries_the_runtime_descriptor(self) -> None:
        pack = ROOT / "enabled_pack.pck"
        descriptor = pck_file_member(pack, "native/hello.gdextension")
        # The editor descriptor the export loaded names only extension editor libraries.
        self.assertEqual(HELLO.read_bytes(), descriptor)
        self.assertIn(
            "res://native/hello.gdextension", pck_file_contents(pack)["extension_list"]
        )


if __name__ == "__main__":
    unittest.main()
