"""
The godot_engines extension settles engines by name and plans their hubs from tags.

Sections: Engine selection, Binaries.
"""

load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/private/tests:mocks.bzl", "mocks")
load(":engine_extension_fixtures.bzl", "extension")

visibility("private")

_engine = extension.engine
_binaries = extension.binaries
_build = extension.build
_module = extension.module
_root = extension.root
_plan = extension.plan
_declared = extension.declared
_rules = extension.rules
_slots = extension.slots
_recipes = extension.recipes
_expect_one_error = extension.expect_one_error
_RELEASE_SOURCE = extension.RELEASE_SOURCE

# ==== Engine selection ========================================================

def _test_root_request_owns_its_name(env):
    declarations, errors = _plan([
        _module("consumer", is_root = True, engine = [_engine()], build = [_build()]),
        _module("dependency", engine = [_engine(version = "4.8.0-beta1")]),
    ])
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_str(_declared(declarations, _RELEASE_SOURCE)[0].attrs["version"]).equals("4.7.2")
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
        [_module("consumer", is_root = True, engine = [_engine(), _engine(name = "godot_source_android_shell")])],
        'The Godot engines "godot" and "godot_source_android_shell" both declare the repository "godot_source_android_shell"; rename one',
    )
    _expect_one_error(
        env,
        _root(name = "godot_engines_toolchains"),
        'The Godot engine "godot_engines_toolchains" and godot_engines both declare the repository "godot_engines_toolchains"; rename the engine',
    )

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
            _test_runtime_profiles_need_a_registered_engine,
            _test_repositories_of_two_engines_may_not_collide,
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
        ],
    )
