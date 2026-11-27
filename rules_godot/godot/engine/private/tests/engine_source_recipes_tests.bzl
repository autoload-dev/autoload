"""
The godot_engines extension plans the source archives, engine trees and recipes of engines
that build from source.
"""

load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/private/tests:mocks.bzl", "mocks")
load(":engine_extension_fixtures.bzl", "extension")

visibility("private")

_engine = extension.engine
_source = extension.source
_binaries = extension.binaries
_build = extension.build
_editor = extension.editor
_module = extension.module
_root = extension.root
_plan = extension.plan
_declared = extension.declared
_rules = extension.rules
_slots = extension.slots
_recipes = extension.recipes
_expect_one_error = extension.expect_one_error
_RELEASE_SOURCE = extension.RELEASE_SOURCE
_RELEASE_TREE = extension.RELEASE_TREE
_TAG_SOURCE = extension.TAG_SOURCE

def _test_lacking_slots_build_from_the_release_sources(env):
    declarations, errors = _plan(_root())
    env.expect.that_collection(errors).contains_exactly([])
    slots = _slots(declarations, "godot")

    # The official simulator libraries are x86_64 only, and the official shells are release builds.
    env.expect.that_str(slots["runtime_ios_x86_64_simulator_release"]["payload"]).equals("@godot_templates_ios//:ios_release")
    env.expect.that_str(slots["runtime_ios_arm64_simulator_release"]["payload"]).equals(
        "@godot_ios_arm64_simulator_template_release//:engine_library",
    )
    env.expect.that_str(slots["runtime_ios_arm64_simulator_debug"]["version"]).equals("4.7.2")
    env.expect.that_str(slots["runtime_android_arm64_debug"]["payload"]).equals("//android:debug")
    env.expect.that_str(slots["runtime_ios_arm64_device_release"]["payload"]).equals("@godot_templates_ios//:ios_release")
    source = _declared(declarations, _RELEASE_SOURCE)
    env.expect.that_collection([declaration.rule for declaration in source]).contains_exactly(["godot_engine_source"])
    env.expect.that_str(source[0].attrs["version"]).equals("4.7.2")
    tree = _declared(declarations, _RELEASE_TREE)
    env.expect.that_collection([declaration.rule for declaration in tree]).contains_exactly(["godot_engine_tree"])
    recipes = _recipes(declarations)
    env.expect.that_collection(recipes.keys()).contains_at_least([
        "godot_android_arm64_template_debug",
        "godot_android_x86_64_template_debug",
        "godot_ios_arm64_simulator_template_debug",
        "godot_ios_arm64_simulator_template_release",
    ])

    # The catalogue's editors serve every editor slot, so no editor is built.
    env.expect.that_bool(any([recipe.endswith("_editor") for recipe in recipes])).equals(False)
    env.expect.that_collection(_declared(declarations, "godot_source_android_shell")).has_size(1)

    # Recipes report the engine's name as their build name.
    env.expect.that_str(recipes["godot_android_arm64_template_debug"]["build_name"]).equals("godot")

def _test_tuned_runtimes_build_from_the_release_sources(env):
    declarations, errors = _plan(_root())
    env.expect.that_collection(errors).contains_exactly([])
    slots = _slots(declarations, "godot")

    # The prebuilt runtime serves applications without a build profile, a source-built one the others.
    env.expect.that_bool(slots["runtime_macos_arm64_release"]["untuned_only"]).equals(True)
    tuned = slots["runtime_macos_arm64_release_tuned"]
    env.expect.that_bool(tuned["untuned_only"]).equals(False)
    env.expect.that_str(tuned["payload"]).equals("@godot_macos_arm64_template_release//:godot")
    env.expect.that_collection(tuned["visibility"]).contains_exactly(["//:registration"])
    env.expect.that_str(slots["runtime_android_arm64_release_tuned"]["payload"]).equals("//android:release_tuned")

    # Slots the artifacts lack serve every application.
    env.expect.that_bool(slots["runtime_ios_arm64_simulator_release"]["untuned_only"]).equals(False)
    env.expect.that_bool("runtime_ios_arm64_simulator_release_tuned" in slots).equals(False)
    hub = _declared(declarations, "godot")[0].attrs
    env.expect.that_collection(json.decode(hub["android_runtimes"]).keys()).contains_exactly(
        ["debug", "release", "release_tuned"],
    )

