"""Small files expose scanner boundaries without requiring a Godot installation."""

import contextlib
import io
import itertools
import json
import tempfile
import unittest
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from tools.pack import selection as pack_selection
from tools.pack.selection import SelectionError, select_pack
from tools.resource_graph.command import main
from tools.resource_graph.graph import build_graph, require_declared
from tools.resource_graph.query import query_graph
from tools.resources.text import validate_identities


def runtime(source: str, target: str) -> dict:
    """A runtime_references entry of the game's target."""
    return {"source": source, "target": target, "kind": "runtime", "owner": "//:game"}


class GraphFixture(unittest.TestCase):
    """Declared files in a temporary project directory."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.files = {}

    def source(self, path: str, text: str = "") -> None:
        source = self.root / path
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(text, encoding="utf-8")
        self.files[path] = path

    def graph(self, **kwargs: object) -> dict:
        return build_graph(dict(member_resource_paths=self.files, **kwargs), self.root)

    def scan_manifest(self) -> Path:
        """The declared files as a godot_project scan manifest."""
        manifest = self.root / "manifest.jsonl"
        manifest.write_text(
            "".join(
                json.dumps(["member", path, source, "//:game"]) + "\n"
                for path, source in self.files.items()
            ),
            encoding="utf-8",
        )
        return manifest


class ResourceGraphTest(GraphFixture):
    def codes(self, graph: dict) -> list[str]:
        return [item["code"] for item in graph["diagnostics"]]

    def test_a_reference_to_an_unused_addon_names_the_addon(self) -> None:
        # FR-026: content refers to an add-on's file and global class while its resources
        # use no such add-on; the add-on's own files and a declared use are no finding.
        self.source(
            "main/main.tscn",
            '[gd_scene format=3]\n[ext_resource type="Script" path="res://addons/inventory/inventory.gd" id="1"]\n[node name="Main" type="Node"]\nscript = ExtResource("1")\n',
        )
        self.source("main/shop.gd", "extends Node\nvar slots := InventorySlots.new()\n")
        self.source("addons/inventory/inventory.gd", "extends Node\n")
        self.source(
            "addons/inventory/slots.gd",
            'class_name InventorySlots\nextends RefCounted\nvar owner_script := preload("res://addons/inventory/inventory.gd")\n',
        )
        owners = {
            "main/main.tscn": "//game:main",
            "main/shop.gd": "//game:main",
            "addons/inventory/inventory.gd": "//addons:inventory",
            "addons/inventory/slots.gd": "//addons:inventory",
        }
        graph = self.graph(
            member_owners=owners,
            addons={"//addons:inventory": ["//addons:inventory"]},
            addon_uses={"//game:main": []},
        )
        findings = [
            item
            for item in graph["diagnostics"]
            if item["code"] == "undeclared_addon_use"
        ]
        self.assertEqual(
            ["res://main/main.tscn", "res://main/shop.gd"],
            [item["path"] for item in findings],
        )
        self.assertIn("of the add-on //addons:inventory", findings[0]["message"])
        self.assertIn("in the deps of //game:main", findings[0]["message"])
        self.assertEqual({"warning"}, {item["severity"] for item in findings})
        self.assertEqual(
            {"error"},
            {
                item["severity"]
                for item in require_declared(graph)["diagnostics"]
                if item["code"] == "undeclared_addon_use"
            },
        )
        graph = self.graph(
            member_owners=owners,
            addons={"//addons:inventory": ["//addons:inventory"]},
            addon_uses={"//game:main": ["//addons:inventory"]},
        )
        self.assertNotIn("undeclared_addon_use", self.codes(graph))

    def test_scene_uid_resolution_and_local_ids_have_distinct_namespaces(self) -> None:
        self.source(
            "scene.tscn",
            '[gd_scene format=3 uid="uid://scene"]\n[ext_resource type="Resource" path="old.tres" uid="uid://resource" id="shared"]\n[sub_resource type="Resource" id="shared"]\n',
        )
        self.source("moved.tres", '[gd_resource type="Resource" uid="uid://resource"]\n')
        graph = self.graph()
        self.assertEqual([], graph["diagnostics"])
        self.assertEqual("res://moved.tres", graph["edges"][0]["target"])
        self.assertEqual(
            ["res://moved.tres", "res://scene.tscn"],
            query_graph(graph, ["uid://scene"])["paths"],
        )

    def test_cycles_and_shortest_explanations(self) -> None:
        self.source("a.gd", 'const B = preload("b.gd")\n')
        self.source("b.gd", 'var a = load("res://a.gd")\n')
        self.source("other.gd")
        graph = self.graph()
        self.assertEqual([], graph["diagnostics"])
        self.assertEqual(
            ["res://a.gd", "res://b.gd"], query_graph(graph, ["a.gd"])["paths"]
        )
        self.assertEqual(
            ["res://b.gd", "res://a.gd"],
            query_graph(graph, ["b.gd"], reverse=True)["chains"]["res://a.gd"],
        )

    def test_binary_resource_alone_marks_coverage_incomplete_without_inventing_missing_refs(
        self,
    ) -> None:
        self.source("opaque.res", "binary resource placeholder")
        graph = self.graph()
        self.assertFalse(graph["complete"])
        self.assertEqual(
            [("binary_resource", "unknown")],
            [(edge["kind"], edge["status"]) for edge in graph["edges"]],
        )
        self.assertEqual(
            ["dynamic_reference", "unsupported_reference_format"], self.codes(graph)
        )
        self.assertTrue(
            all(item["severity"] == "warning" for item in graph["diagnostics"])
        )
        self.assertEqual("unsupported", graph["nodes"][0]["analysis"])
        self.assertEqual(["res://opaque.res"], graph["coverage"]["unsupported"])
        self.assertFalse(query_graph(graph, ["opaque.res"])["complete"])

    def test_unscanned_format_coverage_is_explicit_and_manual_edges_remain_usable(
        self,
    ) -> None:
        for name in (
            "scene.scn",
            "model.glb",
            "model.obj",
            "model.fbx",
            "model.blend",
            "addon.gdextension",
            "plugin.cfg",
            "data.custom",
            "data.json",
        ):
            self.source(name)
        self.source("main.gd", "extends Node\n")
        self.source("texture.png", "pixels")
        self.source("data.bin", "buffer")
        graph = self.graph(
            relationships=[
                {"source": "scene.scn", "target": "texture.png", "kind": "runtime"}
            ]
        )
        self.assertFalse(graph["complete"])
        self.assertEqual(9, len(graph["coverage"]["unsupported"]))
        self.assertEqual(["res://main.gd"], graph["coverage"]["analyzed"])
        self.assertEqual(
            ["res://data.bin", "res://texture.png"], graph["coverage"]["leaf"]
        )
        self.assertEqual(
            ["res://scene.scn", "res://texture.png"],
            query_graph(graph, ["scene.scn"])["paths"],
        )
        self.assertTrue(
            all(item["severity"] == "warning" for item in graph["diagnostics"])
        )
        self.assertFalse(graph["coverage_policy"]["custom_loaders_analyzed"])

    def test_gdscript_lexer_excludes_comments_strings_and_custom_methods(self) -> None:
        self.source(
            "sub/main.gd",
            '''# preload("res://missing-comment")
const EXAMPLE = "load('res://missing-example')"
const MULTILINE = """preload("res://missing-multiline")"""
func load(value): pass
func run():
    object.load("res://missing-custom")
    var resource = ResourceLoader.load(r"asset.tres")
    var other = preload(
        "res://asset.tres"
    )
''',
        )
        self.source("asset.tres", "[gd_resource]\n")
        graph = self.graph()
        self.assertEqual([], graph["diagnostics"])
        self.assertEqual(2, len(graph["edges"]))
        self.assertTrue(
            all(edge["target"] == "res://asset.tres" for edge in graph["edges"])
        )

    def test_runtime_loads_are_project_relative_but_preloads_are_script_relative(
        self,
    ) -> None:
        self.source("asset.tres", "[gd_resource]\n")
        self.source("sub/asset.tres", "[gd_resource]\n")
        self.source(
            "sub/main.gd",
            """const ITEM = preload("asset.tres")
