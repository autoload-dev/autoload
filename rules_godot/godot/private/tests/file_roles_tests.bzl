"""
A path from configuration resolves against the declared files as a file or a directory, and
Godot's ignore rule decides which declared files Godot ignores.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")

# buildifier: disable=bzl-visibility
load("//godot/private:paths.bzl", "godot_ignored", "resolve_project_path")

# buildifier: disable=bzl-visibility
load("//godot/private:view.bzl", "GodotViewInfo")
load(":views.bzl", "run_view")

# Strings stand in for the Files; resolution only looks at resource paths.
_DECLARED = {
    "game.icon/Assets/dot.png": "dot",
    "game.icon/icon.json": "json",
    "game.iconography.png": "other",
    "modules/a/module.tscn": "a",
    "icon.png": "png",
}

def _test_a_declared_file_resolves_as_a_file(env):
    resolved = resolve_project_path(_DECLARED, "res://icon.png")
    env.expect.that_str(resolved.kind).equals("file")
    env.expect.that_str(resolved.path).equals("icon.png")
    env.expect.that_dict(resolved.files).contains_exactly({"icon.png": "png"})

def _test_a_directory_with_a_suffix_resolves_to_every_file_below_it(env):
    for path in ["res://game.icon", "game.icon", "res://game.icon/"]:
        resolved = resolve_project_path(_DECLARED, path)
        env.expect.that_str(resolved.kind).equals("directory")
        env.expect.that_str(resolved.path).equals("game.icon")
        env.expect.that_dict(resolved.files).contains_exactly({
            "game.icon/Assets/dot.png": "dot",
            "game.icon/icon.json": "json",
        })

def _test_an_undeclared_path_resolves_to_nothing(env):
    for path in ["res://modules/b", "res://game", "res://mod"]:
        env.expect.that_bool(resolve_project_path(_DECLARED, path) == None).equals(True)

# Godot's ignore rules, one row per case: a path, the other own files, and whether Godot
# ignores the path.
_IGNORED = [
    ("report/template.html", ["report/.gdignore"], True),
    ("report/.gdignore", [], True),
    ("demo/main.gd", ["demo/project.godot"], True),
    (".godot/imported/a.ctex", [], True),
    ("main/.env", [], True),
    (".cache/a.png", [], True),
    (".gdignore", [], True),
    ("reports/index.html", ["report/.gdignore"], False),
    ("project.godot", [], False),
    ("main/main.gd", [], False),
]

def _test_godot_ignored_follows_godots_ignore_rule(env):
    for path, own, ignored in _IGNORED:
        env.expect.where(path = path).that_bool(path in godot_ignored([path] + own)).equals(ignored)

_IGNORED_FIXTURE = "//godot/private/tests/godot_ignored/fixtures/project_with_ignored_directory"

# The declaring targets decide which of their files Godot ignores, and the operation carries
# that role from their resources.
def _test_operations_carry_the_godot_ignored_role(name):
    analysis_test(
        name = name,
        target = run_view(name + "_run", _IGNORED_FIXTURE, [_IGNORED_FIXTURE + ":reader"]),
        impl = _operations_carry_the_godot_ignored_role,
    )

def _operations_carry_the_godot_ignored_role(env, target):
    view = target[GodotViewInfo]
    env.expect.that_collection(view.ignored_resource_paths.keys()).contains_exactly([
        "demo/demo.gd",
        "demo/project.godot",
        "main/.notes.txt",
        "report/.gdignore",
        "report/helper.gd",
        "report/logo.png",
        "report/template.html",
    ])
    env.expect.that_collection(view.member_resource_paths.keys()).contains_at_least(view.ignored_resource_paths.keys())

def file_roles_test_suite(name):
    test_suite(
        name = name,
        tests = [_test_operations_carry_the_godot_ignored_role],
        basic_tests = [
            _test_a_declared_file_resolves_as_a_file,
            _test_a_directory_with_a_suffix_resolves_to_every_file_below_it,
            _test_an_undeclared_path_resolves_to_nothing,
            _test_godot_ignored_follows_godots_ignore_rule,
        ],
    )
