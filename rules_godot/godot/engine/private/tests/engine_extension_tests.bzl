"""
The godot_engines extension settles engines by name and plans their hubs from tags.

Sections: Engine selection, Binaries, Built from source.
"""

load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/engine/private:extension_plan.bzl", "plan_engines")
load("//godot/private/tests:mocks.bzl", "mocks")

visibility("private")

_ENGINE = {
    "name": "godot",
    "version": "4.7.2",
    "default": False,
    "lock_file": None,
}

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

def _module(name, *, is_root = False, engine = [], source = [], binaries = [], build = [], editor = [], runtime_profile = []):
    return mocks.module(
        name,
        is_root = is_root,
        engine = engine,
        source = source,
        binaries = binaries,
        build = build,
        editor = editor,
        runtime_profile = runtime_profile,
    )

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

# ==== Engine selection ========================================================

def _test_root_request_owns_its_name(env):
    declarations, errors = _plan([
        _module("consumer", is_root = True, engine = [_engine()], build = [_build()]),
        _module("dependency", engine = [_engine(version = "4.8.0-beta1")]),
    ])
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_str(_declared(declarations, "godot_source")[0].attrs["version"]).equals("4.7.2")
    env.expect.that_collection(_rules(declarations, "engine_hub")).has_size(1)

def _test_conflicting_dependency_requests_fail(env):
    _expect_one_error(
        env,
        [
            _module("consumer", is_root = True),
            _module("dependency", engine = [_engine()], build = [_build()]),
            _module("other", engine = [_engine()]),
        ],
        'Conflicting Godot engines named "godot" from dependency and other. ' +
        "Pin one configuration with this name in the root module.",
    )

def _test_identical_dependency_requests_share_repositories(env):
    declarations, errors = _plan([
        _module("consumer", is_root = True),
        _module("first", engine = [_engine(name = "shared")]),
        _module("second", engine = [_engine(name = "shared")]),
    ])
    env.expect.that_collection(errors).contains_exactly([])
    names = [declaration.attrs["name"] for declaration in declarations]
    env.expect.that_collection(names).contains_exactly({name: None for name in names}.keys())
    env.expect.that_collection(_rules(declarations, "engine_hub")).has_size(1)
    env.expect.that_collection(_declared(declarations, "shared_templates_ios")).has_size(1)

def _test_a_module_completes_only_its_own_engines(env):
    _expect_one_error(
        env,
        [
            _module("consumer", is_root = True, binaries = [_binaries()]),
            _module("dependency", engine = [_engine()]),
        ],
        'godot_engines.binaries(engine = "godot") in consumer names no engine that module registers',
    )

def _test_each_part_of_an_engine_is_declared_once(env):
    _expect_one_error(
        env,
        [_module("consumer", is_root = True, engine = [_engine()], build = [_build(), _build()])],
        'consumer declares godot_engines.build twice for the engine "godot"',
    )
    _expect_one_error(
        env,
        [_module("consumer", is_root = True, engine = [_engine(), _engine()])],
        'consumer registers the Godot engine "godot" twice',
    )

def _test_engine_names_are_repository_and_build_names(env):
    for name in ["my-engine", "4godot", ""]:
        _expect_one_error(
            env,
            _root(name = name),
            "godot_engines.engine name %r: use letters, digits and underscores, starting with a letter" % name,
        )

def _test_one_engine_is_the_default(env):
    declarations, errors = _plan(_root(default = True))
    env.expect.that_collection(errors).contains_exactly([])
    hub = _declared(declarations, "godot")[0].attrs
    env.expect.that_str(hub["engine"]).equals("godot")
    env.expect.that_bool(hub["default_engine"]).equals(True)
    _expect_one_error(
        env,
        [_module("consumer", is_root = True, engine = [_engine(default = True), _engine(name = "other", default = True)])],
        "More than one default Godot engine: godot, other; mark one with default = True",
    )

    # The root module's default wins over a dependency's, such as an add-on module's own.
    declarations, errors = _plan([
        _module("consumer", is_root = True, engine = [_engine(name = "game", default = True)]),
        _module("addon", engine = [_engine(default = True)]),
    ])
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_bool(_declared(declarations, "game")[0].attrs["default_engine"]).equals(True)
    env.expect.that_bool(_declared(declarations, "godot")[0].attrs["default_engine"]).equals(False)

