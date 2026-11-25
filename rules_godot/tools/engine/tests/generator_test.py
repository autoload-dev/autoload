import json
import tempfile
import unittest
from pathlib import Path

from tools.engine.configure import write_json
from tools.engine.generator import File, run, safe_relative


class GeneratorTest(unittest.TestCase):
    def test_scons_file_node_name_matches_basename(self) -> None:
        node = File("servers/rendering/storage/make_ltc_lut.py")
        self.assertEqual(node.name, "make_ltc_lut.py")
        self.assertEqual(node.path, "servers/rendering/storage/make_ltc_lut.py")

    def test_scons_value_mapping_order_survives_manifest_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "generator.json"
            write_json(
                manifest,
                {"sources": [{"value": {"dependency": "first", "consumer": "second"}}]},
            )
            restored = json.loads(manifest.read_text())
            self.assertEqual(
                list(restored["sources"][0]["value"]), ["dependency", "consumer"]
            )

    def test_declared_file_and_value_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = root / "builder.py"
            code.write_text(
                'from pathlib import Path\ndef build(target, source, env):\n    Path(target[0]).write_text(Path(source[0]).read_text() + source[1].read()["suffix"])\n'
            )
            source = root / "input.txt"
            source.write_text("Godot")
            output = root / "output.h"
            spec = {
                "code_file": "builder.py",
                "function": "build",
                "targets": ["generated/result.h"],
                "sources": [{"path": "data.txt"}, {"value": {"suffix": " Bazel"}}],
            }
            run(
                spec,
                {"builder.py": str(code), "data.txt": str(source)},
                {"generated/result.h": str(output)},
            )
            self.assertEqual(output.read_text(), "Godot Bazel")

    def test_value_fields_come_from_declared_input_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = root / "builder.py"
            code.write_text(
                "from pathlib import Path\n"
                "def build(target, source, env):\n"
                "    value = source[0].read()\n"
                "    Path(target[0]).write_text(value['build'] + ' ' + value['git_hash'])\n"
            )
            build, hash_file = root / "build.txt", root / "hash.txt"
            build.write_text("custom-git")
            hash_file.write_text("abc1234")
            output = root / "version.h"
            spec = {
                "code_file": "builder.py",
                "function": "build",
                "targets": ["core/version.h"],
                "sources": [
                    {
                        "value": {"build": "custom", "git_hash": ""},
                        "files": {
                            "build": "_revision/build.txt",
                            "git_hash": "_revision/hash.txt",
                        },
                    }
                ],
            }
            run(
                spec,
                {
                    "builder.py": str(code),
                    "_revision/build.txt": str(build),
                    "_revision/hash.txt": str(hash_file),
                },
                {"core/version.h": str(output)},
            )
            self.assertEqual(output.read_text(), "custom-git abc1234")

    def test_missing_generator_output_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = root / "builder.py"
            code.write_text("def build(target, source, env):\n    return 0\n")
            spec = {
                "code_file": "builder.py",
                "function": "build",
                "targets": ["missing.h"],
                "sources": [],
            }
            with self.assertRaisesRegex(RuntimeError, "did not produce"):
                run(
                    spec,
                    {"builder.py": str(code)},
                    {"missing.h": str(root / "missing.h")},
                )

    def test_generator_paths_are_confined(self) -> None:
        for path in ("../escape", "/absolute/file", "dir/../../escape"):
            with self.assertRaises(ValueError):
                safe_relative(path)


if __name__ == "__main__":
    unittest.main()