func run():
    load("asset.tres")
    ResourceLoader.load("asset.tres")
    ResourceLoader.load_threaded_request("asset.tres")
""",
        )
        graph = self.graph()
        self.assertEqual([], graph["diagnostics"])
        self.assertEqual(
            ["res://sub/asset.tres"],
            [edge["target"] for edge in graph["edges"] if edge["kind"] == "preload"],
        )
        self.assertEqual(
            ["res://asset.tres"] * 3,
            [edge["target"] for edge in graph["edges"] if edge["kind"] == "load"],
        )
        self.assertEqual(
            ["res://asset.tres", "res://sub/main.gd"],
            query_graph(graph, ["asset.tres"], reverse=True)["paths"],
        )

    def test_a_constant_with_a_literal_value_names_what_a_script_loads(self) -> None:
        self.source(
            "main.gd",
            'const ASSET := "res://asset.tres"\n'
            'const BUILT = "res://" + "other.tres"\n'
            "func run():\n    load(ASSET)\n    load(BUILT)\n",
        )
        self.source("asset.tres", "[gd_resource]\n")
        graph = self.graph()
        self.assertEqual(["dynamic_reference"], self.codes(graph))
        self.assertEqual(
            ["res://asset.tres", "res://main.gd"],
            query_graph(graph, ["main.gd"])["paths"],
        )

    def test_a_continued_or_repeated_constant_names_nothing(self) -> None:
        self.source(
            "main.gd",
            'const CONTINUED = "res://" \\\n    + "asset.tres"\n'
            'const TWICE = "res://asset.tres"\n'
            "class Inner:\n"
            '    const TWICE = "res://other.tres"\n'
            "func run():\n    load(CONTINUED)\n    load(TWICE)\n",
        )
        self.source("asset.tres", "[gd_resource]\n")
        graph = self.graph()
        self.assertEqual(["dynamic_reference", "dynamic_reference"], self.codes(graph))

    def test_dynamic_references_are_unknown_even_with_manual_declarations(self) -> None:
        self.source(
            "main.gd", 'func run(path):\n    load(path)\n    load("res://" + path)\n'
        )
        self.source("asset.tres", "[gd_resource]\n")
        graph = self.graph(
            relationships=[
                {"source": "main.gd", "target": "asset.tres", "kind": "runtime"}
            ]
        )
        self.assertFalse(graph["complete"])
        self.assertEqual(["dynamic_reference", "dynamic_reference"], self.codes(graph))
        self.assertEqual(
            ["res://asset.tres", "res://main.gd"],
            query_graph(graph, ["main.gd"])["paths"],
        )

    def test_duplicate_uid_ownership_only_counts_authored_identities(self) -> None:
        self.source(
            "one.tscn",
            '[gd_scene uid="uid://duplicate"]\n[ext_resource uid="uid://duplicate" path="two.tres" id="1"]\n',
        )
        self.source("two.tres", '[gd_resource uid="uid://duplicate"]\n')
        graph = self.graph()
        self.assertIn("duplicate_uid", self.codes(graph))
        self.assertIn("ambiguous_uid_reference", self.codes(graph))
        with self.assertRaisesRegex(ValueError, "Duplicate authored resource UID"):
            validate_identities({path: self.root / path for path in self.files})
        self.source("two.tres", '[gd_resource uid="uid://different"]\n')
        validate_identities({path: self.root / path for path in self.files})
        self.assertIn("uid_path_conflict", self.codes(self.graph()))

    def test_metadata_index_corrections_resolve_conflicts_unless_required(self) -> None:
        # main.tscn names a.gd by path but b.gd's UID; the build points it at a.gd.
        self.source(
            "main.tscn",
            '[gd_scene format=3]\n[ext_resource type="Script" uid="uid://bbb" path="res://a.gd" id="1"]\n',
        )
        for path, uid in [("a.gd", "uid://aaa"), ("b.gd", "uid://bbb")]:
            self.source(path, "extends Node\n")
            self.source(path + ".uid", uid + "\n")
        index = self.root / "index.json"
        index.write_text(
            json.dumps(
                {
                    "uids": {"a.gd": "uid://aaa", "b.gd": "uid://bbb"},
                    "resource_uids": {
                        "main.tscn": {"uids": {"a.gd": "uid://aaa"}, "issues": []}
                    },
                }
            )
        )

        def conflict(graph: dict) -> list[tuple[str, str]]:
            return [
                (item["code"], item["severity"])
                for item in graph["diagnostics"]
                if item["code"] == "uid_path_conflict"
            ]

        def edge(graph: dict) -> tuple[str, str]:
            return next(
                (e["target"], e["status"])
                for e in graph["edges"]
                if e["source"] == "res://main.tscn"
            )

        self.assertEqual([("uid_path_conflict", "error")], conflict(self.graph()))
        for corrects, severity, resolved in [
            (True, "warning", ("res://a.gd", "resolved")),
            (False, "error", ("res://b.gd", "conflict")),
        ]:
            with self.subTest(corrects=corrects):
                graph = self.graph(
                    metadata_index={"path": str(index), "corrects": corrects}
                )
                self.assertEqual([("uid_path_conflict", severity)], conflict(graph))
                self.assertEqual(resolved, edge(graph))

    def test_metadata_index_uids_identify_files_without_authored_ones(self) -> None:
        # icon.png's UID exists only in a generated .import file.
        self.source("main.gd", 'const ICON = preload("uid://icon")\n')
        self.source("icon.png", "")
        index = self.root / "index.json"
        index.write_text(
            json.dumps({"uids": {"icon.png": "uid://icon"}, "resource_uids": {}})
        )
        self.assertIn("missing_reference", self.codes(self.graph()))
        graph = self.graph(metadata_index={"path": str(index), "corrects": True})
        self.assertNotIn("missing_reference", self.codes(graph))
        self.assertIn("res://icon.png", [edge["target"] for edge in graph["edges"]])

    def test_script_and_import_sidecars_resolve_uid_references(self) -> None:
        self.source(
            "main.gd", 'extends "uid://parent"\nconst IMAGE = preload("uid://image")\n'
        )
        self.source("parent.gd", "extends Node\n")
        self.source("parent.gd.uid", "uid://parent\n")
        self.source("image.png", "pretend pixels")
        self.source("image.png.import", '[remap]\nuid="uid://image"\n')
        graph = self.graph()
        self.assertEqual([], graph["diagnostics"])
        self.assertEqual(
            {"res://parent.gd", "res://image.png"},
            {edge["target"] for edge in graph["edges"] if edge["origin"] == "inferred"},
        )

    def test_authored_sidecars_affect_their_resources_and_consumers(self) -> None:
        self.source(
            "main.gd",
            'const PARENT = preload("uid://parent")\nconst IMAGE = preload("uid://image")\n',
        )
        self.source("parent.gd", "extends Node\n")
        self.source("parent.gd.uid", "uid://parent\n")
        self.source("image.png", "pretend pixels")
        self.source("image.png.import", '[remap]\nuid="uid://image"\n')
        graph = self.graph(
            require_declared=True,
            relationships=[
                {"source": "main.gd", "target": "parent.gd", "kind": "runtime"},
                {"source": "main.gd", "target": "image.png", "kind": "runtime"},
            ],
        )
        self.assertEqual([], graph["diagnostics"])
        self.assertTrue(graph["complete"])
        self.assertEqual(
            ["res://main.gd", "res://parent.gd", "res://parent.gd.uid"],
            query_graph(graph, ["parent.gd.uid"], reverse=True)["paths"],
        )
        self.assertEqual(
            ["res://image.png", "res://image.png.import", "res://main.gd"],
            query_graph(graph, ["image.png.import"], reverse=True)["paths"],
        )
        self.assertEqual(
            sorted("res://" + path for path in self.files),
            query_graph(graph, ["main.gd"])["paths"],
        )
        structural = [edge for edge in graph["edges"] if edge["origin"] == "structural"]
        self.assertEqual(
            {"import", "metadata"}, {edge["dependency_kind"] for edge in structural}
        )
        self.assertTrue(all(not edge["declared"] for edge in structural))

    def test_conflicting_uid_sidecar_and_header_are_rejected(self) -> None:
        self.source("one.tres", '[gd_resource uid="uid://one"]\n')
        self.source("one.tres.uid", "uid://two\n")
        self.assertEqual(["conflicting_uids"], self.codes(self.graph()))
        with self.assertRaisesRegex(ValueError, "Conflicting authored resource UIDs"):
            validate_identities({path: self.root / path for path in self.files})

    def test_group_membership_relationship_is_preserved_without_fake_file_edges(
        self,
    ) -> None:
        self.source("asset.tres", "[gd_resource]\n")
        relationship = {
            "source": "",
            "target": "asset.tres",
            "kind": "runtime",
            "owner": "//:assets",
        }
        graph = self.graph(relationships=[relationship])
        self.assertEqual([], graph["diagnostics"])
        self.assertEqual([], graph["edges"])
        self.assertEqual([relationship], graph["relationships"])

    def test_import_input_resolves_gltf_without_adding_runtime_membership(
        self,
    ) -> None:
        self.source("model.gltf", '{"buffers":[{"uri":"data.bin"}]}')
        self.source("data.bin", "bytes")
        del self.files["data.bin"]
        graph = self.graph(
            import_resource_paths={"data.bin": "data.bin"}, require_declared=True
        )
        self.assertEqual([], graph["diagnostics"])
        self.assertEqual("import", graph["edges"][0]["dependency_kind"])
        by_path = {node["path"]: node for node in graph["nodes"]}
        self.assertFalse(by_path["res://data.bin"]["membership"])
        self.assertTrue(by_path["res://model.gltf"]["membership"])
        self.source("main.gd", 'load("data.bin")\n')
        graph = self.graph(import_resource_paths={"data.bin": "data.bin"})
        self.assertEqual(["unavailable_runtime_reference"], self.codes(graph))

    def test_runtime_declaration_requires_available_source_and_destination(
        self,
    ) -> None:
        self.source("asset.tres", "[gd_resource]\n")
        graph = self.graph(
            relationships=[
                {"source": "absent.gd", "target": "asset.tres", "kind": "runtime"}
            ]
        )
        self.assertEqual(["missing_declared_source"], self.codes(graph))
        self.assertEqual("invalid_source", graph["edges"][0]["status"])

    def test_missing_conflicting_and_escaping_references(self) -> None:
        self.source("main.gd", 'load("res://missing.tres")\nload("../outside.tres")\n')
        self.source("A.tres", "[gd_resource]\n")
        self.source("a.tres", "[gd_resource]\n")
        graph = self.graph()
        self.assertCountEqual(
            ["case_collision", "missing_reference", "invalid_reference"],
            self.codes(graph),
        )

    def test_declared_runtime_validation_does_not_use_import_or_membership_edges(
        self,
    ) -> None:
        self.source("main.gd", 'load("asset.tres")\n')
        self.source("asset.tres", "[gd_resource]\n")
        graph = self.graph(
            require_declared=True,
            relationships=[
                {"source": "main.gd", "target": "asset.tres", "kind": "import"}
            ],
        )
        self.assertEqual(["undeclared_reference"], self.codes(graph))
        graph = self.graph(
            require_declared=True,
            relationships=[
                {"source": "main.gd", "target": "asset.tres", "kind": "runtime"}
            ],
        )
        self.assertEqual([], graph["diagnostics"])
        graph = self.graph(
            relationships=[
                {"source": "absent.gd", "target": "missing.tres", "kind": "runtime"}
            ]
        )
        self.assertCountEqual(
            ["missing_declared_source", "missing_reference"], self.codes(graph)
        )

    def test_shader_gltf_and_global_script_classes(self) -> None:
        self.source("main.gd", "extends Parent\nvar x: Parent\n")
        self.source("parent.gd", "class_name Parent\nextends Node\n")
        self.source(
            "shaders/main.gdshader",
            '// #include "absent"\n/* #include "absent" */\n#include "shared.gdshaderinc"\n',
        )
        self.source("shaders/shared.gdshaderinc", "vec3 helper() { return vec3(0.0); }\n")
        self.source(
            "model.gltf",
            json.dumps(
                {
                    "buffers": [{"uri": "models/data%20space.bin"}],
                    "images": [
                        {"uri": "data:image/png;base64,AAAA"},
                        {"uri": "image.png"},
                    ],
                }
            ),
        )
        self.source("models/data space.bin", "data")
        self.source("image.png", "pixels")
        graph = self.graph()
        self.assertEqual([], graph["diagnostics"])
        self.assertEqual(
            {"script_class", "shader_include", "gltf_buffers", "gltf_images"},
            {edge["kind"] for edge in graph["edges"]},
        )

    def test_duplicate_scene_resource_ids_and_class_names(self) -> None:
        self.source(
            "scene.tscn",
            '[gd_scene]\n[sub_resource type="Resource" id="duplicate"]\n[sub_resource type="Resource" id="duplicate"]\n',
        )
        self.source("one.gd", "class_name Duplicate\n")
        self.source("two.gd", "class_name Duplicate\n")
        self.assertCountEqual(
            ["duplicate_class", "duplicate_local_id"], self.codes(self.graph())
        )

    def test_project_entrypoints_and_configuration_affected_scope(self) -> None:
        self.source(
            "project.godot",
            '[application]\nrun/main_scene="res://main.tscn"\n[autoload]\nSingleton="*res://singleton.gd"\n',
        )
        self.source("main.tscn", "[gd_scene]\n")
        self.source("singleton.gd", "extends Node\n")
        self.source("other.tres", "[gd_resource]\n")
        graph = self.graph()
        self.assertEqual([], graph["diagnostics"])
        self.assertEqual(
            [
                "res://main.tscn",
                "res://other.tres",
                "res://project.godot",
                "res://singleton.gd",
            ],
            query_graph(graph, ["project.godot"], reverse=True)["paths"],
        )
        self.assertEqual(
            ["res://main.tscn", "res://project.godot", "res://singleton.gd"],
            query_graph(graph, ["project.godot"])["paths"],
        )

    def test_project_entrypoints_use_composed_configuration_syntax(self) -> None:
        self.source(
            "project.godot", '[autoload]\n\n"Quoted"="*res://singleton.gd" ; comment\n'
        )
        self.source("singleton.gd", "extends Node\n")
        edge = self.graph()["edges"][0]
        self.assertEqual(
            ("autoload", "res://singleton.gd", 3),
            (edge["kind"], edge["target"], edge["line"]),
        )

    def test_project_settings_name_resources_except_editor_plugins(self) -> None:
        self.source(
            "project.godot",
            '[application]\nconfig/icon="res://icon.png"\n[internationalization]\nlocale/translations=PackedStringArray("res://text.en.translation")\n[editor_plugins]\nenabled=PackedStringArray("res://addons/tool/plugin.cfg")\n',
        )
        self.source("icon.png", "pixels")
        self.source("text.en.translation", "messages")
        graph = self.graph()
        self.assertEqual([], graph["diagnostics"])
        self.assertEqual(
            {
                ("project_setting", "res://icon.png"),
                ("project_setting", "res://text.en.translation"),
            },
            {(edge["kind"], edge["target"]) for edge in graph["edges"]},
        )

    def test_references_resolve_by_kind_file_directory_or_uid(self) -> None:
        self.source(
            "project.godot",
            '[application]\nconfig/icon="res://icon.png"\n'
            'boot/splash="uid://splash"\n'
            '[game]\nmodules="res://modules"\nlevels="res://levels"\n'
            'bundle="res://game.icon/"\nprefix="res://mod"\n',
        )
        # The rows of the path resolution rules, which
        # godot/private/tests/file_roles_tests.bzl asserts for rules.
        self.source("game.icon/Assets/dot.png", "pixels")
        self.source("game.iconography.png", "pixels")
        self.source("icon.png", "pixels")
        self.source("splash.png", "pixels")
        self.source("splash.png.import", '[remap]\nuid="uid://splash"\n')
        self.source("modules/b/module.tscn", "[gd_scene]\n")
        self.source("modules/a/module.tscn", "[gd_scene]\n")
        graph = self.graph()
        edges = {
            edge["reference"]: edge
            for edge in graph["edges"]
            if edge["kind"] == "project_setting"
        }
        self.assertEqual(
            {
                "res://icon.png": ("resolved", "file", "res://icon.png"),
                "uid://splash": ("resolved", "uid", "res://splash.png"),
                "res://modules": ("resolved", "directory", "res://modules"),
                "res://game.icon/": ("resolved", "directory", "res://game.icon"),
                "res://levels": ("missing", None, None),
                "res://mod": ("missing", None, None),
            },
            {
                reference: (edge["status"], edge["target_kind"], edge["target"])
                for reference, edge in edges.items()
            },
        )
        self.assertEqual(
            ["res://modules/a/module.tscn", "res://modules/b/module.tscn"],
            edges["res://modules"]["targets"],
        )
        self.assertEqual(
            ["res://game.icon/Assets/dot.png"], edges["res://game.icon/"]["targets"]
        )
        self.assertNotIn("targets", edges["res://icon.png"])
        self.assertEqual(
            [
                (
                    "missing_reference",
                    "unavailable project_setting reference: "
                    + reference
                    + " (no declared file or directory)",
                )
                for reference in ("res://levels", "res://mod")
            ],
            [(item["code"], item["message"]) for item in graph["diagnostics"]],
        )
        self.assertIn(
            "res://modules/a/module.tscn",
            query_graph(graph, ["res://project.godot"])["paths"],
        )

    def test_only_settings_and_declared_runtime_references_name_directories(
        self,
    ) -> None:
        self.source("main.gd", 'var scene = load("res://levels")\n')
        self.source("levels/one.tscn", "[gd_scene]\n")
        graph = self.graph(
            relationships=[{"source": "main.gd", "target": "levels", "kind": "runtime"}]
        )
        self.assertEqual(
            {("load", "invalid", None), ("runtime", "resolved", "directory")},
            {
                (edge["kind"], edge["status"], edge["target_kind"])
                for edge in graph["edges"]
            },
        )
        self.assertEqual(
            ["load reference names a directory: res://levels"],
            [item["message"] for item in graph["diagnostics"]],
        )

    def test_directory_of_import_inputs_only_is_unavailable_at_runtime(self) -> None:
        self.source("project.godot", '[game]\nmodels="res://models"\n')
        self.source("main.gd", "extends Node\n")
        self.source("models/data.bin", "bytes")
        del self.files["models/data.bin"]
        graph = self.graph(import_resource_paths={"models/data.bin": "models/data.bin"})
        self.assertEqual(["unavailable_runtime_reference"], self.codes(graph))
        self.assertEqual(
            "res://models has only import inputs below it, no project member",
            graph["diagnostics"][0]["message"],
        )

    def test_file_reads_are_runtime_references_and_listings_are_dynamic(self) -> None:
        self.source(
            "main.gd",
            """func run(path):
    FileAccess.get_file_as_string("res://data.json")
    FileAccess.open("user://save.dat", FileAccess.WRITE)
    FileAccess.open(path, FileAccess.READ)
    FileAccess.file_exists("res://absent.json")
    DirAccess.get_files_at("res://levels")
    DirAccess.open("user://saves")
