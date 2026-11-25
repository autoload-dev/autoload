"""The godot_engines extension settles requests by name and plans hubs from tags."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")

# buildifier: disable=bzl-visibility
load("//godot/engine/private:extension_plan.bzl", "plan_engines")

# buildifier: disable=bzl-visibility
load("//godot/engine/private:source_build_rows.bzl", "plan_rows", "select_rows")

# buildifier: disable=bzl-visibility
load("//godot/private/tests:mocks.bzl", "mocks")

_PREBUILT = {
    "name": "godot",
    "version": "4.7.2",
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
    "source_runtimes": True,
    "engine": "",
}

_SOURCE = {
    "name": "godot_sources",
    "urls": ["file:///godot.tar.gz"],
    "sha256": "0" * 64,
    "strip_prefix": "godot",
    "version": "4.7.2",
}

_SOURCE_BUILD = {
    "name": "godot_source_build",
    "source": "@godot_sources//:source.json",
    "platforms": ["android", "macos"],
    "cpus": ["arm64"],
    "build_targets": ["template_release"],
    "ios_environments": [],
    "enabled_modules": ["gdscript", "text_server_fb"],
    "default_modules": False,
    "custom_modules": {},
    "patches": [],
    "patch_strip": 1,
    "build_options": {},
    "build_name": "custom",
    "python": None,
    "configure_timeout": 600,
    "lock_file": None,
    "engine": "",
}

_TAG_ATTRIBUTES = {
    "prebuilt": _PREBUILT.keys(),
    "source": _SOURCE.keys(),
    "source_build": _SOURCE_BUILD.keys(),
}

def _prebuilt(**overrides):
    return mocks.tag(**(_PREBUILT | overrides))

def _source(**overrides):
    return mocks.tag(**(_SOURCE | overrides))

def _source_build(**overrides):
    return mocks.tag(**(_SOURCE_BUILD | overrides))

def _module(name, *, is_root = False, prebuilt = [], source = [], source_build = [], runtime_profile = []):
    return mocks.module(
        name,
        is_root = is_root,
        prebuilt = prebuilt,
        source = source,
        source_build = source_build,
        runtime_profile = runtime_profile,
    )

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

def _slots(declarations, hub):
    return {slot["name"]: slot for slot in json.decode(_declared(declarations, hub)[0].attrs["components"])}

def _test_root_request_owns_its_name(env):
    declarations, errors = _plan([
        _module("consumer", is_root = True, source_build = [_source_build()]),
        _module("dependency", prebuilt = [_prebuilt(name = "godot_source_build", version = "4.8.0-beta1")]),
    ])
    env.expect.that_collection(errors).contains_exactly([])
    owners = _declared(declarations, "godot_source_build")
    env.expect.that_collection([declaration.rule for declaration in owners]).contains_exactly(
        ["godot_engine_source_build"],
    )
    env.expect.that_collection(owners[0].attrs["platforms"]).contains_exactly(["android", "macos"])

def _test_conflicting_dependency_requests_fail(env):
    _, errors = _plan([
        _module("consumer", is_root = True),
        _module("dependency", source_build = [_source_build()]),
        _module("other", prebuilt = [_prebuilt(name = "godot_source_build", version = "4.8.0-beta1")]),
    ])
    env.expect.that_collection(errors).has_size(1)
    env.expect.that_str(errors[0]).contains('Conflicting Godot requests named "godot_source_build"')

def _test_templates_layout_without_templates_fails(env):
    _, errors = _plan([
        _module("consumer", is_root = True, prebuilt = [_prebuilt(name = "godot_layout", templates_macos_cpus = ["arm64"])]),
    ])
    env.expect.that_collection(errors).has_size(1)
    env.expect.that_str(errors[0]).contains("templates_macos_cpus describes templates_urls")

def _test_pinned_slots_record_artifact_integrity(env):
    debug_integrity = "sha256-" + "A" * 43 + "="
    declarations, errors = _plan([
        _module("consumer", is_root = True, prebuilt = [_prebuilt(
            name = "godot_pinned",
            android_debug_shell_urls = ["file:///shell-debug.aar"],
            android_debug_shell_integrity = debug_integrity,
        )]),
    ])
    env.expect.that_collection(errors).contains_exactly([])
    slots = _slots(declarations, "godot_pinned")
    env.expect.that_str(slots["runtime_android_arm64_debug"]["digest"]).equals(debug_integrity)
    env.expect.that_str(slots["runtime_android_x86_64_debug"]["digest"]).equals(debug_integrity)
    env.expect.that_str(slots["runtime_ios_arm64_device_release"]["digest"]).contains("sha512-")
    env.expect.that_collection(_declared(declarations, "godot_pinned_android_debug_shell")).has_size(1)

def _test_catalogue_registers_every_template_cpu(env):
    declarations, errors = _plan([
        _module("consumer", is_root = True, prebuilt = [_prebuilt(name = "godot_catalogued")]),
    ])
    env.expect.that_collection(errors).contains_exactly([])
    slots = _slots(declarations, "godot_catalogued")
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

def _test_source_build_hub_names_each_recipe(env):
    plan = plan_rows("godot_source_build", select_rows("godot_source_build", ["android", "macos"], cpus = ["arm64"], build_targets = ["template_release"]))
    env.expect.that_collection([slot["name"] for slot in plan.slots]).contains_exactly([
        "runtime_android_arm64_release",
        "runtime_macos_arm64_release",
    ])
    slots = {slot["name"]: slot for slot in plan.slots}
    env.expect.that_str(slots["runtime_macos_arm64_release"]["payload"]).equals(
        "@godot_source_build_macos_arm64_template_release//:godot",
    )
    env.expect.that_str(slots["runtime_android_arm64_release"]["payload"]).equals("//android:release")
    env.expect.that_dict(plan.android["release"]["engine_libraries"]).contains_exactly({
        "arm64": "@godot_source_build_android_arm64_template_release//:godot",
    })
    env.expect.that_collection([recipe.repository for recipe in plan.recipes]).contains_exactly([
        "godot_source_build_android_arm64_template_release",
        "godot_source_build_macos_arm64_template_release",
    ])

def _root(**overrides):
    return [_module("consumer", is_root = True, prebuilt = [_prebuilt(**overrides)])]

def _rules(declarations, rule):
    return [declaration for declaration in declarations if declaration.rule == rule]

def _test_editor_pins_replace_catalogue_editors(env):
    declarations, errors = _plan(_root(
        editor_urls = {"linux_x86_64": ["file:///x86_64.zip"], "linux_arm64": ["file:///arm64.zip"]},
        editor_integrity = {"linux_x86_64": "sha256-x86_64", "linux_arm64": "sha256-arm64"},
        editor_binaries = {"linux_arm64": "custom/godot"},
    ))
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
    editor_slots = [name for name in _slots(declarations, "godot") if name.startswith("editor_")]
    env.expect.that_collection(editor_slots).contains_exactly(["editor_linux_arm64", "editor_linux_x86_64"])

def _test_template_pins_replace_catalogue_templates(env):
    declarations, errors = _plan(_root(templates_urls = ["file:///templates.tpz"], templates_integrity = "sha256-templates"))
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
    declarations, errors = _plan(_root(
        templates_urls = ["file:///templates.tpz"],
        templates_integrity = "sha256-templates",
        templates_macos_cpus = ["arm64"],
        source_runtimes = False,
    ))
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(_declared(declarations, "godot_templates_macos")[0].attrs["cpus"]).contains_exactly(["arm64"])
    slots = _slots(declarations, "godot")
    env.expect.that_str(slots["runtime_macos_arm64_release"]["payload"]).equals("@godot_templates_macos//:macos_arm64_release")
    env.expect.that_bool("runtime_macos_x86_64_release" in slots).equals(False)
    declarations, errors = _plan(_root(
        templates_urls = ["file:///templates.tpz"],
        templates_integrity = "sha256-templates",
        templates_linux_cpus = ["x86_64"],
        source_runtimes = False,
    ))
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(_declared(declarations, "godot_templates_linux")[0].attrs["cpus"]).contains_exactly(["x86_64"])
    linux = [name for name in _slots(declarations, "godot") if name.startswith("runtime_linux_")]
    env.expect.that_collection(linux).contains_exactly(["runtime_linux_x86_64_debug", "runtime_linux_x86_64_release"])

def _test_shell_pins_replace_catalogue_shell(env):
    declarations, errors = _plan(_root(
        android_shell_urls = ["file:///shell.aar"],
        android_shell_integrity = "sha256-shell",
        source_runtimes = False,
    ))
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_dict(_declared(declarations, "godot_android_shell")[0].attrs).contains_exactly({
        "name": "godot_android_shell",
        "urls": ["file:///shell.aar"],
        "integrity": "sha256-shell",
        "downloaded_file_path": "shell.aar",
    })
    hub = _declared(declarations, "godot")[0].attrs
    env.expect.that_dict(json.decode(hub["android_runtimes"])).contains_exactly({
        "release": {"shell": "@godot_android_shell//file"},
    })
    env.expect.that_str(_slots(declarations, "godot")["runtime_android_arm64_release"]["digest"]).equals("sha256-shell")

def _expect_one_error(env, modules, message):
    declarations, errors = _plan(modules)
    env.expect.where(expected = message).that_collection(errors).contains_exactly([message])
    env.expect.where(expected = message).that_bool(declarations == None).equals(True)

def _test_uncatalogued_version_without_pins_fails(env):
    _expect_one_error(
        env,
        _root(version = "4.9.0"),
        "Godot 4.9.0 has no built-in pins; set editor_urls/editor_integrity/editor_binaries " +
        'and templates_urls/templates_integrity on godot_engines.prebuilt(name = "godot")',
    )

def _test_uncatalogued_version_without_template_pins_fails(env):
    _expect_one_error(
        env,
        _root(
            version = "4.9.0",
            editor_urls = {"linux_x86_64": ["file:///editor.zip"]},
            editor_integrity = {"linux_x86_64": "sha256-editor"},
            editor_binaries = {"linux_x86_64": "godot"},
        ),
        'godot_engines.prebuilt "godot": Godot 4.9.0 needs templates_urls and templates_integrity',
    )

def _test_uncatalogued_version_without_editor_binaries_fails(env):
    _expect_one_error(
        env,
        _root(
            version = "4.9.0",
            editor_urls = {"linux_x86_64": ["file:///editor.zip"]},
            editor_integrity = {"linux_x86_64": "sha256-editor"},
        ),
        'godot_engines.prebuilt "godot": editor_binaries lacks "linux_x86_64"',
    )

def _test_unknown_editor_platform_fails(env):
    _expect_one_error(
        env,
        _root(editor_urls = {"windows_x86_64": ["file:///editor.zip"]}),
        'godot_engines.prebuilt "godot": unknown editor platform "windows_x86_64"; expected one of ' +
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
        _expect_one_error(env, _root(**pins), 'godot_engines.prebuilt "godot": ' + message)

def _test_source_tag_declares_engine_source(env):
    declarations, errors = _plan([_module("consumer", is_root = True, source = [_source()])])
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection([declaration.rule for declaration in declarations]).contains_exactly(
        ["godot_engine_source"],
    )
    env.expect.that_dict(declarations[0].attrs).contains_exactly(_SOURCE)

def _test_identical_dependency_requests_share_repositories(env):
    declarations, errors = _plan([
        _module("consumer", is_root = True),
        _module("first", prebuilt = [_prebuilt(name = "godot_shared")]),
        _module("second", prebuilt = [_prebuilt(name = "godot_shared")]),
    ])
    env.expect.that_collection(errors).contains_exactly([])
    names = [declaration.attrs["name"] for declaration in declarations]
    env.expect.that_collection(names).contains_exactly({name: None for name in names}.keys())
    env.expect.that_collection(_rules(declarations, "engine_hub")).has_size(1)
    env.expect.that_collection(_declared(declarations, "godot_shared_templates_ios")).has_size(1)

def _test_tags_name_the_engine_of_their_hubs(env):
    declarations, errors = _plan([_module(
        "consumer",
        is_root = True,
        prebuilt = [_prebuilt(engine = "stock")],
        source_build = [_source_build(engine = "petri")],
    )])
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_str(_declared(declarations, "godot")[0].attrs["engine"]).equals("stock")
    env.expect.that_str(_declared(declarations, "godot_source_build")[0].attrs["engine"]).equals("petri")

def _test_source_builds_take_the_version_of_their_source_tag(env):
    declarations, errors = _plan([_module(
        "consumer",
        is_root = True,
        source = [_source()],
        source_build = [_source_build(), _source_build(name = "godot_foreign", source = "@foreign_sources//:source.json")],
    )])
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_str(_declared(declarations, "godot_source_build")[0].attrs["version"]).equals("4.7.2")
    env.expect.that_str(_declared(declarations, "godot_foreign")[0].attrs["version"]).equals("")

def _test_profiled_runtimes_build_from_the_release_sources(env):
    declarations, errors = _plan(_root())
    env.expect.that_collection(errors).contains_exactly([])
    slots = _slots(declarations, "godot")

    # The prebuilt runtime serves applications without a build profile, a source-built one the others.
    env.expect.that_bool(slots["runtime_macos_arm64_release"]["without_build_profile"]).equals(True)
    profiled = slots["runtime_macos_arm64_release_profiled"]
    env.expect.that_bool(profiled["without_build_profile"]).equals(False)
    env.expect.that_str(profiled["payload"]).equals("@godot__source_macos_arm64_template_release//:godot")
    env.expect.that_str(slots["runtime_android_arm64_release_profiled"]["payload"]).equals("//android:release_profiled")

    # Slots the artifacts lack serve every application.
    env.expect.that_bool(slots["runtime_ios_arm64_simulator_release"]["without_build_profile"]).equals(False)
    env.expect.that_bool("runtime_ios_arm64_simulator_release_profiled" in slots).equals(False)
    hub = _declared(declarations, "godot")[0].attrs
    env.expect.that_collection(json.decode(hub["android_runtimes"]).keys()).contains_exactly(
        ["debug", "release", "release_profiled"],
    )

def _test_runtime_profiles_reach_the_runtime_recipes_of_their_engine(env):
    declarations, errors = _plan([_module(
        "consumer",
        is_root = True,
        prebuilt = [_prebuilt()],
        source = [_source()],
        source_build = [
            _source_build(build_targets = ["editor", "template_release"]),
            _source_build(name = "godot_petri", engine = "petri"),
        ],
        runtime_profile = [
            mocks.tag(profile = "//app:small.gdbuild", engine = ""),
            # Classes alone need no runtime variant.
            mocks.tag(profile = "//app:classes.gdbuild", engine = ""),
        ],
    )])
    env.expect.that_collection(errors).contains_exactly([])
    build = _declared(declarations, "godot_source_build")[0].attrs

    # A recipe takes a profile's build options, so editing its classes configures nothing.
    options = {"//app:small.gdbuild": '{"disable_3d":true}'}
    env.expect.that_dict(build["runtime_profiles"]).contains_exactly(options)
    env.expect.that_dict(_declared(declarations, "godot_petri")[0].attrs["runtime_profiles"]).contains_exactly({})
    recipe = _declared(declarations, "godot__source_macos_arm64_template_release")[0].attrs
    env.expect.that_dict(recipe["runtime_profiles"]).contains_exactly(options)

# Apple's source-built runtimes declare their rendering methods, without Vulkan, which would
# need the MoltenVK SDK on the configuring Mac; applications check their project's method.
def _test_apple_source_runtimes_build_without_vulkan(env):
    declarations, errors = _plan(_root())
    env.expect.that_collection(errors).contains_exactly([])
    for declaration in _rules(declarations, "godot_engine_build"):
        platform = declaration.attrs["platform"]
        expected = ["gl_compatibility", "mobile", "forward_plus"] if platform in ["ios", "macos"] else []
        expect = env.expect.where(recipe = declaration.attrs["name"])
        expect.that_collection(declaration.attrs["renderers"]).contains_exactly(expected)
        expect.that_dict(declaration.attrs["build_options"]).contains_exactly({})

def _test_lacking_slots_build_from_the_release_sources(env):
    declarations, errors = _plan(_root())
    env.expect.that_collection(errors).contains_exactly([])
    slots = _slots(declarations, "godot")

    # The official simulator libraries are x86_64 only, and the official shells are release builds.
    env.expect.that_str(slots["runtime_ios_x86_64_simulator_release"]["payload"]).equals("@godot_templates_ios//:ios_release")
    env.expect.that_str(slots["runtime_ios_arm64_simulator_release"]["payload"]).equals(
        "@godot__source_ios_arm64_simulator_template_release//:engine_library",
    )
    env.expect.that_str(slots["runtime_ios_arm64_simulator_debug"]["version"]).equals("4.7.2")
    env.expect.that_str(slots["runtime_android_arm64_debug"]["payload"]).equals("//android:debug")
    env.expect.that_str(slots["runtime_ios_arm64_device_release"]["payload"]).equals("@godot_templates_ios//:ios_release")
    source = _declared(declarations, "godot__source_archive")
    env.expect.that_collection([declaration.rule for declaration in source]).contains_exactly(["godot_engine_source"])
    env.expect.that_str(source[0].attrs["version"]).equals("4.7.2")
    recipes = [declaration.attrs["name"] for declaration in _rules(declarations, "godot_engine_build")]
    env.expect.that_collection(recipes).contains_at_least([
        "godot__source_android_arm64_template_debug",
        "godot__source_android_x86_64_template_debug",
        "godot__source_ios_arm64_simulator_template_debug",
        "godot__source_ios_arm64_simulator_template_release",
    ])
    env.expect.that_collection(_declared(declarations, "godot__source_android_shell")).has_size(1)

def _test_source_runtimes_can_be_left_unbuilt(env):
    declarations, errors = _plan(_root(source_runtimes = False))
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(_rules(declarations, "godot_engine_build")).contains_exactly([])
    env.expect.that_bool("runtime_ios_arm64_simulator_release" in _slots(declarations, "godot")).equals(False)

def _test_pinned_runtimes_need_source_builds_only_for_build_profiles(env):
    declarations, errors = _plan(_root(
        ios_simulator_cpus = ["arm64", "x86_64"],
        android_debug_shell_urls = ["file:///shell-debug.aar"],
        android_debug_shell_integrity = "sha256-" + "A" * 43 + "=",
    ))
    env.expect.that_collection(errors).contains_exactly([])
    slots = _slots(declarations, "godot")
    source_built = [
        name
        for name, slot in slots.items()
        if slot["payload"].startswith("@godot__source_") or slot["payload"].endswith("_profiled")
    ]
    env.expect.that_bool(all([name.endswith("_profiled") for name in source_built])).equals(True)

def _test_pinned_artifacts_build_no_upstream_runtimes(env):
    declarations, errors = _plan(_root(
        templates_urls = ["file:///fork_templates.tpz"],
        templates_integrity = "sha256-" + "A" * 43 + "=",
    ))
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(_rules(declarations, "godot_engine_build")).contains_exactly([])

def _test_pinned_shells_build_no_upstream_android_runtimes(env):
    declarations, errors = _plan(_root(
        android_shell_urls = ["file:///fork_shell.aar"],
        android_shell_integrity = "sha256-" + "A" * 43 + "=",
    ))
    env.expect.that_collection(errors).contains_exactly([])
    recipes = [declaration.attrs["name"] for declaration in _rules(declarations, "godot_engine_build")]
    env.expect.that_bool(any([recipe.startswith("godot__source_android") for recipe in recipes])).equals(False)
    env.expect.that_collection(recipes).contains_at_least([
        "godot__source_ios_arm64_simulator_template_debug",
        "godot__source_ios_arm64_simulator_template_release",
    ])

def _test_prerelease_simulator_runtimes_build_from_its_sources(env):
    declarations, errors = _plan(_root(name = "godot_beta", version = "4.8.0-beta1"))
    env.expect.that_collection(errors).contains_exactly([])
    slots = _slots(declarations, "godot_beta")
    env.expect.that_str(slots["runtime_ios_arm64_simulator_release"]["version"]).equals("4.8.0-beta")
    env.expect.that_str(slots["runtime_ios_arm64_simulator_release"]["payload"]).equals(
        "@godot_beta__source_ios_arm64_simulator_template_release//:engine_library",
    )

def engine_extension_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_apple_source_runtimes_build_without_vulkan,
            _test_root_request_owns_its_name,
            _test_conflicting_dependency_requests_fail,
            _test_templates_layout_without_templates_fails,
            _test_pinned_slots_record_artifact_integrity,
            _test_catalogue_registers_every_template_cpu,
            _test_catalogue_downloads_prefer_godot_cdn,
            _test_source_build_hub_names_each_recipe,
            _test_source_builds_take_the_version_of_their_source_tag,
            _test_editor_pins_replace_catalogue_editors,
            _test_template_pins_replace_catalogue_templates,
            _test_shell_pins_replace_catalogue_shell,
            _test_uncatalogued_version_without_pins_fails,
            _test_uncatalogued_version_without_template_pins_fails,
            _test_uncatalogued_version_without_editor_binaries_fails,
            _test_unknown_editor_platform_fails,
            _test_pins_without_integrity_fail,
            _test_source_tag_declares_engine_source,
            _test_identical_dependency_requests_share_repositories,
            _test_tags_name_the_engine_of_their_hubs,
            _test_lacking_slots_build_from_the_release_sources,
            _test_profiled_runtimes_build_from_the_release_sources,
            _test_runtime_profiles_reach_the_runtime_recipes_of_their_engine,
            _test_source_runtimes_can_be_left_unbuilt,
            _test_pinned_runtimes_need_source_builds_only_for_build_profiles,
            _test_pinned_artifacts_build_no_upstream_runtimes,
            _test_pinned_shells_build_no_upstream_android_runtimes,
            _test_prerelease_simulator_runtimes_build_from_its_sources,
        ],
    )
