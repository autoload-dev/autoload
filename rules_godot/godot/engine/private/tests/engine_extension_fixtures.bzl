"""
The tags and helpers of the godot_engines extension's planning tests.

The tests plan the extension's repositories from mocked modules: engine_extension_tests.bzl
those of engine selection and binaries, engine_source_recipes_tests.bzl those built from
source.
"""

# buildifier: disable=bzl-visibility
load("//godot/engine/private:extension_plan.bzl", "plan_engines")

# buildifier: disable=bzl-visibility
load("//godot/private/tests:mocks.bzl", "mocks")

_ENGINE = {
    "name": "godot",
    "version": "4.7.2",
    "default": False,
    "lock_file": None,
}

# The repositories of the catalogue's 4.7.2 sources and of _SOURCE's, which their digests name.
_RELEASE_SOURCE = "godot_source_e954996374cb"
_RELEASE_TREE = "godot_tree_e954996374cb"
_TAG_SOURCE = "godot_source_000000000000"

_SOURCE = {
    "engine": "godot",
    "urls": ["file:///godot.tar.gz"],
    "sha256": "0" * 64,
    "strip_prefix": "godot",
    "version": "",
}

_BINARIES = {
    "engine": "godot",
    "editor_urls": {},
    "editor_integrity": {},
    "editor_binaries": {},
    "templates_urls": [],
    "templates_integrity": "",
    "templates_macos_cpus": [],
    "templates_linux_cpus": [],
    "ios_simulator_cpus": [],
    "android_shell_urls": [],
    "android_shell_integrity": "",
    "android_debug_shell_urls": [],
    "android_debug_shell_integrity": "",
}

_BUILD = {
    "engine": "godot",
    "enabled_modules": ["gdscript", "text_server_fb"],
    "default_modules": False,
    "custom_modules": {},
    "patches": [],
    "patch_strip": 1,
    "renderers": [],
    "build_options": {"vulkan": "no"},
}

_EDITOR = {
    "engine": "godot",
    "enabled_modules": [],
    "default_modules": False,
    "build_options": {},
}

_TAG_ATTRIBUTES = {
    "engine": _ENGINE.keys(),
    "source": _SOURCE.keys(),
    "binaries": _BINARIES.keys(),
    "build": _BUILD.keys(),
    "editor": _EDITOR.keys(),
}

def _engine(**overrides):
    return mocks.tag(**(_ENGINE | overrides))

def _source(**overrides):
    return mocks.tag(**(_SOURCE | overrides))

def _binaries(**overrides):
    return mocks.tag(**(_BINARIES | overrides))

def _build(**overrides):
    return mocks.tag(**(_BUILD | overrides))

def _editor(**overrides):
    return mocks.tag(**(_EDITOR | overrides))

# The extension's tag classes, each empty unless a module lists its tags.
_TAG_CLASSES = ["engine", "source", "binaries", "build", "editor", "runtime_profile"]

def _module(name, *, is_root = False, **tags):
    """A module with the given tags of each tag class, and no tags of the others."""
    return mocks.module(name, is_root = is_root, **({tag: [] for tag in _TAG_CLASSES} | tags))

def _root(binaries = None, **overrides):
    """The root module with one engine, and its binaries tag where given."""
    return [_module(
        "consumer",
        is_root = True,
        engine = [_engine(**overrides)],
        binaries = [binaries] if binaries else [],
    )]

# The contents of the runtime profiles the tests register, by label.
_PROFILES = {
    "//app:small.gdbuild": json.encode({"disabled_build_options": {"disable_3d": True}}),
    "//app:classes.gdbuild": json.encode({"disabled_classes": ["Tree"], "disabled_build_options": {}}),
}

def _plan(modules):
    errors, fail_ = mocks.errors()
    declarations = plan_engines(modules, tag_attributes = _TAG_ATTRIBUTES, read = lambda label: _PROFILES[label], _fail = fail_)
    return declarations, errors

def _declared(declarations, name):
    return [declaration for declaration in declarations if declaration.attrs["name"] == name]

def _rules(declarations, rule):
    return [declaration for declaration in declarations if declaration.rule == rule]

def _slots(declarations, hub):
    return {slot["name"]: slot for slot in json.decode(_declared(declarations, hub)[0].attrs["components"])}

def _recipes(declarations):
    return {declaration.attrs["name"]: declaration.attrs for declaration in _rules(declarations, "godot_engine_build")}

def _expect_one_error(env, modules, message):
    declarations, errors = _plan(modules)
    env.expect.where(expected = message).that_collection(errors).contains_exactly([message])
    env.expect.where(expected = message).that_bool(declarations == None).equals(True)

extension = struct(
    engine = _engine,
    source = _source,
    binaries = _binaries,
    build = _build,
    editor = _editor,
    module = _module,
    root = _root,
    plan = _plan,
    declared = _declared,
    rules = _rules,
    slots = _slots,
    recipes = _recipes,
    expect_one_error = _expect_one_error,
    ENGINE = _ENGINE,
    RELEASE_SOURCE = _RELEASE_SOURCE,
    RELEASE_TREE = _RELEASE_TREE,
    TAG_SOURCE = _TAG_SOURCE,
    SOURCE = _SOURCE,
    BINARIES = _BINARIES,
    BUILD = _BUILD,
    EDITOR = _EDITOR,
    TAG_ATTRIBUTES = _TAG_ATTRIBUTES,
    PROFILES = _PROFILES,
)
