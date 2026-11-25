import tempfile
import unittest
from pathlib import Path

from tools.engine import build_profile
from tools.engine.include_graph import CompileGroup, Generated, include_graph
from tools.engine.tests.source_files import write_tree


class BuildProfileTest(unittest.TestCase):
    UPSTREAM_CLASS_DB = (
        "#pragma once\n"
        "#define GD_IS_CLASS_ENABLED(m_class) is_class_enabled_v<m_class>\n\n"
        '#include "core/disabled_classes.gen.h" // IWYU pragma: keep.\n'
        "#define GDREGISTER_CLASS(m_class) if constexpr (GD_IS_CLASS_ENABLED(m_class)) {}\n"
    )

    def test_class_db_includes_the_profile_only_where_it_is_declared(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_tree(root, {"core/object/class_db.h": self.UPSTREAM_CLASS_DB})
            self.assertTrue(build_profile.scope(root))
            text = (root / "core/object/class_db.h").read_text()
            self.assertIn("#ifdef GODOT_DECLARES_BUILD_PROFILE", text)
            # Without the profile, evaluating a class's state names an undeclared identifier.
            self.assertIn(
                "#define GD_IS_CLASS_ENABLED(m_class) "
                "GODOT_BUILD_PROFILE_NOT_DECLARED_FOR_##m_class",
                text,
            )

    def test_a_fork_that_changed_class_db_keeps_the_profile_everywhere(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            changed = self.UPSTREAM_CLASS_DB.replace("// IWYU pragma: keep.", "")
            write_tree(root, {"core/object/class_db.h": changed})
            self.assertFalse(build_profile.scope(root))
            self.assertEqual((root / "core/object/class_db.h").read_text(), changed)

    def test_only_sources_that_reach_a_registration_see_the_profile(self) -> None:
        files = {
            "core/object/class_db.h": self.UPSTREAM_CLASS_DB,
            "scene/node.cpp": '#include "core/object/class_db.h"\n',
            "scene/register_scene_types.cpp": (
                '#include "core/object/class_db.h"\nGDREGISTER_CLASS(Node);\n'
            ),
            "modules/x/register.cpp": '#include "modules/x/registry.h"\n',
            "modules/x/registry.h": (
                '#include "core/object/class_db.h"\n'
                "#define REGISTER_X(c) if constexpr (GD_IS_CLASS_ENABLED(c)) {}\n"
            ),
            "modules/y/trait.cpp": (
                '#include "core/object/class_db.h"\n'
                "bool y = is_class_enabled<Node>::value;\n"
            ),
            "core/core_bind.cpp": (
                '#include "core/object/class_db.h"\n'
                "bool f() { return ::ClassDB::is_class_enabled(name); }\n"
            ),
            "core/version.cpp": '#include "core/version_generated.gen.h"\n',
        }
        sources = [
            "scene/node.cpp",
            "scene/register_scene_types.cpp",
            "modules/x/register.cpp",
            "modules/y/trait.cpp",
            "core/core_bind.cpp",
            "core/version.cpp",
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_tree(root, files)
            # One builder file writes both the profile's specializations and the version.
            code = 'f"template <> struct is_class_enabled<{cs}> : std::false_type {{}};"'
            generated = {
                name: Generated(code, (), (name,))
                for name in [build_profile.HEADER, "core/version_generated.gen.h"]
            }
            graph = include_graph(root, [CompileGroup(sources, [], [])], generated)
            self.assertIn(build_profile.HEADER, graph["core/object/class_db.h"])
            graph, users = build_profile.declare(root, graph, generated, sources)
        self.assertEqual(
            users,
            {
                "scene/register_scene_types.cpp",
                "modules/x/register.cpp",
                "modules/y/trait.cpp",
            },
        )
        self.assertNotIn(build_profile.HEADER, graph["core/object/class_db.h"])
        self.assertNotIn(build_profile.HEADER, graph["scene/node.cpp"])
        self.assertIn(build_profile.HEADER, graph["modules/x/register.cpp"])


if __name__ == "__main__":
    unittest.main()