""",
        )
        self.source("data.json", "{}")
        graph = self.graph()
        self.assertEqual(
            [
                ("file_access", "resolved"),
                ("dynamic_file_access", "unknown"),
                ("directory_access", "unknown"),
            ],
            [(edge["kind"], edge["status"]) for edge in graph["edges"]],
        )
        self.assertEqual(
            ["unsupported_reference_format", "dynamic_reference", "dynamic_reference"],
            self.codes(graph),
        )
        self.assertEqual(
            ["res://data.json", "res://main.gd"],
            query_graph(graph, ["main.gd"])["paths"],
        )

    def test_old_graph_preserves_deleted_files_and_edges_for_affected_queries(
        self,
    ) -> None:
        self.source("main.gd", 'load("old.tres")\n')
        self.source("old.tres", "[gd_resource]\n")
        previous = self.graph()
        del self.files["old.tres"]
        self.source("main.gd", "extends Node\n")
        graph = self.graph()
        with self.assertRaisesRegex(ValueError, "query root is missing"):
            query_graph(graph, ["old.tres"], reverse=True)
        self.assertEqual(
            ["res://main.gd", "res://old.tres"],
            query_graph(graph, ["old.tres"], reverse=True, previous=previous)["paths"],
        )

    def test_stable_uid_moves_between_graphs_retain_both_affected_owners(self) -> None:
        self.source("old.tres", '[gd_resource uid="uid://stable"]\n')
        self.source("old_consumer.gd", 'const ITEM = preload("uid://stable")\n')
        previous = self.graph()
        del self.files["old.tres"]
        del self.files["old_consumer.gd"]
        self.source("new.tres", '[gd_resource uid="uid://stable"]\n')
        self.source("new_consumer.gd", 'const ITEM = preload("uid://stable")\n')
        graph = self.graph()
        affected = query_graph(graph, ["uid://stable"], reverse=True, previous=previous)
        self.assertEqual(["res://new.tres", "res://old.tres"], affected["roots"])
        self.assertEqual(
            [
                "res://new.tres",
                "res://new_consumer.gd",
                "res://old.tres",
                "res://old_consumer.gd",
            ],
            affected["paths"],
        )
        self.assertEqual(
            ["res://new.tres"],
            query_graph(graph, ["uid://stable"], previous=previous)["paths"],
        )
        self.assertEqual(
            ["res://new.tres"],
            query_graph(graph, ["uid://stable", "new.tres"], previous=previous)["roots"],
        )
        self.assertEqual(
            ["res://old.tres"],
            query_graph(
                dict(graph, nodes=[], edges=[]), ["uid://stable"], previous=previous
            )["paths"],
        )

        self.source("duplicate.tres", '[gd_resource uid="uid://stable"]\n')
        with self.assertRaisesRegex(ValueError, "query root is missing or ambiguous"):
            query_graph(self.graph(), ["uid://stable"], reverse=True, previous=previous)

    def test_the_scan_reads_addons_and_uses_from_their_own_file(self) -> None:
        # godot_view writes the add-ons and each unit's uses beside the scan manifest.
        self.source("main.gd", 'const ITEM = preload("res://addons/shop/item.gd")\n')
        self.source("addons/shop/item.gd", "extends Node\n")
        manifest = self.root / "manifest.jsonl"
        manifest.write_text(
            json.dumps(["member", "main.gd", "main.gd", "//:game"])
            + "\n"
            + json.dumps(
                ["member", "addons/shop/item.gd", "addons/shop/item.gd", "//addons:shop"]
            )
            + "\n",
            encoding="utf-8",
        )
        addons = self.root / "addons.jsonl"
        addons.write_text(
            json.dumps(["addon", "//addons:shop", ["//addons:shop"]])
            + "\n"
            + json.dumps(["uses", "//:game", []])
            + "\n",
            encoding="utf-8",
        )
        scanned = self.root / "graph.json"
        self.assertEqual(
            0,
            main(
                [
                    "scan",
                    "--manifest",
                    str(manifest),
                    "--addons",
                    str(addons),
                    "--execroot",
                    str(self.root),
                    "--output",
                    str(scanned),
                ]
            ),
        )
        self.assertIn(
            "undeclared_addon_use",
            [
                item["code"]
                for item in json.loads(scanned.read_text(encoding="utf-8"))["diagnostics"]
            ],
        )

    def test_determinism_and_cli_validation_failure_retains_diagnostic_graph(
        self,
    ) -> None:
        self.source(
            "main.gd", 'load("missing.tres")\nconst OTHER = preload("other.gd")\n'
        )
        self.source("other.gd", "extends Node\n")
        scanned, checked = self.root / "graph.json", self.root / "checked.json"
        self.assertEqual(
            0,
            main(
                [
                    "scan",
                    "--manifest",
                    str(self.scan_manifest()),
                    "--execroot",
                    str(self.root),
                    "--output",
                    str(scanned),
                ]
            ),
        )
        owners = {
            node["path"]: node["owner"]
            for node in json.loads(scanned.read_text(encoding="utf-8"))["nodes"]
        }
        self.assertEqual(
            {"res://main.gd": "//:game", "res://other.gd": "//:game"}, owners
        )
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = main(
                [
                    "check",
                    "--graph",
                    str(scanned),
                    "--output",
                    str(checked),
                    "--require-declared",
                    "--validate",
                ]
            )
        self.assertEqual(1, result)
        self.assertIn("missing_reference", stderr.getvalue())
        self.assertIn("undeclared_reference", stderr.getvalue())
        expected = self.graph(
            require_declared=True,
            member_owners={path: "//:game" for path in self.files},
        )
        self.assertEqual(expected, json.loads(checked.read_text(encoding="utf-8")))

    def test_check_without_validate_writes_graph_and_succeeds(self) -> None:
        self.source("main.gd", 'load("missing.tres")\n')
        graph = self.graph()
        self.assertIn("missing_reference", self.codes(graph))
        scanned, checked = self.root / "graph.json", self.root / "checked.json"
        scanned.write_text(json.dumps(graph), encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = main(["check", "--graph", str(scanned), "--output", str(checked)])
        self.assertEqual(0, result)
        self.assertEqual("", stderr.getvalue())
        self.assertEqual(graph, json.loads(checked.read_text(encoding="utf-8")))

    def test_script_forms_name_resources_by_what_they_do(self) -> None:
        self.source("icon.png")
        self.source("base.gd", "class_name Base\n")
        self.source("a.gd")
        self.source(
            "hero.gd",
            """class_name Hero