# Apple's recipes of an official policy declare their rendering methods, without Vulkan,
# which would need the MoltenVK SDK on the configuring Mac; applications check their
# project's method.
def _test_apple_official_recipes_build_without_vulkan(env):
    declarations, errors = _plan(_root())
    env.expect.that_collection(errors).contains_exactly([])
    for recipe in _recipes(declarations).values():
        expected = ["gl_compatibility", "mobile", "forward_plus"] if recipe["platform"] in ["ios", "macos"] else []
        expect = env.expect.where(recipe = recipe["name"])
        expect.that_collection(recipe["renderers"]).contains_exactly(expected)
        expect.that_dict(recipe["build_options"]).contains_exactly({})
        expect.that_bool(recipe["default_modules"]).equals(True)

def _test_prerelease_runtimes_build_from_its_sources(env):
    declarations, errors = _plan(_root(name = "beta", version = "4.8.0-beta1"))
    env.expect.that_collection(errors).contains_exactly([])
    slots = _slots(declarations, "beta")
    env.expect.that_str(slots["runtime_ios_arm64_simulator_release"]["version"]).equals("4.8.0-beta")
    env.expect.that_str(slots["runtime_ios_arm64_simulator_release"]["payload"]).equals(
        "@beta_ios_arm64_simulator_template_release//:engine_library",
    )

def _test_a_build_policy_builds_every_slot(env):
    declarations, errors = _plan([_module("consumer", is_root = True, engine = [_engine()], build = [_build()])])
    env.expect.that_collection(errors).contains_exactly([])

    # The catalogue's binaries belong to Godot's official policy, so none serve.
    env.expect.that_collection(_rules(declarations, "godot_editor_archive")).contains_exactly([])
    env.expect.that_collection(_rules(declarations, "http_file")).contains_exactly([])
    slots = _slots(declarations, "godot")
    env.expect.that_str(slots["editor_linux_x86_64"]["payload"]).equals("@godot_linux_x86_64_editor//:godot")
    env.expect.that_str(slots["runtime_macos_arm64_release"]["payload"]).equals("@godot_macos_arm64_template_release//:godot")
    env.expect.that_str(slots["runtime_android_arm64_release"]["payload"]).equals("//android:release")
    env.expect.that_bool(any([name.endswith("_tuned") for name in slots])).equals(False)
    for recipe in _recipes(declarations).values():
        expect = env.expect.where(recipe = recipe["name"])
        expect.that_collection(recipe["enabled_modules"]).contains_exactly(["gdscript", "text_server_fb"])
        expect.that_dict(recipe["build_options"]).contains_exactly({"vulkan": "no"})
        expect.that_collection(recipe["renderers"]).contains_exactly([])

    # Every valid slot exists; the source build constructs nothing invalid such as an iOS editor.
    env.expect.that_collection(slots.keys()).contains_at_least([
        "editor_linux_arm64",
        "editor_macos_x86_64",
        "runtime_linux_x86_64_debug",
        "runtime_ios_arm64_device_release",
        "runtime_ios_x86_64_simulator_debug",
        "runtime_android_x86_64_debug",
    ])
    env.expect.that_bool("editor_ios_arm64" in slots).equals(False)

def _test_binaries_beside_a_build_policy_serve(env):
    pins = dict(
        android_shell_urls = ["file:///fork_shell.aar"],
        android_shell_integrity = "sha256-" + "A" * 43 + "=",
    )
    declarations, errors = _plan([_module(
        "consumer",
        is_root = True,
        engine = [_engine()],
        build = [_build()],
        binaries = [_binaries(**pins)],
    )])
    env.expect.that_collection(errors).contains_exactly([])
    runtimes = json.decode(_declared(declarations, "godot")[0].attrs["android_runtimes"])
    env.expect.that_dict(runtimes["release"]).contains_exactly({"shell": "@godot_android_shell//file"})
    env.expect.that_str(runtimes["debug"]["shell"]).equals("@godot_source_android_shell//:debug.aar")

