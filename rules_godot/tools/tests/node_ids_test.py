"""Give scene nodes the stable unique_id Godot 4.7 exports instead of a random one."""

import unittest

from tools.node_ids import missing_node_ids, node_id, with_node_ids

# Headers as Godot 4.7 writes them, with its own IDs removed.
_SCENE = """[gd_scene format=3]

[ext_resource type="PackedScene" path="res://base.tscn" id="1"]

[node name="Main" type="Node"]

[node name="Inst" parent="." instance=ExtResource("1")]

[node name="Child" parent="Inst" index="0"]
position = Vector2(3, 4)

[node name="Extra" type="Node2D" parent="Inst/Child" index="1" groups=["h"]]

[connection signal="ready" from="." to="Inst" method="go"]

[editable path="Inst"]
"""


class NodeIdTest(unittest.TestCase):
    def test_declared_nodes_get_ids_where_godot_writes_them(self) -> None:
        main = node_id("main.tscn", ".", set())
        inst = node_id("main.tscn", "Inst", {main})
        extra = node_id("main.tscn", "Inst/Child/Extra", {main, inst})
        self.assertEqual(
            _SCENE.replace(
                '[node name="Main" type="Node"]',
                f'[node name="Main" type="Node" unique_id={main}]',
            )
            .replace(
                '[node name="Inst" parent="." instance=',
                f'[node name="Inst" parent="." unique_id={inst} instance=',
            )
            .replace(
                'index="1" groups=["h"]]',
                f'index="1" unique_id={extra} groups=["h"]]',
            ),
            with_node_ids(_SCENE, "main.tscn"),
        )

    def test_overrides_of_instanced_nodes_keep_their_base_ids(self) -> None:
        self.assertEqual(["Main", "Inst", "Inst/Child/Extra"], missing_node_ids(_SCENE))
        self.assertIn(
            '[node name="Child" parent="Inst" index="0"]\n',
            with_node_ids(_SCENE, "main.tscn"),
        )

    def test_complete_scenes_are_unchanged(self) -> None:
        complete = with_node_ids(_SCENE, "main.tscn")
        self.assertEqual([], missing_node_ids(complete))
        self.assertEqual(complete, with_node_ids(complete, "other.tscn"))

    def test_ids_follow_scene_and_node_path(self) -> None:
        self.assertEqual(with_node_ids(_SCENE, "a.tscn"), with_node_ids(_SCENE, "a.tscn"))
        self.assertNotEqual(
            with_node_ids(_SCENE, "a.tscn"), with_node_ids(_SCENE, "b.tscn")
        )
        identity = node_id("a.tscn", "Node", set())
        self.assertTrue(0 < identity < 2**31)

    def test_existing_ids_are_kept_and_never_repeated(self) -> None:
        taken = node_id("main.tscn", ".", set())
        scene = (
            '[gd_scene format=3]\n\n[node name="Main" type="Node"]\n\n'
            f'[node name="Kept" type="Node" parent="." unique_id={taken}]\n'
        )
        updated = with_node_ids(scene, "main.tscn")
        self.assertIn(f'parent="." unique_id={taken}]', updated)
        self.assertNotIn(f'type="Node" unique_id={taken}]\n\n[node name="Kept"', updated)
        self.assertEqual([], missing_node_ids(updated))

    def test_quoted_values_may_contain_brackets_and_quotes(self) -> None:
        scene = '[node name="A \\"[x]\\"" type="Node" groups=["a]", "b"]]\n'
        updated = with_node_ids(scene, "q.tscn")
        identity = node_id("q.tscn", ".", set())
        self.assertEqual(
            f'[node name="A \\"[x]\\"" type="Node" unique_id={identity} groups=["a]", "b"]]\n',
            updated,
        )

    def test_placeholders_and_inherited_roots_are_declared(self) -> None:
        scene = (
            '[node name="Base" instance=ExtResource("1")]\n'
            '[node name="Later" parent="." instance_placeholder="res://later.tscn"]\n'
        )
        self.assertEqual(["Base", "Later"], missing_node_ids(scene))


if __name__ == "__main__":
    unittest.main()
