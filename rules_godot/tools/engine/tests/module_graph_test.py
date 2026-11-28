import tempfile
import unittest
from pathlib import Path

from tools.engine.module_graph import module_closure, module_dependencies


class ModuleGraphTest(unittest.TestCase):
    def test_required_transitive_dependencies_and_optional_exclusion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, body in {
                "movie": 'env.module_add_dependencies("movie", ["vorbis"])',
                "vorbis": 'env.module_add_dependencies("vorbis", ["ogg"])',
                "ogg": "",
                "gltf": 'env.module_add_dependencies("gltf", ["movie"], optional=True)',
            }.items():
                config = root / "modules" / name / "config.py"
                config.parent.mkdir(parents=True)
                config.write_text(body)
            graph = module_dependencies(root)
            self.assertEqual(module_closure(["movie"], graph), ["movie", "ogg", "vorbis"])
            self.assertEqual(module_closure(["gltf"], graph), ["gltf"])

    def test_unknown_or_cyclic_dependencies_fail(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown Godot module"):
            module_closure(["typo"], {})
        with self.assertRaisesRegex(ValueError, "dependency cycle"):
            module_closure(["a"], {"a": ["b"], "b": ["a"]})

    def test_custom_modules_override_upstream_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream = root / "modules" / "same" / "config.py"
            custom = root / "custom" / "same" / "config.py"
            for config in [upstream, custom]:
                config.parent.mkdir(parents=True)
            upstream.write_text('env.module_add_dependencies("same", ["obsolete"])')
            custom.write_text("")
            self.assertEqual(module_dependencies(root, [root / "custom"]), {"same": []})

    def test_positional_optional_flag_excludes_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "modules" / "gltf" / "config.py"
            config.parent.mkdir(parents=True)
            config.write_text('env.module_add_dependencies("gltf", ["movie"], True)')
            self.assertEqual(module_dependencies(directory), {"gltf": []})

    def test_non_string_module_dependencies_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "modules" / "numbers" / "config.py"
            config.parent.mkdir(parents=True)
            config.write_text('env.module_add_dependencies("numbers", [1])')
            with self.assertRaisesRegex(ValueError, "Unsupported dependency declaration"):
                module_dependencies(directory)

    def test_dynamic_module_dependencies_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "modules" / "dynamic" / "config.py"
            config.parent.mkdir(parents=True)
            config.write_text(
                'env.module_add_dependencies("dynamic", calculate_dependencies())'
            )
            with self.assertRaisesRegex(ValueError, "Unsupported dependency declaration"):
                module_dependencies(directory)


if __name__ == "__main__":
    unittest.main()