def _test_editor_recipes_take_the_editor_policy(env):
    declarations, errors = _plan([_module(
        "consumer",
        is_root = True,
        engine = [_engine()],
        build = [_build(build_options = {"disable_3d": "yes"}, patches = ["//:fork.patch"])],
        editor = [_editor(enabled_modules = ["gdscript", "text_server_fb", "svg"], build_options = {"vulkan": "no"})],
    )])
    env.expect.that_collection(errors).contains_exactly([])
    recipes = _recipes(declarations)
    editor = recipes["godot_macos_arm64_editor"]
    env.expect.that_collection(editor["enabled_modules"]).contains_exactly(["gdscript", "text_server_fb", "svg"])
    env.expect.that_dict(editor["build_options"]).contains_exactly({"vulkan": "no"})

    # The tree is the archive's alone; every recipe and the Android shell patch their own
    # copies of the files the policy's patches touch.
    env.expect.that_dict(_declared(declarations, _RELEASE_TREE)[0].attrs).contains_exactly({
        "name": _RELEASE_TREE,
        "source": "@%s//:source.json" % _RELEASE_SOURCE,
    })
    env.expect.that_str(editor["tree"]).equals("@%s//:tree.json" % _RELEASE_TREE)
    env.expect.that_collection(editor["patches"]).contains_exactly(["//:fork.patch"])
    env.expect.that_int(editor["patch_strip"]).equals(1)
    shell = _declared(declarations, "godot_source_android_shell")[0].attrs
    env.expect.that_dict(shell).contains_exactly({
        "name": "godot_source_android_shell",
        "tree": "@%s//:tree.json" % _RELEASE_TREE,
        "patches": ["//:fork.patch"],
        "patch_strip": 1,
    })
    runtime = recipes["godot_macos_arm64_template_release"]
    env.expect.that_collection(runtime["enabled_modules"]).contains_exactly(["gdscript", "text_server_fb"])
    env.expect.that_dict(runtime["build_options"]).contains_exactly({"disable_3d": "yes"})

def _test_source_tag_replaces_the_catalogue_sources(env):
    declarations, errors = _plan([_module(
        "consumer",
        is_root = True,
        engine = [_engine(version = "4.7.3-rc1")],
        source = [_source()],
    )])
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_dict(_declared(declarations, _TAG_SOURCE)[0].attrs).contains_exactly({
        "name": _TAG_SOURCE,
        "urls": ["file:///godot.tar.gz"],
        "sha256": "0" * 64,
        "strip_prefix": "godot",
        "version": "4.7.3-rc1",
    })

    # Without binaries, every slot is built from these sources.
    slots = _slots(declarations, "godot")
    env.expect.that_str(slots["editor_macos_arm64"]["payload"]).equals("@godot_macos_arm64_editor//:godot")
    env.expect.that_str(slots["editor_macos_arm64"]["version"]).equals("4.7.3-rc1")
    declarations, errors = _plan([_module(
        "consumer",
        is_root = True,
        engine = [_engine(version = "4.8.0-beta1")],
        source = [_source(version = "4.8.0-beta")],
    )])
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_str(_declared(declarations, _TAG_SOURCE)[0].attrs["version"]).equals("4.8.0-beta")

def _test_engines_of_one_source_share_its_tree(env):
    # The default engine builds the slots its binaries lack, simulation every slot, both
    # from the catalogue's 4.7.2 sources; patches stay each engine's.
    declarations, errors = _plan([_module(
        "consumer",
        is_root = True,
        engine = [_engine(default = True), _engine(name = "simulation")],
        build = [_build(engine = "simulation", patches = ["//:fork.patch"])],
    )])
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection([
        declaration.attrs["name"]
        for declaration in declarations
        if declaration.rule in ["godot_engine_source", "godot_engine_tree"]
    ]).contains_exactly([_RELEASE_SOURCE, _RELEASE_TREE])
    recipes = _recipes(declarations)
    tree = "@%s//:tree.json" % _RELEASE_TREE
    env.expect.that_str(recipes["godot_ios_arm64_simulator_template_release"]["tree"]).equals(tree)
    env.expect.that_str(recipes["simulation_macos_arm64_editor"]["tree"]).equals(tree)
    env.expect.that_collection(recipes["godot_ios_arm64_simulator_template_release"]["patches"]).contains_exactly([])
    env.expect.that_collection(recipes["simulation_macos_arm64_editor"]["patches"]).contains_exactly(["//:fork.patch"])

def _test_engines_of_one_archive_share_its_mirrors(env):
    # Mirror URLs are no identity: the shared archive takes both engines' URLs.
    declarations, errors = _plan([_module(
        "consumer",
        is_root = True,
        engine = [_engine(version = "4.7.3-rc1"), _engine(name = "fork", version = "4.7.3-rc1")],
        source = [_source(), _source(engine = "fork", urls = ["file:///mirror.tar.gz"])],
    )])
    env.expect.that_collection(errors).contains_exactly([])
    sources = _rules(declarations, "godot_engine_source")
    env.expect.that_collection(sources).has_size(1)
    env.expect.that_collection(sources[0].attrs["urls"]).contains_exactly(
        ["file:///godot.tar.gz", "file:///mirror.tar.gz"],
    )

