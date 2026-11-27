import tempfile
import unittest
from pathlib import Path

from tools.engine.include_graph import (
    ANY_HEADER,
    CompileGroup,
    Generated,
    TreeCache,
    components,
    include_graph,
)
from tools.engine.tests.source_files import write_tree


class IncludeGraphTest(unittest.TestCase):
    def graph(
        self,
        files: dict[str, str],
        groups: list[CompileGroup],
        generated: dict[str, Generated] | None = None,
        code: frozenset[str] = frozenset(),
    ) -> dict[str, frozenset[str]]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_tree(root, files)
            return include_graph(TreeCache(root, code), groups, generated or {})

    def test_sources_that_reach_a_custom_modules_code_include_every_header(self) -> None:
        # The code's contents come by label at build time, so the scan cannot read them:
        # a source that reaches it includes every header of the tree and its generators.
        # Headers include only what they name, so no header joins a cycle through it.
        code = frozenset(
            {"_custom_modules/probe/probe.cpp", "_custom_modules/probe/probe.h"}
        )
        graph = self.graph(
            {
                "_custom_modules/probe/probe.cpp": "",
                "_custom_modules/probe/probe.h": "",
                "modules/register.cpp": '#include "modules/register.h"\n',
                "modules/register.h": '#include "_custom_modules/probe/probe.h"\n',
                "core/object.h": '#include "core/typedefs.h"\n',
                "core/typedefs.h": "",
                "core/object.cpp": '#include "core/object.h"\n',
                "thirdparty/zlib/zlib.h": "",
                "doc/classes/Node.xml": "",
                # A module's other files, such as a table its code includes beside it.
                "_custom_modules/probe/opcodes.def": "",
            },
            [
                CompileGroup(
                    [
                        "_custom_modules/probe/probe.cpp",
                        "modules/register.cpp",
                        "core/object.cpp",
                    ],
                    ["."],
                    [],
                )
            ],
            {"core/version.gen.h": Generated("", (), ("core/version.gen.h",))},
            code,
        )
        self.assertEqual(graph["_custom_modules/probe/probe.cpp"], {ANY_HEADER})
        self.assertEqual(graph["_custom_modules/probe/probe.h"], set())
        self.assertEqual(
            graph["modules/register.cpp"], {"modules/register.h", ANY_HEADER}
        )
        self.assertEqual(graph["core/object.cpp"], {"core/object.h"})
        self.assertEqual(
            graph[ANY_HEADER],
            {
                "_custom_modules/probe/opcodes.def",
                "_custom_modules/probe/probe.h",
                "core/object.h",
                "core/typedefs.h",
                "core/version.gen.h",
                "modules/register.h",
                "thirdparty/zlib/zlib.h",
            },
        )
        self.assertEqual(
            [component for component in components(graph) if len(component) > 1], []
        )

    def test_quoted_includes_prefer_the_including_files_directory(self) -> None:
        graph = self.graph(
            {
                "modules/a/register_types.cpp": '#include "register_types.h"\n',
                "modules/a/register_types.h": '#include "core/object.h"\n',
                "modules/b/register_types.h": "",
                "core/object.h": "#pragma once\n",
            },
            [CompileGroup(["modules/a/register_types.cpp"], ["modules/b"], [])],
        )
        self.assertEqual(
            graph["modules/a/register_types.cpp"], {"modules/a/register_types.h"}
        )
        self.assertEqual(graph["modules/a/register_types.h"], {"core/object.h"})

    def test_angle_includes_name_every_include_directory_of_any_group(self) -> None:
        # Two groups may resolve <config.h> differently; a header both include gets both.
        graph = self.graph(
            {
                "lib/x.c": '#include "shared.h"\n',
                "lib/y.c": '#include "shared.h"\n',
                "lib/shared.h": "#include <config.h>\n#include <missing.h>\n",
                "lib/config.h": "",
                "x/config.h": "",
                "y/config.h": "",
            },
            [
                CompileGroup(["lib/x.c"], ["x"], []),
                CompileGroup(["lib/y.c"], ["y"], []),
            ],
        )
        self.assertEqual(
            graph["lib/shared.h"], {"lib/config.h", "x/config.h", "y/config.h"}
        )

    def test_sources_textual_files_and_includes_beyond_the_root(self) -> None:
        # Embree compiles one source that includes others.
        graph = self.graph(
            {
                "thirdparty/embree/bvh/hybrid4.cpp": '#include "intersector.cpp"\n',
                "thirdparty/embree/bvh/intersector.cpp": (
                    '#include "../common/shared.inc"\n#include "../../../../outside.h"\n'
                ),
                "thirdparty/embree/common/shared.inc": "",
            },
            [CompileGroup(["thirdparty/embree/bvh/hybrid4.cpp"], [], [])],
        )
        self.assertEqual(
            set(graph),
            {
                "thirdparty/embree/bvh/hybrid4.cpp",
                "thirdparty/embree/bvh/intersector.cpp",
                "thirdparty/embree/common/shared.inc",
            },
        )

    def test_computed_and_conditional_includes_count(self) -> None:
        graph = self.graph(
            {
                "font.cpp": "#include <ft2build.h>\n#include FT_FREETYPE_H\n"
                "#if __has_include(<optional.h>)\n#endif\n",
                "freetype/ft2build.h": "#include <freetype/config/ftheader.h>\n",
                "freetype/freetype/config/ftheader.h": (
                    "#define FT_FREETYPE_H <freetype/freetype.h>\n"
                ),
                "freetype/freetype/freetype.h": "",
                "optional.h": "",
                "crypto.c": "#include MBEDTLS_CONFIG_FILE\n",
                "mbedtls/godot_config.h": "",
            },
            [
                CompileGroup(["font.cpp"], ["freetype"], []),
                CompileGroup(
                    ["crypto.c"],
                    [],
                    ['-DMBEDTLS_CONFIG_FILE=\\"godot_config.h\\"', "-Imbedtls"],
                ),
            ],
        )
        self.assertEqual(graph["font.cpp"], {"freetype/ft2build.h", "optional.h"})
        self.assertEqual(
            graph["freetype/freetype/config/ftheader.h"],
            {"freetype/freetype/freetype.h"},
        )
        self.assertEqual(graph["crypto.c"], {"mbedtls/godot_config.h"})

    def test_generated_files_include_what_their_generator_writes(self) -> None:
        code = (
            "def build(target, source, env):\n"
            '    file.write("""#include "drivers/shader.h"\n""")\n'
            "    includes = [f'#include \"{path}/api/api.h\"' for path in paths]\n"
            "    tests = [f'#include \"{header}\"' for header in headers]\n"
            '    print_error(f\'In "{name}": #include "{line}" could not be found\')\n'
        )
        graph = self.graph(
            {
                "main.cpp": '#include "shaders/canvas.gen.h"\n',
                "drivers/shader.h": "",
                "platform/android/api/api.h": "",
                "platform/android/api/other.h": "",
                "tests/test_main.h": "",
            },
            [CompileGroup(["main.cpp"], [], [])],
            {
                "shaders/canvas.gen.h": Generated(
                    code, ("tests/test_main.h",), ("shaders/canvas.gen.h",)
                )
            },
        )
        self.assertEqual(
            graph["shaders/canvas.gen.h"],
            {"drivers/shader.h", "platform/android/api/api.h", "tests/test_main.h"},
        )

    def test_a_generated_file_includes_the_header_its_generator_writes(self) -> None:
        # Godot's translation generators write a header and a source that includes it.
        code = (
            "def make_translations(target, source, env):\n"
            "    target_h, target_cpp = str(target[0]), str(target[1])\n"
            '    file.write(f"""#include "{target_h}"\n""")\n'
        )
        doc = ("editor/translations/doc.gen.h", "editor/translations/doc.gen.cpp")
        # Another generator of the same builder file and the same inputs.
        other = ("editor/translations/other.gen.h",)
        inputs = ("doc/translations/de.po",)
        graph = self.graph(
            {"doc/translations/de.po": ""},
            [CompileGroup(["editor/translations/doc.gen.cpp"], [], [])],
            {
                **dict.fromkeys(doc, Generated(code, inputs, doc)),
                **dict.fromkeys(other, Generated(code, inputs, other)),
            },
        )
        self.assertEqual(
            graph["editor/translations/doc.gen.cpp"],
            {"doc/translations/de.po", "editor/translations/doc.gen.h"},
        )
        self.assertEqual(
            graph["editor/translations/doc.gen.h"], {"doc/translations/de.po"}
        )

    def test_files_that_include_each_other_form_one_component(self) -> None:
        graph = {
            "main.cpp": {"a.h"},
            "a.h": {"b.h", "c.h"},
            "b.h": {"a.h"},
            "c.h": set(),
        }
        self.assertEqual(components(graph), [["c.h"], ["a.h", "b.h"], ["main.cpp"]])


if __name__ == "__main__":
    unittest.main()
