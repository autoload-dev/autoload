"""Public core rules for resources, add-ons, projects, PCK exports, binaries, tests and editor views."""

load("//godot/private:addon.bzl", _godot_addon = "godot_addon")
load("//godot/private:analysis.bzl", _godot_resource_graph = "godot_resource_graph")
load(
    "//godot/private:editor.bzl",
    _godot_editor = "godot_editor",
    _godot_metadata_sync = "godot_metadata_sync",
)
load("//godot/private:pack.bzl", _godot_pack = "godot_pack")
load("//godot/private:project.bzl", _godot_project = "godot_project")
load("//godot/private:resources.bzl", _godot_resources = "godot_resources")
load(
    "//godot/private:run.bzl",
    _godot_run = "godot_run",
    _godot_test = "godot_test",
)

godot_resources = _godot_resources
godot_addon = _godot_addon
godot_project = _godot_project
godot_pack = _godot_pack
godot_run = _godot_run
godot_test = _godot_test
godot_editor = _godot_editor
godot_metadata_sync = _godot_metadata_sync
godot_resource_graph = _godot_resource_graph
