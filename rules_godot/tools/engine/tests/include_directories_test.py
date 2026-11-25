"""The include directories each engine source reaches."""

import tempfile
import unittest
from pathlib import Path

from tools.engine.include_graph import CompileGroup, include_graph, reached_directories
from tools.engine.render import include_rules, object_rules


class IncludeDirectoryTest(unittest.TestCase):
    def test_files_reach_the_directories_that_hold_them_or_their_includes(
        self,
    ) -> None:
        graph = {
            "core/a.cpp": {"core/a.h"},
            "core/a.h": {"thirdparty/zlib/zlib.h", "core/b.h"},
            "core/b.h": {"core/a.h"},
            "thirdparty/zlib/zlib.h": set(),
            "_custom_modules/probe/probe.cpp": {"core/a.h"},
        }
        directories = [
            ".",
            "./core",
            "thirdparty/zlib/",
            "thirdparty/zstd",
            "_custom_modules",
        ]
        reached = reached_directories(graph, directories)
        self.assertEqual(reached["core/a.cpp"], {".", "./core", "thirdparty/zlib/"})
        self.assertEqual(reached["core/b.h"], reached["core/a.cpp"])
        self.assertEqual(reached["thirdparty/zlib/zlib.h"], {".", "thirdparty/zlib/"})
        self.assertEqual(
            reached["_custom_modules/probe/probe.cpp"],
            {".", "./core", "thirdparty/zlib/", "_custom_modules"},
        )

    def test_each_source_names_the_include_directories_it_reaches(self) -> None:
        files = {
            "core/a.cpp": '#include "core/a.h"\n',
            "core/a.h": "",
            "main/main.cpp": "#include <probe/register_types.h>\n",
            "_custom_modules/probe/register_types.h": "",
        }
        # A custom module's directory leaves the include path of the sources that do
        # not reach it, so adding the first custom module keeps their cache keys.
        includes = ("_custom_modules", ".")
        sources = ["core/a.cpp", "main/main.cpp"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, text in files.items():
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text(text)
            graph = include_graph(root, [CompileGroup(sources, includes, [])], {})
            _, targets = include_rules(graph)
            lines, _ = object_rules(
                [("cpp", (), includes, sources)], graph, targets, set()
            )
        self.assertIn("_INCLUDES_0_0 = ['.']", lines)
        self.assertIn("_INCLUDES_0_1 = ['_custom_modules', '.']", lines)
        rules = {
            line.split("'")[1]: line for line in lines if line.startswith("cc_library")
        }
        self.assertIn("includes = _INCLUDES_0_0,", rules["_objects__core__a.cpp"])
        self.assertIn("includes = _INCLUDES_0_1,", rules["_objects__main__main.cpp"])


if __name__ == "__main__":
    unittest.main()
