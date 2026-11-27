import json
import tempfile
import unittest
from pathlib import Path

from tools.engine import custom_modules
from tools.engine.tests.source_files import write_tree

_MODULE = {
    "config.py": "def can_build(env, platform):\n    return True\n",
    "SCsub": 'Import("env")\n',
    "BUILD.bazel": "filegroup(name = 'probe')\n",
    "__pycache__/config.cpython-314.pyc": "",
    "probe.cpp": '#include "probe.h"\n',
    "probe.h": "#pragma once\n",
    "shaders/blur.glsl": "#[compute]\n",
    "doc_classes/Probe.xml": "<class/>\n",
}


class PrepareTest(unittest.TestCase):
    def _prepare(self, directory: str) -> tuple[Path, dict[str, object]]:
        module = Path(directory) / "workspace/modules/probe"
        write_tree(module, _MODULE)
        recipe = Path(directory) / "recipe"
        recipe.mkdir()
        declaration = custom_modules.parse_module(
            "probe", str(module), "@@//modules/probe:probe"
        )
        result = custom_modules.prepare(recipe, [declaration])
        return recipe, result

    def test_the_recipe_copies_what_shapes_the_graph(self) -> None:
        # Godot's build scripts, shader sources and data, which a script may read, decide
        # the graph by their contents.
        with tempfile.TemporaryDirectory() as directory:
            recipe, _result = self._prepare(directory)
            modules = recipe / "_custom_modules/probe"
            for name in [
                "config.py",
                "SCsub",
                "shaders/blur.glsl",
                "doc_classes/Probe.xml",
            ]:
                self.assertEqual((modules / name).read_text(), _MODULE[name], name)
            # Bazel's files are no part of the module.
            self.assertFalse((modules / "BUILD.bazel").exists())

    def test_the_code_comes_by_label_and_counts_by_path(self) -> None:
        # SCons finds every file of the module, but the code's contents are no input of
        # the repository: they come from the module's target when a build compiles them.
        with tempfile.TemporaryDirectory() as directory:
            recipe, result = self._prepare(directory)
            manifest = json.loads((recipe / custom_modules.MANIFEST).read_text())
            code = ["probe.cpp", "probe.h"]
            self.assertEqual(
                manifest,
                {"probe": {"label": "@@//modules/probe:probe", "files": code}},
            )
            placeholders = [f"_custom_modules/probe/{name}" for name in code]
            self.assertEqual(result["placeholders"], placeholders)
            for name in placeholders:
                self.assertEqual((recipe / name).read_text(), "", name)
            self.assertEqual(custom_modules.code_files(recipe), placeholders)

    def test_the_repository_watches_listings_and_graph_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _recipe, result = self._prepare(directory)
            self.assertEqual(
                result["modules"],
                {
                    "probe": {
                        "directories": [".", "doc_classes", "shaders"],
                        "files": [
                            "SCsub",
                            "config.py",
                            "doc_classes/Probe.xml",
                            "shaders/blur.glsl",
                        ],
                    }
                },
            )

    def test_a_pin_action_writes_the_placeholders_from_the_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recipe, _result = self._prepare(directory)
            source = Path(directory) / "pin"
            write_tree(
                source,
                {custom_modules.MANIFEST: (recipe / custom_modules.MANIFEST).read_text()},
            )
            written = custom_modules.write_placeholders(source)
            self.assertIn("_custom_modules/probe/probe.cpp", written)
            self.assertTrue((source / "_custom_modules/probe/probe.cpp").is_file())

    def test_invalid_module_names_fail(self) -> None:
        with self.assertRaises(ValueError):
            custom_modules.parse_module("2d", "/modules/x", "@@//x")


class ShapesGraphTest(unittest.TestCase):
    def test_every_file_but_the_code_shapes_the_graph(self) -> None:
        for name in ["SCsub", "config.py", "a.glsl", "icons/Probe.svg", "data.json"]:
            self.assertTrue(custom_modules.shapes_graph(Path(name)), name)
        for name in ["probe.cpp", "probe.h", "inline.inc", "bridge.mm"]:
            self.assertFalse(custom_modules.shapes_graph(Path(name)), name)


if __name__ == "__main__":
    unittest.main()
