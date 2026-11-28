"""Unit interfaces: what dependents read stays, function bodies and asset data leave."""

import tempfile
import unittest
from pathlib import Path

from tools.inputs.originals import read_original
from tools.resources.files import import_base
from tools.validation.unit_interface import (
    AssetInterface,
    asset_interface,
    interface_files,
    script_interface,
)

BASE = """class_name Base
extends Node
## Docs.

signal hit(amount: int)
enum Kind { A, B }
const SPEED := 3.5
const Scene = preload("res://scene.tscn")
static var counter := 0
var inferred := make_value()
@onready var label := $Label as Label
var prop: int:
	get: return counter
	set(value): counter = value
var callback := func(x: int) -> int:
	return x + 1


func make_value() -> Vector2:
	var x := Vector2.ZERO
	return x


func wait() -> int:
	await get_tree().process_frame
	return 1


func wait_untyped():
	await get_tree().process_frame


func lambda_waits() -> String:
	var f := func(): await get_tree().process_frame
	return "x"


static func make(
	n: int,
	s := "a",
) -> Base:
	return null


func untyped(a, b):
	return a if b else null


func one_line() -> int: return 3


@abstract func declared() -> int


class Inner:
	extends RefCounted
	var v := 2

	func get_v() -> int:
		return v

	class Deeper:
		func deep():
			await Engine.get_main_loop().process_frame
"""

EXPECTED = """@warning_ignore_start("unused_parameter", "unused_private_class_variable", "unused_signal")
class_name Base
extends Node
## Docs.

signal hit(amount: int)
enum Kind { A, B }
const SPEED := 3.5
const Scene = preload("res://scene.tscn")
static var counter := 0
var inferred := make_value()
@onready var label := $Label as Label
var prop: int:
	get: return counter
	set(value): counter = value
var callback := func(x: int) -> int:
	return x + 1


func make_value() -> Vector2: return Engine.get_meta(&"")


func wait() -> int: return await Engine.get_meta(&"")


func wait_untyped(): await Engine.get_meta(&"")


func lambda_waits() -> String:
	var f := func(): await get_tree().process_frame
	return "x"


static func make(
	n: int,
	s := "a",
) -> Base: return Engine.get_meta(&"")


func untyped(a, b): pass


func one_line() -> int: return Engine.get_meta(&"")


@abstract func declared() -> int


class Inner:
	extends RefCounted
	var v := 2

	func get_v() -> int: return Engine.get_meta(&"")

	class Deeper:
		func deep(): await Engine.get_meta(&"")
"""

TEXTURE_IMPORT = """[remap]

importer="texture"
type="CompressedTexture2D"
uid="uid://bh4dk6iumym0v"
path="res://.godot/imported/icon.png-487276ed.ctex"
metadata={
"vram_texture": false
}

[deps]

source_file="res://art/icon.png"
dest_files=["res://.godot/imported/icon.png-487276ed.ctex"]

[params]

compress/mode=0
"""


def _stubs(source: str) -> str:
    """The script interface of source without its first line, @warning_ignore_start."""
    return script_interface(source).split("\n", 1)[1]