def _test_one_repository_registers_every_engine(env):
    declarations, errors = _plan([_module(
        "consumer",
        is_root = True,
        engine = [_engine(default = True), _engine(name = "simulation")],
        build = [_build(engine = "simulation")],
    )])
    env.expect.that_collection(errors).contains_exactly([])
    (toolchains,) = _declared(declarations, "godot_engines_toolchains")
    env.expect.that_str(toolchains.rule).equals("engine_toolchains")
    engines = {engine["name"]: engine for engine in json.decode(toolchains.attrs["engines"])}
    env.expect.that_collection(engines.keys()).contains_exactly(["godot", "simulation"])
    env.expect.that_bool(engines["godot"]["default_engine"]).equals(True)
    slots = {slot["name"]: slot for slot in engines["godot"]["slots"]}
    env.expect.that_bool(slots["runtime_macos_arm64_release"]["untuned_only"]).equals(True)
    env.expect.that_bool("runtime_macos_arm64_release_tuned" in slots).equals(True)

    # Without engines, the repository registers nothing.
    declarations, errors = _plan([_module("consumer", is_root = True)])
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_str(_declared(declarations, "godot_engines_toolchains")[0].attrs["engines"]).equals("[]")

# ==== Binaries ================================================================

def _test_catalogue_registers_every_template_cpu(env):
    declarations, errors = _plan(_root())
    env.expect.that_collection(errors).contains_exactly([])
    slots = _slots(declarations, "godot")
    for operating_system in ["linux", "android"]:
        for cpu in ["arm32", "arm64", "x86_32", "x86_64"]:
            name = "runtime_%s_%s_release" % (operating_system, cpu)
            env.expect.where(slot = name).that_bool(name in slots, expr = "the slot is registered").equals(True)
            if name in slots:
                env.expect.where(slot = name).that_str(slots[name]["cpu"]).equals(cpu)

def _test_catalogue_downloads_prefer_godot_cdn(env):
    declarations, errors = _plan(_root(version = "4.8.0-beta1"))
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(_declared(declarations, "godot_editor_linux_x86_64")[0].attrs["urls"]).contains_exactly([
        "https://downloads.godotengine.org/?version=4.8&flavor=beta1&slug=linux.x86_64.zip",
        "https://github.com/godotengine/godot-builds/releases/download/4.8-beta1/Godot_v4.8-beta1_linux.x86_64.zip",
    ]).in_order()
    env.expect.that_collection(_declared(declarations, "godot_templates_archive")[0].attrs["urls"]).contains_exactly([
        "https://downloads.godotengine.org/?version=4.8&flavor=beta1&slug=export_templates.tpz",
        "https://github.com/godotengine/godot-builds/releases/download/4.8-beta1/Godot_v4.8-beta1_export_templates.tpz",
    ]).in_order()
    declarations, errors = _plan(_root())
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(_declared(declarations, "godot_editor_macos")[0].attrs["urls"]).contains_exactly([
        "https://downloads.godotengine.org/?version=4.7.2&flavor=stable&slug=macos.universal.zip",
        "https://github.com/godotengine/godot-builds/releases/download/4.7.2-stable/Godot_v4.7.2-stable_macos.universal.zip",
    ]).in_order()

def _test_pinned_slots_record_artifact_integrity(env):
    debug_integrity = "sha256-" + "A" * 43 + "="
    declarations, errors = _plan(_root(binaries = _binaries(
        android_debug_shell_urls = ["file:///shell-debug.aar"],
        android_debug_shell_integrity = debug_integrity,
    )))
    env.expect.that_collection(errors).contains_exactly([])
    slots = _slots(declarations, "godot")
    env.expect.that_str(slots["runtime_android_arm64_debug"]["digest"]).equals(debug_integrity)
    env.expect.that_str(slots["runtime_android_x86_64_debug"]["digest"]).equals(debug_integrity)
    env.expect.that_str(slots["runtime_ios_arm64_device_release"]["digest"]).contains("sha512-")
    env.expect.that_collection(_declared(declarations, "godot_android_debug_shell")).has_size(1)

