import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

from tools.engine.feature_macros import FeatureMacroScan, assembles, feature_options
from tools.engine.include_graph import CompileGroup, Generated, include_graph
from tools.engine.render import copts_constants


def write_tree(root: Path, files: dict[str, str]) -> None:
    """Write files below a source root."""
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)


class FeatureMacroTest(unittest.TestCase):
    COPTS = ("-O2", "-DXR_DISABLED", "-DNDEBUG", "-D_3D_DISABLED", "-DGLES3_ENABLED")

    def copts(
        self,
        files: dict[str, str],
        source: str = "main.cpp",
        copts: Sequence[str] = COPTS,
        generated: dict[str, Generated] | None = None,
    ) -> list[str]:
        """Return the options a source of a tree compiles with."""
        generated = generated or {}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_tree(root, files)
            graph = include_graph(root, [CompileGroup([source], [], copts)], generated)
            scan = FeatureMacroScan(root, graph, generated, [copts])
            return scan.copts(source, copts)

    def test_only_godot_feature_macros_can_be_dropped(self) -> None:
        self.assertEqual(
            feature_options(
                [
                    "-DXR_DISABLED",
                    "-D_3D_DISABLED",
                    "-DTHREADS_ENABLED=1",
                    "-D__ARM_FEATURE_ENABLED",
                    "-D_LIBCPP_HARDENING_ENABLED",
                    "-DNDEBUG",
                    "-D_FILE_OFFSET_BITS=64",
                    "-UXR_DISABLED",
                ]
            ),
            {
                "-DXR_DISABLED": "XR_DISABLED",
                "-D_3D_DISABLED": "_3D_DISABLED",
                "-DTHREADS_ENABLED=1": "THREADS_ENABLED",
            },
        )

    def test_a_source_keeps_the_macros_its_includes_name_in_their_order(self) -> None:
        files = {
            "main.cpp": '#include "scene.h"\n',
            "scene.h": "#if !defined(_3D_DISABLED) // and GLES3_ENABLED in a comment\n#endif\n",
            "other.cpp": "int other;\n",
        }
        self.assertEqual(
            self.copts(files),
            ["-O2", "-DNDEBUG", "-D_3D_DISABLED", "-DGLES3_ENABLED"],
        )
        self.assertEqual(self.copts(files, "other.cpp"), ["-O2", "-DNDEBUG"])

    def test_option_values_name_macros(self) -> None:
        copts = [*self.COPTS, "-DFEATURE=XR_DISABLED"]
        self.assertIn("-DXR_DISABLED", self.copts({"main.cpp": "FEATURE\n"}, copts=copts))

    def test_pasted_fragments_keep_the_macros_they_can_form(self) -> None:
        pasting = "#define FEATURE(m_name) m_name##_DISABLED\n"
        self.assertIn(
            "-DXR_DISABLED",
            self.copts({"main.cpp": pasting + "#if FEATURE(XR)\n#endif\n"}),
        )
        # _DISABLED and NAV form no feature macro of the options.
        self.assertEqual(
            self.copts({"main.cpp": pasting + "#if FEATURE(NAV)\n#endif\n"}),
            ["-O2", "-DNDEBUG"],
        )

    def test_forwarded_and_expanded_arguments_are_pasted_fragments(self) -> None:
        concat = "#define CONCAT(a, b) a ## b\n"
        forwarded = concat + "#define FEATURE(x) CONCAT(x, _DISABLED)\nFEATURE(XR)\n"
        self.assertIn("-DXR_DISABLED", self.copts({"main.cpp": forwarded}))
        expanded = (
            concat + "#define NAME XR\n#define SUFFIX _DISABLED\nCONCAT(NAME, SUFFIX)\n"
        )
        self.assertIn("-DXR_DISABLED", self.copts({"main.cpp": expanded}))
        number = concat + "CONCAT(_, 3D_DISABLED)\n"
        self.assertIn("-D_3D_DISABLED", self.copts({"main.cpp": number}))

    def test_generated_files_read_what_their_generator_can_write(self) -> None:
        files = {
            "main.cpp": '#include "features.gen.h"\n',
            "icon.png": "",
        }
        code = 'def build(target, source, env):\n    write(f"#ifdef {name}_DISABLED")\n'
        kept = self.copts(
            files,
            generated={"features.gen.h": Generated(code, (), '[{"value": ["xr"]}]')},
        )
        self.assertIn("-DXR_DISABLED", kept)
        self.assertNotIn("-DGLES3_ENABLED", kept)
        escaped = self.copts(
            files,
            generated={"features.gen.h": Generated('write("\\nXR_DISABLED")\n', ())},
        )
        self.assertIn("-DXR_DISABLED", escaped)
        # Single characters of a generator's code or inputs join no name.
        dropped = self.copts(
            files | {"icon.png": "x r"},
            generated={
                "features.gen.h": Generated(
                    "def build(x, r): write(x + r)\n", ("icon.png",), '["_disabled"]'
                )
            },
        )
        self.assertNotIn("-DXR_DISABLED", dropped)

    def test_aliases_of_pasting_macros_paste(self) -> None:
        alias = "#define CONCAT(a, b) a ## b\n#define JOIN CONCAT\nJOIN(XR_, DISABLED)\n"
        self.assertIn("-DXR_DISABLED", self.copts({"main.cpp": alias}))
        spliced = "#define FEATURE(x) x ## \\ \n _DISABLED\nFEATURE(XR)\n"
        self.assertIn("-DXR_DISABLED", self.copts({"main.cpp": spliced}))
        commented = "#define FEATURE(x) /* a\n */ x ## _DISABLED\nFEATURE /* b */ (XR)\n"
        self.assertIn("-DXR_DISABLED", self.copts({"main.cpp": commented}))

    def test_text_inputs_of_generators_need_not_be_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_tree(root, {"main.cpp": '#include "features.gen.h"\n'})
            (root / "names.txt").write_bytes("XR_DISABLED caf\xe9\n".encode("latin-1"))
            generated = {"features.gen.h": Generated("", ("names.txt",))}
            graph = include_graph(root, [CompileGroup(["main.cpp"], [], [])], generated)
            scan = FeatureMacroScan(root, graph, generated, [self.COPTS])
            self.assertIn("-DXR_DISABLED", scan.copts("main.cpp", self.COPTS))

    def test_each_distinct_set_of_options_is_one_constant(self) -> None:
        files = {
            "a.cpp": "#ifdef XR_DISABLED\n#endif\n",
            "b.cpp": "",
            "c.cpp": "",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_tree(root, files)
            sources = sorted(files)
            graph = include_graph(root, [CompileGroup(sources, [], self.COPTS)], {})
            scan = FeatureMacroScan(root, graph, {}, [self.COPTS])
            lines, by_source = copts_constants(3, self.COPTS, sources, scan)
        self.assertEqual(
            lines,
            [
                "_COPTS_3_0 = ['-O2', '-DXR_DISABLED', '-DNDEBUG']",
                "_COPTS_3_1 = ['-O2', '-DNDEBUG']",
            ],
        )
        self.assertEqual(
            by_source,
            {"a.cpp": "_COPTS_3_0", "b.cpp": "_COPTS_3_1", "c.cpp": "_COPTS_3_1"},
        )

    def test_names_assemble_from_fragments_and_numbers(self) -> None:
        self.assertTrue(assembles("_3D_DISABLED", {"_", "D_DISABLED"}, ()))
        self.assertTrue(assembles("XR_DISABLED", (), {"xr", "_disabled"}))
        self.assertFalse(assembles("XR_DISABLED", {"X", "_DISABLED"}, ()))


if __name__ == "__main__":
    unittest.main()