class ScriptInterfaceTest(unittest.TestCase):
    def test_bodies_leave_and_declarations_stay(self) -> None:
        self.assertEqual(EXPECTED, script_interface(BASE))

    def test_a_body_edit_keeps_the_interface(self) -> None:
        edited = BASE.replace("var x := Vector2.ZERO", "var x := Vector2.ONE * 2")
        self.assertEqual(script_interface(BASE), script_interface(edited))

    def test_a_signature_edit_changes_the_interface(self) -> None:
        edited = BASE.replace("func one_line() -> int:", "func one_line() -> float:")
        self.assertNotEqual(script_interface(BASE), script_interface(edited))

    def test_an_await_makes_the_stub_a_coroutine(self) -> None:
        plain = "func f() -> int:\n\treturn 1\n"
        waiting = "func f() -> int:\n\tawait g()\n\treturn 1\n"
        self.assertNotEqual(script_interface(plain), script_interface(waiting))
        self.assertIn("return await", script_interface(waiting))

    def test_undecided_bodies_stay(self) -> None:
        for source in [
            # An await in a node path names a node.
            "func f():\n\tprint($await)\n",
            # A restored warning would report again in the stubs.
            (
                '@warning_ignore_start("unused_parameter")\nfunc f(a):\n\tpass\n'
                '@warning_ignore_restore("unused_parameter")\n'
            ),
        ]:
            self.assertEqual(source, script_interface(source))

    def test_a_byte_order_mark_stays_first(self) -> None:
        stub = script_interface("\ufeffextends Node\nfunc f():\n\tprint(1)\n")
        self.assertTrue(stub.startswith("\ufeff@warning_ignore_start("), stub)
        self.assertEqual(1, stub.count("\ufeff"))

    def test_a_lambda_default_has_no_say_in_the_return_type(self) -> None:
        self.assertEqual(
            "func f(cb := func() -> int: return 1): pass\n",
            _stubs("func f(cb := func() -> int: return 1):\n\tcb.call()\n"),
        )
        self.assertEqual(
            'func g(cb := func() -> int: return 1) -> int: return Engine.get_meta(&"")\n',
            _stubs("func g(cb := func() -> int: return 1) -> int:\n\treturn cb.call()\n"),
        )

    def test_a_string_ending_in_a_backslash_joins_no_line(self) -> None:
        self.assertEqual(
            'const SEP = "\\\\"\nfunc f() -> int: return Engine.get_meta(&"")\n',
            _stubs('const SEP = "\\\\"\nfunc f() -> int:\n\treturn 1\n'),
        )

    def test_brackets_in_annotation_strings_nest_nothing(self) -> None:
        self.assertEqual(
            '@warning_ignore("(") func f(): pass\n',
            _stubs('@warning_ignore("(") func f():\n\tprint(1)\n'),
        )

    def test_a_script_without_bodies_stays(self) -> None:
        source = "extends Node\nsignal done\nconst X = 1\n"
        self.assertEqual(source, script_interface(source))


class AssetInterfaceTest(unittest.TestCase):
    def test_a_texture_remaps_to_a_stand_in_of_its_class(self) -> None:
        self.assertEqual(
            AssetInterface(
                '[remap]\n\nimporter="texture"\ntype="CompressedTexture2D"\n'
                'uid="uid://bh4dk6iumym0v"\nmetadata={\n"vram_texture": false\n}\n'
                f'path="res://{import_base("art/icon.png")}interface.tres"\n',
                import_base("art/icon.png") + "interface.tres",
                '[gd_resource type="CompressedTexture2D" format=3]\n\n[resource]\n',
            ),
            asset_interface("art/icon.png", TEXTURE_IMPORT),
        )

    def test_a_scene_stand_in_is_a_scene(self) -> None:
        text = TEXTURE_IMPORT.replace('importer="texture"', 'importer="scene"')
        interface = asset_interface("art/model.glb", text)
        assert interface is not None
        self.assertEqual(
            import_base("art/model.glb") + "interface.tscn", interface.stand_in
        )
        self.assertEqual(
            '[gd_scene format=3]\n\n[node name="Imported" type="Node"]\n',
            interface.content,
        )

    def test_other_importers_are_their_own_interface(self) -> None:
        for importer in ["keep", "my_addon_importer", "texture_atlas"]:
            text = TEXTURE_IMPORT.replace("texture", importer, 1)
            self.assertIsNone(asset_interface("art/icon.png", text), importer)

    def test_unit_files_without_their_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "art").mkdir()
            (root / "art/icon.png").write_bytes(b"\x89PNG pixels")
            (root / "art/icon.png.import").write_text(TEXTURE_IMPORT)
            (root / "art/data.json").write_text("{}")
            (root / "art/data.json.import").write_text('[remap]\n\nimporter="keep"\n')
            (root / "base.gd").write_text(BASE)
            tree = root / "import"
            base = import_base("art/icon.png")
            (tree / ".godot/imported").mkdir(parents=True)
            (tree / "art").mkdir()
            (tree / (base + "ctex")).write_bytes(b"GST2")
            (tree / (base + "md5")).write_text("md5")
            (tree / "art/icon.png.import").write_text(TEXTURE_IMPORT)
            files = {
                path: read_original(original)
                for path, original in interface_files(
                    {"base.gd": root / "base.gd"},
                    {
                        path: root / path
                        for path in [
                            "art/icon.png",
                            "art/icon.png.import",
                            "art/data.json",
                            "art/data.json.import",
                        ]
                    },
                    tree,
                ).items()
            }
        self.assertEqual(
            {
                import_base("art/icon.png") + "interface.tres",
                "art/data.json",
                "art/data.json.import",
                "art/icon.png",
                "art/icon.png.import",
                "base.gd",
            },
            set(files),
        )
        self.assertEqual(b"", files["art/icon.png"])
        self.assertEqual(b"{}", files["art/data.json"])
        self.assertEqual(EXPECTED.encode(), files["base.gd"])


if __name__ == "__main__":
    unittest.main()
