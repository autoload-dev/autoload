"""
Prototype: the targets of a shared tree repository, from its recipes' descriptions.

Each recipe repository writes `shared.bzl` with its generators, header sets and objects,
named by digests of what their actions read. The tree repository declares the union, so
equivalent work of two recipes is one target with one action and one cache key.
"""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("@rules_cc//cc:objc_library.bzl", "objc_library")
load(":generator.bzl", "godot_shared_generator", "godot_source_headers", "godot_source_revision")

visibility("public")

_RULES = {
    "cc_library": cc_library,
    "objc_library": objc_library,
}

def _union(recipes, kind):
    """Each named entry of the recipes' descriptions once; equal names describe equal work."""
    entries = {}
    for recipe in recipes:
        for entry in recipe[kind]:
            entries.setdefault(entry["name"], entry)
    return entries.values()

def godot_shared_objects(name, recipes):
    """
    Declare the generators, header sets and objects of the recipes of a shared tree.

    Args:
        name: The library of the tree's root include directory, which every object uses
            as `:_root`.
        recipes: The SHARED descriptions of the recipe repositories.
    """
    cc_library(name = name, includes = ["."], tags = ["manual"])
    for entry in _union(recipes, "build_names"):
        # Only the build name file is read; a recipe's hash and time stamp stay with it.
        directory = "_build_names/" + entry["build_name"]
        godot_source_revision(
            name = entry["name"],
            build_name = entry["build_name"],
            inputs_hash = "",
            build = directory + "/build.txt",
            hash = directory + "/hash.txt",
            timestamp = directory + "/timestamp.txt",
            tags = ["manual"],
        )
    for entry in _union(recipes, "generators"):
        godot_shared_generator(
            name = entry["name"],
            spec_json = entry["spec_json"],
            inputs = entry["inputs"],
            outs = entry["outs"],
            logical_outputs = entry["logical_outputs"],
        )
    for entry in _union(recipes, "headers"):
        godot_source_headers(name = entry["name"], hdrs = entry["hdrs"], deps = entry["deps"], tags = ["manual"])
    for entry in _union(recipes, "objects"):
        _RULES[entry["rule"]](
            name = entry["name"],
            srcs = entry["srcs"],
            copts = entry["copts"],
            includes = entry["includes"],
            local_defines = entry["local_defines"],
            deps = entry["deps"],
            alwayslink = True,
            tags = ["manual"],
        )
