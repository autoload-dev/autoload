"""The merged class fragments of a unit equal the class cache Godot's own scan writes."""

import json
import sys
import unittest
from pathlib import Path

from tools.validation.class_fragment import CACHE, class_cache

FILES = [Path(path) for path in sys.argv[1:]]
sys.argv = sys.argv[:1]


class ClassCacheTest(unittest.TestCase):
    def test_merged_fragments_equal_the_initializations_cache(self) -> None:
        fragments = [path for path in FILES if path.name.endswith(".classes.json")]
        self.assertEqual(["classes.classes.json"], [path.name for path in fragments])
        initialized = [
            path for path in FILES if path.name == "classes_run.view.initialized"
        ]
        self.assertEqual(1, len(initialized), FILES)
        godot = (initialized[0] / CACHE).read_text(encoding="utf-8")
        merged = class_cache([json.loads(fragments[0].read_text(encoding="utf-8"))])
        self.assertEqual(godot, merged)


if __name__ == "__main__":
    unittest.main()