def _test_editor_pins_replace_catalogue_editors(env):
    declarations, errors = _plan(_root(binaries = _binaries(
        editor_urls = {"linux_x86_64": ["file:///x86_64.zip"], "linux_arm64": ["file:///arm64.zip"]},
        editor_integrity = {"linux_x86_64": "sha256-x86_64", "linux_arm64": "sha256-arm64"},
        editor_binaries = {"linux_arm64": "custom/godot"},
    )))
    env.expect.that_collection(errors).contains_exactly([])
    editors = {declaration.attrs["name"]: declaration.attrs for declaration in _rules(declarations, "godot_editor_archive")}
    env.expect.that_dict(editors).contains_exactly({
        "godot_editor_linux_arm64": {
            "name": "godot_editor_linux_arm64",
            "urls": ["file:///arm64.zip"],
            "integrity": "sha256-arm64",
            "binary": "custom/godot",
            "version": "4.7.2",
        },
        "godot_editor_linux_x86_64": {
            "name": "godot_editor_linux_x86_64",
            "urls": ["file:///x86_64.zip"],
            "integrity": "sha256-x86_64",
            # The catalogue's layout names the binary of a catalogued version.
            "binary": "Godot_v4.7.2-stable_linux.x86_64",
            "version": "4.7.2",
        },
    })
    slots = _slots(declarations, "godot")
    env.expect.that_str(slots["editor_linux_arm64"]["payload"]).equals("@godot_editor_linux_arm64//:editor")

    # Pinned editors are a fork's, whose sources the catalogue lacks: the slots they lack
    # stay empty.
    env.expect.that_bool("editor_macos_arm64" in slots).equals(False)
    env.expect.that_collection(_recipes(declarations).keys()).contains_exactly([])

def _test_template_pins_replace_catalogue_templates(env):
    pins = dict(templates_urls = ["file:///templates.tpz"], templates_integrity = "sha256-templates")
    declarations, errors = _plan(_root(binaries = _binaries(**pins)))
    env.expect.that_collection(errors).contains_exactly([])

    # One repository downloads the archive; each platform's templates have a repository
    # of their own that extracts them from it.
    archive = _declared(declarations, "godot_templates_archive")[0]
    env.expect.that_str(archive.rule).equals("http_file")
    env.expect.that_dict(archive.attrs).contains_exactly({
        "name": "godot_templates_archive",
        "urls": ["file:///templates.tpz"],
        "integrity": "sha256-templates",
        "downloaded_file_path": "export_templates.tpz",
    })
    for platform, cpus in [
        ("linux", ["arm32", "arm64", "x86_32", "x86_64"]),
        ("macos", ["universal"]),
        ("ios", []),
    ]:
        name = "godot_templates_" + platform
        env.expect.where(platform = platform).that_dict(_declared(declarations, name)[0].attrs).contains_exactly({
            "name": name,
            "archive": "@godot_templates_archive//file:export_templates.tpz",
            "integrity": "sha256-templates",
            "version": "4.7.2",
            "platform": platform,
            "cpus": cpus,
        })
    slots = _slots(declarations, "godot")
    env.expect.that_str(slots["runtime_linux_arm64_debug"]["payload"]).equals("@godot_templates_linux//:linux_arm64_debug")
    env.expect.that_str(slots["runtime_macos_x86_64_release"]["payload"]).equals("@godot_templates_macos//:macos_release")
    env.expect.that_str(slots["runtime_ios_arm64_device_debug"]["payload"]).equals("@godot_templates_ios//:ios_debug")
    declarations, errors = _plan(_root(binaries = _binaries(templates_macos_cpus = ["arm64"], **pins)))
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(_declared(declarations, "godot_templates_macos")[0].attrs["cpus"]).contains_exactly(["arm64"])
    slots = _slots(declarations, "godot")
    env.expect.that_str(slots["runtime_macos_arm64_release"]["payload"]).equals("@godot_templates_macos//:macos_arm64_release")

    # Pinned templates are a fork's: the slot they lack stays empty.
    env.expect.that_bool("runtime_macos_x86_64_release" in slots).equals(False)

