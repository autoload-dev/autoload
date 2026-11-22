"""The pack of a glTF imported with an external buffer leaves the buffer out."""

import sys
import unittest

from tools.pck import pck_file_contents


class GltfPackTest(unittest.TestCase):
    def test_pack_excludes_the_buffer_import_input(self) -> None:
        paths = pck_file_contents(sys.argv[1], include_paths=True)["paths"]
        self.assertNotIn("main/triangle.bin", paths)


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1])