@icon("res://icon.png")
extends "res://base.gd"
const A = preload("a.gd")
var b = ResourceLoader.load("res://a.gd")
var c = other.load("res://skipped.gd")
func load(x): pass
var d = FileAccess.open("user://save.dat", FileAccess.READ)
var e = FileAccess.open(path, FileAccess.READ)
var f = DirAccess.get_files_at("res://")
@icon(dynamic)
""",
        )
        edges = self.graph()["edges"]
        self.assertEqual(
            [
                ("script_icon", "res://icon.png"),
                ("script_extends", "res://base.gd"),
                ("preload", "a.gd"),
                ("load", "res://a.gd"),
                ("dynamic_file_access", None),
                ("directory_access", None),
            ],
            [(edge["kind"], edge["reference"]) for edge in edges],
        )

    def test_unreadable_formats_and_unnamed_includes_are_diagnosed(self) -> None:
        self.source("a.bin")
        self.source(
            "model.gltf",
            json.dumps({"buffers": [{"uri": "a.bin"}, {"uri": "http://host/b.bin"}]}),
        )
        self.source("broken.gltf", "{not json")
        self.source("shader.gdshader", "#include <vendor>\n")
        self.source("project.godot", "[application]\nrun/main_scene=\n[broken\n")
        graph = self.graph()
        self.assertEqual(
            [
                ("res://broken.gltf", "invalid_gltf"),
                ("res://model.gltf", "dynamic_reference"),
                ("res://project.godot", "invalid_project"),
                ("res://shader.gdshader", "dynamic_reference"),
            ],
            [(item["path"], item["code"]) for item in graph["diagnostics"]],
        )
        self.assertEqual(
            ["external_uri", "gltf_buffers", "dynamic_include"],
            [edge["kind"] for edge in graph["edges"]],
        )

    def test_query_command_prints_the_report_and_fails_for_unknown_roots(self) -> None:
        self.source("a.gd", 'const B = preload("b.gd")\n')
        self.source("b.gd")
        graph = self.root / "graph.json"
        graph.write_text(json.dumps(self.graph()), encoding="utf-8")

        def query(*arguments: str) -> tuple[int, str, str]:
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = main(["query", "--graph", str(graph), *arguments])
            return result, stdout.getvalue(), stderr.getvalue()

        result, stdout, _ = query("a.gd")
        report = json.loads(stdout)
        self.assertEqual(0, result)
        self.assertEqual(
            ("reachable", ["res://a.gd", "res://b.gd"]),
            (report["direction"], report["paths"]),
        )
        result, stdout, _ = query("--direction", "affected", "b.gd")
        report = json.loads(stdout)
        self.assertEqual(0, result)
        self.assertEqual(
            ("affected", ["res://a.gd", "res://b.gd"]),
            (report["direction"], report["paths"]),
        )
        result, stdout, stderr = query("missing.gd")
        self.assertEqual((2, ""), (result, stdout))
        self.assertIn("query root is missing or ambiguous", stderr)


class PackSelectionTest(GraphFixture):
    """Pack content follows references and must find what it references."""

    def setUp(self) -> None:
        super().setUp()
        self.source("project.godot", '[application]\nrun/main_scene="res://main.tscn"\n')
        self.source(
            "main.tscn",
            '[gd_scene]\n[ext_resource type="Script" path="res://main.gd" id="1"]\n',
        )
        self.source(
            "main.gd",
            'const UTIL = preload("util.gd")\nvar data = FileAccess.get_file_as_string("res://data.json")\n',
        )
        self.source("util.gd", "extends RefCounted\n")
        self.source("data.json", "{}")
        self.source("unused.gd", "extends Node\n")

    def select(
        self,
        relationships: Iterable[dict] = (),
        ignored: Iterable[str] = (),
        **kwargs: Any,
    ) -> dict:
        graph = self.graph(relationships=list(relationships), ignored=list(ignored))
        return select_pack(
            graph,
            sources={"res://" + path: source for path, source in self.files.items()},
            **kwargs,
        )

    def errors(self, **kwargs: Any) -> list[str]:
        with self.assertRaises(SelectionError) as raised:
            self.select(**kwargs)
        return [item["code"] for item in raised.exception.diagnostics]

    def diagnostics(self, **kwargs: Any) -> list[dict]:
        """The selection's diagnostics, whether or not they fail it."""
        try:
            return self.select(**kwargs)["diagnostics"]
        except SelectionError as error:
            return error.diagnostics

    def test_reachable_selection_starts_from_configuration_and_entry_points(
        self,
    ) -> None:
        self.source("tool.gd", "extends Node\n")
        selection = self.select(reachable=True, entry_points=["res://tool.gd"])
        self.assertEqual(
            [
                "res://data.json",
                "res://main.gd",
                "res://main.tscn",
                "res://tool.gd",
                "res://util.gd",
            ],
            selection["resources"],
        )
        self.assertEqual(
            [
                "res://project.godot",
                "res://main.tscn",
                "res://main.gd",
                "res://data.json",
            ],
            selection["chains"]["res://data.json"],
        )
        self.assertEqual(["res://tool.gd"], selection["chains"]["res://tool.gd"])
        members = self.select(reachable=False)
        self.assertIn("res://unused.gd", members["resources"])
        self.assertEqual({}, members["chains"])

    def test_directory_setting_reaches_every_member_below_it(self) -> None:
        self.source(
            "project.godot",
            '[application]\nrun/main_scene="res://main.tscn"\n'
            '[game]\nmodules="res://modules"\n',
        )
        self.source("modules/a/module.tscn", "[gd_scene]\n")
        self.source("modules/b/module.gd", 'const DATA = preload("res://data.json")\n')
        selection = self.select(reachable=True)
        self.assertLessEqual(
            {"res://modules/a/module.tscn", "res://modules/b/module.gd"},
            set(selection["resources"]),
        )
        self.assertNotIn("res://unused.gd", selection["resources"])
        self.assertEqual(
            ["res://project.godot", "res://modules/a/module.tscn"],
            selection["chains"]["res://modules/a/module.tscn"],
        )
        self.assertEqual(
            ["unavailable_reference"],
            self.errors(reachable=True, excluded=["res://modules/a/module.tscn"]),
        )

    def test_dynamic_access_needs_declarations_only_for_reachable_selection(
        self,
    ) -> None:
        self.source("main.gd", 'func run(level):\n    load("res://levels/" + level)\n')
        self.source("levels/a.tres", "[gd_resource]\n")
        self.assertEqual(["undeclared_dynamic_reference"], self.errors(reachable=True))
        self.assertIn("res://levels/a.tres", self.select(reachable=False)["resources"])
        declared = self.select(
            reachable=True,
            relationships=[
                {
                    "source": "main.gd",
                    "target": "levels/a.tres",
                    "kind": "runtime",
                    "owner": "//:game",
                }
            ],
        )
        self.assertIn("res://levels/a.tres", declared["resources"])
        group = [
            {
                "source": "",
                "target": "main.gd",
                "kind": "membership",
                "owner": "//:game",
            },
            {
                "source": "",
                "target": "levels/a.tres",
                "kind": "runtime",
                "owner": "//:game",
            },
        ]
        chains = self.select(reachable=True, relationships=group)["chains"]
        self.assertEqual(
            [
                "res://project.godot",
                "res://main.tscn",
                "res://main.gd",
                "res://levels/a.tres",
            ],
            chains["res://levels/a.tres"],
        )

    def test_unanalyzed_binary_scenes_need_declarations(self) -> None:
        self.source(
            "main.tscn",
            '[gd_scene]\n[ext_resource type="PackedScene" path="res://level.scn" id="1"]\n',
        )
        self.source("level.scn", "binary")
        self.assertEqual(["undeclared_dynamic_reference"], self.errors(reachable=True))
        selection = self.select(
            reachable=True,
            relationships=[
                {
                    "source": "level.scn",
                    "target": "util.gd",
                    "kind": "runtime",
                    "owner": "//:game",
                }
            ],
        )
        self.assertEqual(
            ["res://level.scn", "res://main.tscn", "res://util.gd"],
            selection["resources"],
        )

    def test_targets_without_files_contribute_their_runtime_members(self) -> None:
        self.source("levels/a.json", "{}")
        selection = self.select(
            reachable=True,
            relationships=[
                {
                    "source": "",
                    "target": "levels/a.json",
                    "kind": "runtime",
                    "owner": "//:levels",
                }
            ],
        )
        self.assertEqual(
            ["res://levels/a.json"], selection["chains"]["res://levels/a.json"]
        )

    def test_required_packs_provide_content_with_one_identity(self) -> None:
        required = [{"pack": "//:base", "resources": {"util.gd": "util.gd"}}]
        selection = self.select(reachable=True, required=required)
        self.assertEqual(
            ["res://data.json", "res://main.gd", "res://main.tscn"],
            selection["resources"],
        )
        self.assertEqual({"res://util.gd": "//:base"}, selection["required"])
        self.assertNotIn(
            "res://util.gd",
            self.select(reachable=False, required=required)["resources"],
        )
        conflict = [{"pack": "//:base", "resources": {"util.gd": "other/util.gd"}}]
        self.assertEqual(
            ["identity_conflict"], self.errors(reachable=True, required=conflict)
        )

    def test_hard_references_to_excluded_files_fail(self) -> None:
        self.assertEqual(
            ["unavailable_reference"],
            self.errors(reachable=True, excluded=["res://util.gd"]),
        )
        # Code can guard a file read; the excluded file is then simply absent.
        self.assertNotIn(
            "res://data.json",
            self.select(reachable=True, excluded=["res://data.json"])["resources"],
        )

    def test_extension_library_paths_never_advertise_membership(self) -> None:
        self.source("native.gdextension", "[configuration]\n")
        self.source("native.so", "binary")
        self.source("opaque.so", "user data")
        for reachable in [False, True]:
            with self.subTest(reachable=reachable):
                selection = self.select(
                    reachable=reachable,
                    entry_points=["res://opaque.so"] if reachable else [],
                    extensions=["res://native.gdextension", "res://native.so"],
                    extension_library_paths=["res://native.so"],
                )
                self.assertIn("res://native.gdextension", selection["resources"])
                self.assertIn("res://opaque.so", selection["resources"])
                self.assertNotIn("res://native.so", selection["resources"])

    def test_references_to_files_the_export_leaves_out(self) -> None:
        hiders = {
            "a/.gdignore": "res://a/.gdignore hides its directory",
            "b/project.godot": "res://b/project.godot hides its directory",
            ".c/.keep": "res://.c is a hidden directory",
        }
        references = {
            "preload": ('const T = preload("res://{}")\n', "error"),
            "load": ('var t = load("res://{}")\n', "error"),
            "file_access": (
                'var t = FileAccess.get_file_as_string("res://{}")\n',
                "warning",
            ),
        }
        ignored = []
        for marker in hiders:
            self.source(marker)
            self.source(marker.partition("/")[0] + "/template.tres", "[gd_resource]\n")
            ignored += [marker, marker.partition("/")[0] + "/template.tres"]
        for (marker, cause), (kind, (code, severity)), reachable in itertools.product(
            hiders.items(), references.items(), [False, True]
        ):
            with self.subTest(marker=marker, kind=kind, reachable=reachable):
                target = marker.partition("/")[0] + "/template.tres"
                self.source("main.gd", "extends Node\n" + code.format(target))
                [item] = self.diagnostics(ignored=ignored, reachable=reachable)
                self.assertEqual(
                    ("ignored_reference", "res://main.gd", 2, severity),
                    (item["code"], item["path"], item["line"], item["severity"]),
                )
                self.assertIn(
                    f"{kind} reference to res://{target}, which Godot's export leaves out: {cause}",
                    item["message"],
                )

    def test_scene_references_to_files_the_export_leaves_out_fail(self) -> None:
        self.source("addons/demo/project.godot")
        self.source("addons/demo/icon.png", "binary")
        self.source(
            "main.tscn",
            '[gd_scene]\n[ext_resource type="Texture2D" path="res://addons/demo/icon.png" id="1"]\n',
        )
        with self.assertRaises(SelectionError) as raised:
            self.select(
                ignored=["addons/demo/project.godot", "addons/demo/icon.png"],
                reachable=False,
            )
        [item] = raised.exception.diagnostics
        self.assertEqual(
            ("ignored_reference", "res://main.tscn", 2, "error"),
            (item["code"], item["path"], item["line"], item["severity"]),
        )
        self.assertIn("resource reference to res://addons/demo/icon.png", item["message"])

    def test_each_line_reporting_the_same_reference_counts(self) -> None:
        self.source("report/.gdignore")
        self.source("report/a.html")
        read = 'FileAccess.get_file_as_string("res://report/a.html")\n'
        self.source("main.gd", f"var a = {read}var b = {read}")
        diagnostics = self.select(
            ignored=["report/.gdignore", "report/a.html"], reachable=False
        )["diagnostics"]
        self.assertEqual([1, 2], [item["line"] for item in diagnostics])

    def test_godot_packs_a_hidden_file_of_a_visible_directory(self) -> None:
        self.source("main.gd", 'const T = preload("res://.template.tres")\n')
        self.source(".template.tres", "[gd_resource]\n")
        selection = self.select(ignored=[".template.tres"], reachable=True)
        self.assertEqual([], selection["diagnostics"])
        self.assertIn("res://.template.tres", selection["resources"])

    def test_declared_runtime_references_acknowledge_file_reads(self) -> None:
        self.source(
            "main.gd",
            'var a = FileAccess.get_file_as_string("res://report/a.html")\n'
            'var b = FileAccess.get_file_as_string("res://report/css/b.css")\n',
        )
        ignored = ["report/.gdignore", "report/a.html", "report/css/b.css"]
        for path in ignored:
            self.source(path)
        for destination in [["report/a.html", "report/css/b.css"], ["report"]]:
            with self.subTest(destination=destination):
                selection = self.select(
                    relationships=[runtime("main.gd", target) for target in destination],
                    ignored=ignored,
                    reachable=True,
                )
                self.assertEqual([], selection["diagnostics"])
        # A declaration from another file acknowledges nothing.
        self.source("other.gd", "extends Node\n")
        selection = self.select(
            relationships=[runtime("other.gd", "report/a.html")],
            ignored=ignored,
            reachable=False,
        )
        self.assertEqual(
            ["res://main.gd:1", "res://main.gd:2"],
            [f"{item['path']}:{item['line']}" for item in selection["diagnostics"]],
        )

    def test_hard_references_to_acknowledged_files_still_fail(self) -> None:
        self.source("main.gd", 'const T = preload("res://report/t.tres")\n')
        self.source("report/.gdignore")
        self.source("report/t.tres", "[gd_resource]\n")
        self.assertEqual(
            ["ignored_reference"],
            self.errors(
                relationships=[runtime("main.gd", "report/t.tres")],
                ignored=["report/.gdignore", "report/t.tres"],
                reachable=True,
            ),
        )

    def test_members_packing_leaves_source_graph_errors_to_the_graph(self) -> None:
        self.source("main.gd", 'const MISSING = preload("res://missing.tres")\n')
        self.assertEqual(["missing_reference"], self.errors(reachable=True))
        self.assertEqual([], self.select(reachable=False)["diagnostics"])

    def test_graph_errors_matter_only_for_selected_files(self) -> None:
        self.source("unused.gd", 'const MISSING = preload("res://missing.tres")\n')
        self.assertNotIn("res://unused.gd", self.select(reachable=True)["resources"])
        self.assertEqual(
            ["missing_reference"],
            self.errors(reachable=True, entry_points=["res://unused.gd"]),
        )

    def test_select_command_writes_content_and_rejects_conflicting_providers(
        self,
    ) -> None:
        def run() -> tuple[int, str]:
            (self.root / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                result = pack_selection.main(
                    [
                        "--manifest",
                        str(self.root / "manifest.json"),
                        "--graph",
                        str(graph),
                        "--project-manifest",
                        str(project),
                        "--output",
                        str(self.root / "selection.json"),
                        "--content",
                        str(self.root / "content.json"),
                        "--execroot",
                        str(self.root),
                    ]
                )
            return result, stderr.getvalue()

        project = self.scan_manifest()
        graph = self.root / "graph.json"
        graph.write_text(json.dumps(self.graph()), encoding="utf-8")
        (self.root / "base.json").write_text(
            json.dumps({"pack": "//:base", "resources": {"util.gd": "util.gd"}}),
            encoding="utf-8",
        )
        manifest = {
            "pack": "//:dlc",
            "selection": "reachable",
            "entry_points": [],
            "extensions": [],
            "excluded": [],
            "extension_library_paths": [],
            "required": ["base.json"],
        }
        self.assertEqual((0, ""), run())
        content = json.loads((self.root / "content.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {
                "pack": "//:dlc",
                "resources": {
                    "data.json": "data.json",
                    "main.gd": "main.gd",
                    "main.tscn": "main.tscn",
                },
            },
            content,
        )
        self.assertEqual(
            {"res://util.gd": "//:base"},
            json.loads((self.root / "selection.json").read_text(encoding="utf-8"))[
                "required"
            ],
        )
        (self.root / "other.json").write_text(
            json.dumps({"pack": "//:other", "resources": {"util.gd": "other/util.gd"}}),
            encoding="utf-8",
        )
        manifest["required"].append("other.json")
        result, stderr = run()
        self.assertEqual(2, result)
        self.assertIn("identity_conflict", stderr)
        # A pack that builds prints its warnings.
        self.source(".data/.keep")
        self.source(
            "main.gd",
            'var data = FileAccess.get_file_as_string("res://.data/data.json")\n',
        )
        self.source(".data/data.json", "{}")
        graph.write_text(
            json.dumps(self.graph(ignored=[".data/.keep", ".data/data.json"])),
            encoding="utf-8",
        )
        manifest["required"] = []
        self.scan_manifest()
        result, stderr = run()
        self.assertEqual(0, result)
        self.assertIn("res://main.gd:1: warning: ignored_reference: file_access", stderr)


if __name__ == "__main__":
    unittest.main()