def _test_shell_pins_replace_catalogue_shell(env):
    declarations, errors = _plan(_root(binaries = _binaries(
        android_shell_urls = ["file:///shell.aar"],
        android_shell_integrity = "sha256-shell",
    )))
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_dict(_declared(declarations, "godot_android_shell")[0].attrs).contains_exactly({
        "name": "godot_android_shell",
        "urls": ["file:///shell.aar"],
        "integrity": "sha256-shell",
        "downloaded_file_path": "shell.aar",
    })
    runtimes = json.decode(_declared(declarations, "godot")[0].attrs["android_runtimes"])
    env.expect.that_dict(runtimes["release"]).contains_exactly({"shell": "@godot_android_shell//file"})
    env.expect.that_str(_slots(declarations, "godot")["runtime_android_arm64_release"]["digest"]).equals("sha256-shell")

    # The pinned shell matches the engine's sources, so applications with a build profile
    # take a runtime built from them.
    env.expect.that_str(runtimes["release_tuned"]["shell"]).equals("@godot_source_android_shell//:release.aar")

def _test_templates_layout_without_templates_fails(env):
    _expect_one_error(
        env,
        _root(binaries = _binaries(templates_macos_cpus = ["arm64"])),
        'godot_engines.binaries of "godot": templates_macos_cpus describes templates_urls; set both',
    )

def _test_uncatalogued_version_without_sources_or_editors_fails(env):
    _expect_one_error(
        env,
        _root(version = "4.9.0"),
        'Godot 4.9.0 has no catalogue entry for the engine "godot"; declare its sources with ' +
        "godot_engines.source or its editors with godot_engines.binaries",
    )

def _test_uncatalogued_version_without_editor_binaries_fails(env):
    _expect_one_error(
        env,
        _root(version = "4.9.0", binaries = _binaries(
            editor_urls = {"linux_x86_64": ["file:///editor.zip"]},
            editor_integrity = {"linux_x86_64": "sha256-editor"},
        )),
        'godot_engines.binaries of "godot": editor_binaries lacks "linux_x86_64"',
    )

def _test_unknown_editor_platform_fails(env):
    _expect_one_error(
        env,
        _root(binaries = _binaries(editor_urls = {"windows_x86_64": ["file:///editor.zip"]})),
        'godot_engines.binaries of "godot": unknown editor platform "windows_x86_64"; expected one of ' +
        '["linux_arm64", "linux_x86_64", "macos", "macos_arm64", "macos_x86_64"]',
    )

def _test_pins_without_integrity_fail(env):
    for pins, message in [
        (
            {"editor_urls": {"linux_x86_64": ["file:///editor.zip"]}},
            'editor_integrity lacks "linux_x86_64"',
        ),
        (
            {"templates_urls": ["file:///templates.tpz"]},
            "templates_integrity is required with templates_urls",
        ),
        (
            {"android_shell_urls": ["file:///shell.aar"]},
            "android_shell_integrity is required with android_shell_urls",
        ),
        (
            {"android_debug_shell_urls": ["file:///shell-debug.aar"]},
            "android_debug_shell_integrity is required with android_debug_shell_urls",
        ),
    ]:
        _expect_one_error(env, _root(binaries = _binaries(**pins)), 'godot_engines.binaries of "godot": ' + message)

def _test_binaries_alone_build_nothing_from_source(env):
    pins = dict(
        editor_urls = {"linux_x86_64": ["file:///editor.zip"]},
        editor_integrity = {"linux_x86_64": "sha256-editor"},
        editor_binaries = {"linux_x86_64": "godot"},
        templates_urls = ["file:///templates.tpz"],
        templates_integrity = "sha256-templates",
    )
    declarations, errors = _plan(_root(version = "4.9.0", binaries = _binaries(**pins)))
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(_rules(declarations, "godot_engine_build")).contains_exactly([])
    env.expect.that_collection(_rules(declarations, "godot_engine_source")).contains_exactly([])
    _expect_one_error(
        env,
        _root(version = "4.9.0", lock_file = "//engines:godot.lock.json", binaries = _binaries(**pins)),
        'godot_engines.engine "godot": lock_file pins source recipes, but the engine has no sources',
    )

