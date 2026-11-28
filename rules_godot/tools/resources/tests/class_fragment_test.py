"""Class fragments: the headers Godot's scan reads, merged into Godot's class cache."""

import os
import unittest
from pathlib import Path

from tools.resources.class_fragment import class_cache, fragment, script_header

_FIXTURE = "godot/private/tests/validation/fixtures/classes"

# What Godot's editor scan writes as .godot/global_script_class_cache.cfg for the fixture
# at res://classes/ (Godot 4.6.3, --headless --editor --quit). The validation tests in
# //godot/private/tests/validation compare the merge with the registered editor's own.
EXPECTED = 'list=[{\n"base": &"Node",\n"class": &"Base",\n"icon": "",\n"is_abstract": true,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/base.gd"\n}, {\n"base": &"",\n"class": &"FromInner",\n"icon": "",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/frominner.gd"\n}, {\n"base": &"Base",\n"class": &"FromPath",\n"icon": "",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/frompath.gd"\n}, {\n"base": &"Base",\n"class": &"FromUnnamed",\n"icon": "",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/fromunnamed.gd"\n}, {\n"base": &"Node2D",\n"class": &"Iconic",\n"icon": "res://classes/iconic.svg",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/iconic.gd"\n}, {\n"base": &"Base",\n"class": &"Mid",\n"icon": "",\n"is_abstract": false,\n"is_tool": true,\n"language": &"GDScript",\n"path": "res://classes/mid.gd"\n}, {\n"base": &"RefCounted",\n"class": &"NoExtChain",\n"icon": "",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/noext.gd"\n}, {\n"base": &"Node",\n"class": &"PathInner",\n"icon": "",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/pathinner.gd"\n}, {\n"base": &"RefCounted",\n"class": &"Plain",\n"icon": "",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/plain.gd"\n}, {\n"base": &"",\n"class": &"Rel",\n"icon": "",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/rel.gd"\n}, {\n"base": &"Node",\n"class": &"ToolAbs",\n"icon": "",\n"is_abstract": true,\n"is_tool": true,\n"language": &"GDScript",\n"path": "res://classes/toolabs.gd"\n}, {\n"base": &"RefCounted",\n"class": &"WithInner",\n"icon": "",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/inner.gd"\n}]\n'


def fixture() -> dict[str, str]:
    root = Path(os.environ["TEST_SRCDIR"]) / os.environ["TEST_WORKSPACE"] / _FIXTURE
    return {
        "classes/" + path.name: path.read_text(encoding="utf-8")
        for path in sorted(root.glob("*.gd"))
    }


class ClassFragmentTest(unittest.TestCase):
    def test_merged_fragments_equal_godots_cache(self) -> None:
        scripts = fixture()
        # One fragment per script, as units of one script each would write them.
        fragments = [fragment({path: text}) for path, text in scripts.items()]
        self.assertEqual(EXPECTED, class_cache(fragments))
        self.assertEqual(EXPECTED, class_cache([fragment(scripts)]))

    def test_header_annotations(self) -> None:
        header = script_header(
            "## class_name InDoc\n@tool @abstract class_name One extends Node\n"
            '@abstract func f()\nclass Inner extends "res://other.gd":\n\tpass\n'
        )
        self.assertEqual("One", header["class"])
        self.assertEqual({"path": None, "names": ["Node"]}, header["base"])
        self.assertTrue(header["is_tool"])
        self.assertTrue(header["is_abstract"])
        self.assertEqual(
            {"Inner": {"path": "res://other.gd", "names": []}}, header["inner"]
        )

    def test_annotation_arguments_may_nest_brackets(self) -> None:
        header = script_header(
            '@icon("res://i.svg")\n@warning_ignore(("unused"))\n@tool\nclass_name C\n'
        )
        self.assertEqual("res://i.svg", header["icon"])
        self.assertTrue(header["is_tool"])
        self.assertEqual("C", header["class"])

    def test_brackets_in_annotation_strings_nest_nothing(self) -> None:
        header = script_header(
            'class_name C\n@export_placeholder("(") var p := ""\n'
            "class Inner extends Node:\n\tpass\n"
        )
        self.assertEqual({"Inner": {"path": None, "names": ["Node"]}}, header["inner"])

    def test_an_icon_may_end_in_a_comma(self) -> None:
        header = script_header('@icon(\n\t"res://i.svg",\n)\nclass_name C\n')
        self.assertEqual("res://i.svg", header["icon"])

    def test_an_icon_without_a_single_closed_string_records_none(self) -> None:
        # Godot 4.7's editor scan records the class and no icon for these.
        for icon in [
            "@icon(",
            '@icon("res://i.svg"',
            '@icon("res://a.svg", "res://b.svg")',
            '@icon(&"res://i.svg")',
        ]:
            with self.subTest(icon):
                header = script_header("class_name C\n" + icon)
                self.assertEqual("", header["icon"])
                self.assertEqual("C", header["class"])

    def test_member_annotations_leave_the_class(self) -> None:
        header = script_header("extends Node\n@abstract func f()\n")
        self.assertFalse(header["is_abstract"])
        self.assertEqual("", header["class"])

    def test_a_base_outside_the_closure_records_none(self) -> None:
        cache = class_cache(
            [fragment({"a.gd": 'class_name A\nextends "res://missing.gd"\n'})]
        )
        self.assertIn('"base": &"",\n"class": &"A"', cache)
        self.assertEqual("list=[]\n", class_cache([fragment({"b.gd": "extends Node\n"})]))

    def test_copies_without_tool_annotations_record_no_tool_scripts(self) -> None:
        scripts = fixture()
        self.assertIn('"is_tool": true', class_cache([fragment(scripts)]))
        self.assertEqual(
            EXPECTED.replace('"is_tool": true', '"is_tool": false'),
            class_cache([fragment(scripts)], tool_annotations=False),
        )


if __name__ == "__main__":
    unittest.main()