def _test_engines_of_one_archive_describe_it_alike(env):
    _expect_one_error(
        env,
        [_module(
            "consumer",
            is_root = True,
            engine = [_engine(version = "4.7.3-rc1"), _engine(name = "fork", version = "4.7.3-rc1")],
            source = [_source(), _source(engine = "fork", strip_prefix = "fork")],
        )],
        "Godot engines declare the source archive of %s with different strip_prefix " % _TAG_SOURCE +
        "or version; declare it alike in every engine",
    )

def _test_runtime_profiles_reach_the_runtime_recipes_of_their_engine(env):
    declarations, errors = _plan([_module(
        "consumer",
        is_root = True,
        engine = [_engine(default = True), _engine(name = "simulation")],
        build = [_build(engine = "simulation")],
        runtime_profile = [
            mocks.tag(profile = "//app:small.gdbuild", engine = ""),
            # Classes alone need no runtime variant.
            mocks.tag(profile = "//app:classes.gdbuild", engine = ""),
        ],
    )])
    env.expect.that_collection(errors).contains_exactly([])
    recipes = _recipes(declarations)

    # A recipe takes a profile's build options, so editing its classes configures nothing.
    options = {"//app:small.gdbuild": '{"disable_3d":true}'}
    env.expect.that_dict(recipes["godot_macos_arm64_template_release"]["runtime_profiles"]).contains_exactly(options)
    env.expect.that_dict(recipes["simulation_macos_arm64_template_release"]["runtime_profiles"]).contains_exactly({})
    env.expect.that_dict(recipes["simulation_macos_arm64_editor"]["runtime_profiles"]).contains_exactly({})

def _test_a_lock_file_pins_every_recipe(env):
    declarations, errors = _plan([_module(
        "consumer",
        is_root = True,
        engine = [_engine(name = "simulation", lock_file = Label("//engines/simulation:simulation.lock.json"))],
        build = [_build(engine = "simulation")],
    )])
    env.expect.that_collection(errors).contains_exactly([])
    hub = _declared(declarations, "simulation")[0].attrs
    pins = json.decode(hub["pin_recipes"])
    env.expect.that_str(pins["@simulation_linux_x86_64_editor//:pin"]).equals("linux_x86_64_editor")
    env.expect.that_str(pins["@simulation_ios_arm64_device_template_release//:pin"]).equals("ios_arm64_device_template_release")
    env.expect.that_str(hub["lock"]).equals("engines/simulation/simulation.lock.json")
    recipe = _recipes(declarations)["simulation_macos_arm64_editor"]
    env.expect.that_str(recipe["lock_key"]).equals("macos_arm64_editor")
    env.expect.that_str(recipe["repin"]).equals("@simulation//:pin")

def _test_fork_binaries_take_no_catalogue_sources(env):
    pins = dict(
        editor_urls = {"linux_x86_64": ["file:///fork_editor.zip"]},
        editor_integrity = {"linux_x86_64": "sha256-editor"},
    )
    declarations, errors = _plan(_root(binaries = _binaries(**pins)))
    env.expect.that_collection(errors).contains_exactly([])

    # The catalogue's sources are upstream's, not the fork's, so nothing is built from them.
    env.expect.that_collection(_rules(declarations, "godot_engine_source")).contains_exactly([])
    env.expect.that_collection(_rules(declarations, "godot_engine_build")).contains_exactly([])

    # A shell pin alone, such as a prerelease's, keeps the catalogue's sources.
    declarations, errors = _plan(_root(binaries = _binaries(android_shell_urls = ["file:///shell.aar"], android_shell_integrity = "sha256-shell")))
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(_rules(declarations, "godot_engine_source")).has_size(1)

def engine_source_recipes_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_lacking_slots_build_from_the_release_sources,
            _test_tuned_runtimes_build_from_the_release_sources,
            _test_apple_official_recipes_build_without_vulkan,
            _test_prerelease_runtimes_build_from_its_sources,
            _test_a_build_policy_builds_every_slot,
            _test_binaries_beside_a_build_policy_serve,
            _test_editor_recipes_take_the_editor_policy,
            _test_source_tag_replaces_the_catalogue_sources,
            _test_engines_of_one_source_share_its_tree,
            _test_engines_of_one_archive_share_its_mirrors,
            _test_engines_of_one_archive_describe_it_alike,
            _test_runtime_profiles_reach_the_runtime_recipes_of_their_engine,
            _test_a_lock_file_pins_every_recipe,
            _test_fork_binaries_take_no_catalogue_sources,
        ],
    )