# ==== Built from source =======================================================

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
    source = _declared(declarations, "godot_source")
    env.expect.that_collection([declaration.rule for declaration in source]).contains_exactly(["godot_engine_source"])
    env.expect.that_str(source[0].attrs["version"]).equals("4.7.2")
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
    env.expect.that_collection(editor["patches"]).contains_exactly(["//:fork.patch"])
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
    env.expect.that_dict(_declared(declarations, "godot_source")[0].attrs).contains_exactly({
        "name": "godot_source",
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
    env.expect.that_str(_declared(declarations, "godot_source")[0].attrs["version"]).equals("4.8.0-beta")

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

def _test_runtime_profiles_need_a_registered_engine(env):
    profile = mocks.tag(profile = "//app:small.gdbuild", engine = "")
    _expect_one_error(
        env,
        [_module("consumer", is_root = True, engine = [_engine()], runtime_profile = [profile])],
        'godot_engines.runtime_profile(profile = "//app:small.gdbuild") names no engine, and no engine is the default',
    )
    _expect_one_error(
        env,
        [_module("consumer", is_root = True, engine = [_engine()], runtime_profile = [mocks.tag(profile = "//app:small.gdbuild", engine = "other")])],
        'godot_engines.runtime_profile(profile = "//app:small.gdbuild") names the engine "other", which no module registers',
    )

def _test_repositories_of_two_engines_may_not_collide(env):
    _expect_one_error(
        env,
        [_module("consumer", is_root = True, engine = [_engine(), _engine(name = "godot_source")])],
        'The Godot engines "godot" and "godot_source" both declare the repository "godot_source"; rename one',
    )
    _expect_one_error(
        env,
        _root(name = "godot_engines_toolchains"),
        'The Godot engine "godot_engines_toolchains" and godot_engines both declare the repository "godot_engines_toolchains"; rename the engine',
    )

def engine_extension_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_root_request_owns_its_name,
            _test_conflicting_dependency_requests_fail,
            _test_identical_dependency_requests_share_repositories,
            _test_a_module_completes_only_its_own_engines,
            _test_each_part_of_an_engine_is_declared_once,
            _test_engine_names_are_repository_and_build_names,
            _test_one_engine_is_the_default,
            _test_one_repository_registers_every_engine,
            _test_catalogue_registers_every_template_cpu,
            _test_catalogue_downloads_prefer_godot_cdn,
            _test_pinned_slots_record_artifact_integrity,
            _test_editor_pins_replace_catalogue_editors,
            _test_template_pins_replace_catalogue_templates,
            _test_shell_pins_replace_catalogue_shell,
            _test_templates_layout_without_templates_fails,
            _test_uncatalogued_version_without_sources_or_editors_fails,
            _test_uncatalogued_version_without_editor_binaries_fails,
            _test_unknown_editor_platform_fails,
            _test_pins_without_integrity_fail,
            _test_binaries_alone_build_nothing_from_source,
            _test_lacking_slots_build_from_the_release_sources,
            _test_tuned_runtimes_build_from_the_release_sources,
            _test_apple_official_recipes_build_without_vulkan,
            _test_prerelease_runtimes_build_from_its_sources,
            _test_a_build_policy_builds_every_slot,
            _test_binaries_beside_a_build_policy_serve,
            _test_editor_recipes_take_the_editor_policy,
            _test_source_tag_replaces_the_catalogue_sources,
            _test_runtime_profiles_reach_the_runtime_recipes_of_their_engine,
            _test_a_lock_file_pins_every_recipe,
            _test_fork_binaries_take_no_catalogue_sources,
            _test_runtime_profiles_need_a_registered_engine,
            _test_repositories_of_two_engines_may_not_collide,
        ],
    )
