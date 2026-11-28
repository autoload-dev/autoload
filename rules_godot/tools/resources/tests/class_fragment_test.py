"""Class fragments: the headers Godot's scan reads, merged into Godot's class cache."""

import os
import re
import unittest
from pathlib import Path

from tools.resources.class_fragment import class_cache, fragment, script_header

_FIXTURE = "godot/private/tests/validation/fixtures/classes"

# What Godot's editor scan writes as .godot/global_script_class_cache.cfg for the fixture
# at res://classes/ (--headless --editor --quit). Godot 4.6.3 wrote it first, and Godot 4.7.2
# wrote the entries of CommaIcon, DocFirst, FromNested, FromNextLine, Nested,
# NextLine and RelIcon. The validation tests in
# //godot/private/tests/validation compare the merge with the registered editor's own.
EXPECTED = 'list=[{\n"base": &"Node",\n"class": &"Base",\n"icon": "",\n"is_abstract": true,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/base.gd"\n}, {\n"base": &"Node2D",\n"class": &"CommaIcon",\n"icon": "res://classes/iconic.svg",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/commaicon.gd"\n}, {\n"base": &"Node",\n"class": &"DocFirst",\n"icon": "",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/docfirst.gd"\n}, {\n"base": &"",\n"class": &"FromInner",\n"icon": "",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/frominner.gd"\n}, {\n"base": &"Node2D",\n"class": &"FromNested",\n"icon": "",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/fromnested.gd"\n}, {\n"base": &"Node3D",\n"class": &"FromNextLine",\n"icon": "",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/fromnextline.gd"\n}, {\n"base": &"Base",\n"class": &"FromPath",\n"icon": "",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/frompath.gd"\n}, {\n"base": &"Base",\n"class": &"FromUnnamed",\n"icon": "",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/fromunnamed.gd"\n}, {\n"base": &"Node2D",\n"class": &"Iconic",\n"icon": "res://classes/iconic.svg",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/iconic.gd"\n}, {\n"base": &"Base",\n"class": &"Mid",\n"icon": "",\n"is_abstract": false,\n"is_tool": true,\n"language": &"GDScript",\n"path": "res://classes/mid.gd"\n}, {\n"base": &"RefCounted",\n"class": &"Nested",\n"icon": "",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/nested.gd"\n}, {\n"base": &"RefCounted",\n"class": &"NextLine",\n"icon": "",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/nextline.gd"\n}, {\n"base": &"RefCounted",\n"class": &"NoExtChain",\n"icon": "",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/noext.gd"\n}, {\n"base": &"Node",\n"class": &"PathInner",\n"icon": "",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/pathinner.gd"\n}, {\n"base": &"RefCounted",\n"class": &"Plain",\n"icon": "",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/plain.gd"\n}, {\n"base": &"",\n"class": &"Rel",\n"icon": "",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/rel.gd"\n}, {\n"base": &"Node2D",\n"class": &"RelIcon",\n"icon": "res://classes/iconic.svg",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/relicon.gd"\n}, {\n"base": &"Node",\n"class": &"ToolAbs",\n"icon": "",\n"is_abstract": true,\n"is_tool": true,\n"language": &"GDScript",\n"path": "res://classes/toolabs.gd"\n}, {\n"base": &"RefCounted",\n"class": &"WithInner",\n"icon": "",\n"is_abstract": false,\n"is_tool": false,\n"language": &"GDScript",\n"path": "res://classes/inner.gd"\n}]\n'


def fixture() -> dict[str, str]:
    root = Path(os.environ["TEST_SRCDIR"]) / os.environ["TEST_WORKSPACE"] / _FIXTURE
    return {
        "classes/" + path.name: path.read_text(encoding="utf-8")
        for path in sorted(root.glob("*.gd"))
    }


def _inner_bases(header: dict, prefix: str = "") -> dict[str, dict | None]:
    """The bases of a header's inner classes, nested ones by their dotted name."""
    bases = {}
    for name, inner in header["inner"].items():
        bases[prefix + name] = inner["base"]
        bases |= _inner_bases(inner, prefix + name + ".")
    return bases


def _cache_bases(scripts: dict[str, str]) -> dict[str, str]:
    """The base of each named class that Godot's cache records for the scripts."""
    cache = class_cache([fragment(scripts)])
    entries = re.findall(r'"base": &"([^"]*)",\n"class": &"([^"]*)"', cache)
    return {name: base for base, name in entries}


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
            {"Inner": {"path": "res://other.gd", "names": []}}, _inner_bases(header)
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
        self.assertEqual(
            {"Inner": {"path": None, "names": ["Node"]}}, _inner_bases(header)
        )

    def test_an_inner_class_may_extend_on_its_next_line(self) -> None:
        header = script_header("class Inner:\n\textends Node\n")
        self.assertEqual(
            {"Inner": {"path": None, "names": ["Node"]}}, _inner_bases(header)
        )

    def test_a_string_starts_no_annotation(self) -> None:
        header = script_header('"@"\nicon("res://i.svg")\n')
        self.assertEqual("", header["icon"])

    def test_a_nested_class_is_no_inner_class_of_the_script(self) -> None:
        header = script_header(
            "class A:\n\tclass B extends Node2D:\n\t\tpass\nclass B extends Node3D:\n\tpass\n"
        )
        self.assertEqual(
            {
                "A": None,
                "A.B": {"path": None, "names": ["Node2D"]},
                "B": {"path": None, "names": ["Node3D"]},
            },
            _inner_bases(header),
        )

    def test_a_string_names_no_inner_class(self) -> None:
        header = script_header('class_name C\nfunc f(s):\n\tif "class" in s:\n\t\tpass\n')
        self.assertEqual({}, _inner_bases(header))

    def test_an_icon_may_end_in_a_comma(self) -> None:
        header = script_header('@icon(\n\t"res://i.svg",\n)\nclass_name C\n')
        self.assertEqual("res://i.svg", header["icon"])

    def test_an_icon_other_than_one_string_records_none(self) -> None:
        # Godot 4.7's editor scan records the class and no icon for these.
        for icon in [
            "@icon(",
            '@icon("res://a.svg", "res://b.svg")',
            '@icon(&"res://i.svg")',
            '@icon("res://" + "i.svg")',
            "@icon(ICON)",
        ]:
            with self.subTest(icon):
                header = script_header(
                    icon + '\nclass_name C\nconst ICON = "res://i.svg"\n'
                )
                self.assertEqual("", header["icon"])
                self.assertEqual("C", header["class"])

    def test_godot_reads_on_after_an_unclosed_annotation(self) -> None:
        header = script_header('@icon("res://i.svg"\nclass_name C\n')
        self.assertEqual(("C", "res://i.svg"), (header["class"], header["icon"]))
        header = script_header("@tool(\nclass_name C extends Node\n")
        self.assertFalse(header["is_tool"])
        self.assertEqual({"path": None, "names": ["Node"]}, header["base"])

    def test_the_first_icon_counts(self) -> None:
        header = script_header(
            '@icon("res://a.svg")\n@icon("res://b.svg")\nclass_name C\n'
        )
        self.assertEqual("res://a.svg", header["icon"])

    def test_an_icon_path_resolves_against_the_script(self) -> None:
        for icon, expected in [
            ("icon.svg", "res://sub/icon.svg"),
            ("../up.svg", "res://up.svg"),
            ("../../out.svg", "res://../out.svg"),
            ("res://sub/../a//b.svg", "res://a/b.svg"),
            ("/abs.svg", "/abs.svg"),
            ("user://u.svg", "user://u.svg"),
        ]:
            with self.subTest(icon):
                script = f'@icon("{icon}")\nclass_name C\n'
                self.assertEqual(expected, fragment({"sub/c.gd": script})[0]["icon"])

    def test_annotations_after_the_declaration_end_the_header(self) -> None:
        header = script_header('class_name C\n@icon("res://i.svg")\n')
        self.assertEqual("", header["icon"])
        header = script_header("class_name C\n@abstract\nextends Node\n")
        self.assertFalse(header["is_abstract"])
        self.assertIsNone(header["base"])

    def test_strings_in_the_header_are_skipped(self) -> None:
        header = script_header('"""Doc."""\nclass_name C extends Node\n')
        self.assertEqual("C", header["class"])
        header = script_header('class_name C\n"""Doc."""\nextends Node\n')
        self.assertEqual({"path": None, "names": ["Node"]}, header["base"])
        header = script_header('@tool\n"""Doc."""\n@abstract\nclass_name C\n')
        self.assertTrue(header["is_tool"] and header["is_abstract"])

    def test_a_base_may_name_a_nested_inner_class(self) -> None:
        outer = "class A:\n\tclass B extends Node2D:\n\t\tpass\n"
        bases = _cache_bases(
            {
                "outer.gd": outer,
                "chain.gd": 'class_name Chain extends "res://outer.gd".A.B\n',
                "missing.gd": 'class_name Missing extends "res://outer.gd".A.C\n',
                "plain.gd": 'class_name Plain extends "res://outer.gd".A\n',
            }
        )
        self.assertEqual({"Chain": "Node2D", "Missing": "", "Plain": "RefCounted"}, bases)

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
