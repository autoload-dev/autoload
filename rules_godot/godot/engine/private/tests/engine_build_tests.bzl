"""godot_engine_build links one recipe to its engine tree and passes it to the configure-only capture."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/engine/private:source_repositories.bzl", "engine_build_impl", "profile_options")
load("//godot/private/tests:copyright_excerpt.bzl", "COPYRIGHT_EXCERPT")
load("//godot/private/tests:mocks.bzl", "mocks")

visibility("private")

_TREE = Label("//godot/engine/private/tests:tree.json")
_TREE_DIRECTORY = str(_TREE).rpartition("/")[0]
_ARCHIVE = "@@godot_sources//:source.tar.gz"
_PATCH_LABEL = "@@//engines:fork.patch"
_SHA256 = "e954996374cbd1cb5d72e0e3781cc537408e6ce73b010b12c6c2f308a820690a"
_PYTHON = "/usr/bin/python3"

# The variables Godot's configuration reads, watched before anything else.
_CONFIGURE_ENVIRONMENT = [
    "APPLE_LLVM_CROSS",
    "CCACHE",
    "GODOT_VERSION_STATUS",
    "MACPORTS_PREFIX",
    "OSXCROSS_IOS",
    "OSXCROSS_ROOT",
    "PKG_CONFIG_PATH",
]

_ATTRS = {
    "name": "godot_linux_x86_64_template_release",
    "tree": _TREE,
    "patches": [],
    "patch_strip": 1,
    "platform": "linux",
    "cpu": "x86_64",
    "build_target": "template_release",
    "environment": "",
    "enabled_modules": ["gdscript", "text_server_fb"],
    "default_modules": False,
    "custom_modules": {},
    "renderers": [],
    "build_options": {},
    "build_name": "custom",
    "_configure": "rules_godot/tools/engine/configure.py",
    "_compile_options": "rules_godot/tools/engine/compile_options.py",
    "_generator_inputs": "rules_godot/tools/engine/generator_inputs.py",
    "_lock": "rules_godot/tools/engine/lock.py",
    "_recipe_options": "rules_godot/tools/engine/recipe_options.py",
    "_python": _PYTHON,
    "_module_graph": "rules_godot/tools/engine/module_graph.py",
    "_include_graph": "rules_godot/tools/engine/include_graph.py",
    "_render": "rules_godot/tools/engine/render.py",
    "_build_profile": "rules_godot/tools/engine/build_profile.py",
    "_define_analysis": "rules_godot/tools/engine/define_analysis.py",
    "_source_tree": "rules_godot/tools/engine/source_tree.py",
    "_variants": "rules_godot/tools/engine/variants.py",
    "_generators": "rules_godot/tools/engine/generators.py",
    "_build_file": "rules_godot/tools/engine/build_file.py",
    "_custom_modules": "rules_godot/tools/engine/custom_modules.py",
    "_tree": "rules_godot/tools/engine/tree.py",
    "_tree_link": "rules_godot/tools/engine/tree_link.py",
    "_class_db": "rules_godot/tools/engine/class_db.py",
    "_patches": "rules_godot/tools/engine/patches.py",
    "_build_profile_label": "@@//godot/private:build_profile_label",
    "_generator": "@@//godot/engine/private:generator.bzl",
    "_cc_rules": "@@rules_cc+//cc:cc_library.bzl",
    "_platforms_constraint": "@@platforms//os:android",
    "_apple_constraint": "@@apple_support+//constraints:device",
    "_swift_library": "@@rules_swift+//swift:swift_library.bzl",
    "_pin_bzl": "@@//godot/engine/private:pin.bzl",
    "lock_file": None,
    "lock_key": "",
    "repin": "",
    "runtime_profiles": {},
}

# The recipe watches each of its .py tool attributes once, so the count follows them.
_TOOL_WATCHES = ["watch"] * len([
    path
    for path in _ATTRS.values()
    if type(path) == "string" and path.endswith(".py")
])

def _tree_json():
    return json.encode({
        "archive": _ARCHIVE,
        "sha256": _SHA256,
        "strip_prefix": "godot-4.7.2-stable",
        "version": "4.7.2",
        "digest": "0" * 64,
    })

# Godot's license text and COPYRIGHT.txt in the engine tree, beside its descriptor.
_LICENSE = mocks.path(_TREE).dirname + "/LICENSE.txt"
_COPYRIGHT = mocks.path(_TREE).dirname + "/COPYRIGHT.txt"

def _paths(path):
    """Bazel's paths: a struct for the tree descriptor, whose directory the recipe links."""
    mapping = path or str
    return lambda value: mocks.path(value) if str(value) in (str(_TREE), _LICENSE, _COPYRIGHT) else mapping(value)

def _build(*, execute = {}, path = None, environ = {}, files = {}, tree = None, **overrides):
    ctx = mocks.repository_ctx(
        attr = _ATTRS | overrides,
        files = {
            str(_TREE): tree or _tree_json(),
            _LICENSE: "Copyright (c) Godot Engine contributors.",
            _COPYRIGHT: COPYRIGHT_EXCERPT,
        } | files,
        execute = execute,
        path = _paths(path),
        environ = environ,
    )
    errors, fail_ = mocks.errors()
    engine_build_impl(ctx, _fail = fail_)
    return ctx, errors

def _configure(ctx):
    """The configure call."""
    calls = [call for call in mocks.calls(ctx, "execute") if call.args[1:4] == ["-P", "-m", "tools.engine.configure"]]
    return calls[0] if calls else None

def _options(arguments):
    return [arguments[i + 1] for i in range(len(arguments)) if arguments[i] == "--option"]

# The configure command of the recipe _test_configure_command_carries_the_recipe declares.
_CONFIGURE_COMMAND = [
    _PYTHON,
    "-P",
    "-m",
    "tools.engine.configure",
    "--source",
    ".",
    "--scons",
    "_scons",
    "--generator-bzl",
    "@@//godot/engine/private:generator.bzl",
    "--cc-repository",
    "@@rules_cc+",
    "--platforms-repository",
    "@@platforms",
    "--apple-repository",
    "@@apple_support+",
    "--swift-repository",
    "@@rules_swift+",
    "--platform",
    "linuxbsd",
    "--cpu",
    "x86_64",
    "--build-target",
    "template_release",
    "--environment",
    "",
    "--expected-version",
    "4.7.2",
    "--modules",
    "gdscript,svg",
    "--build-name",
    "studio",
    "--source-sha256",
    _SHA256,
    "--patch-strip",
    "2",
    "--patch",
    _PATCH_LABEL,
    # The settings a recipe with runtime variants selects them on, here without any.
    "--build-profile-label",
    "@@//godot/private:build_profile_label",
]

def _test_configure_command_carries_the_recipe(env):
    ctx, errors = _build(
        enabled_modules = ["gdscript", "svg"],
        build_name = "studio",
        patches = [_PATCH_LABEL],
        patch_strip = 2,
    )
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection([call.method for call in ctx.calls]).contains_exactly(
        _TOOL_WATCHES + ["getenv"] * len(_CONFIGURE_ENVIRONMENT) + [
            "watch",
            "execute",
            "execute",
            "delete",
            # REPO.bazel, the license text, the four bundled libraries' texts and the
            # metadata's BUILD file, then WORKSPACE.bazel.
        ] + ["file"] * 8,
    ).in_order()
    env.expect.that_str(mocks.calls(ctx, "delete")[0].path).equals(".scons_env.json")

    # The recipe patches its own copies of the files its patches touch, and its pin digest
    # covers the patches.
    env.expect.that_collection(mocks.calls(ctx, "execute")[0].args).contains_exactly([
        _PYTHON,
        "-P",
        "-m",
        "tools.engine.tree_link",
        "--tree",
        _TREE_DIRECTORY,
        "--recipe",
        ".",
        "--path",
        "",
        "--patch-strip",
        "2",
        "--patch",
        _PATCH_LABEL,
    ]).in_order()
    env.expect.that_collection([call.path for call in mocks.calls(ctx, "watch")]).contains(_PATCH_LABEL)
    env.expect.that_collection(mocks.calls(ctx, "extract")).contains_exactly([])
    env.expect.that_collection(mocks.calls(ctx, "download_and_extract")).contains_exactly([])
    env.expect.that_collection(_configure(ctx).args).contains_exactly(_CONFIGURE_COMMAND).in_order()
    env.expect.that_collection([call.path for call in mocks.calls(ctx, "file")]).contains_exactly([
        "WORKSPACE.bazel",
        "REPO.bazel",
        "_package_metadata/LICENSE",
        "_package_metadata/BUILD.bazel",
        # The libraries the tree's COPYRIGHT.txt lists, each a package of its own.
        "_package_metadata/bullet_continuous_collision_detection_and_physics_library.txt",
        "_package_metadata/servers_audio_effects_audio_effect_pitch_shift_cpp.txt",
        "_package_metadata/smol_v.txt",
        "_package_metadata/zlib.txt",
    ])

# A recipe holds its generated files and links the engine tree's sources hard: no recipe
# extracts them again.
def _test_a_recipe_links_its_engine_tree(env):
    ctx, errors = _build()
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(mocks.calls(ctx, "execute")[0].args).contains_exactly(
        [_PYTHON, "-P", "-m", "tools.engine.tree_link", "--tree", _TREE_DIRECTORY, "--recipe", ".", "--path", "", "--patch-strip", "1"],
    ).in_order()
    env.expect.that_collection([call.path for call in mocks.calls(ctx, "watch")]).contains_at_least([
        "rules_godot/tools/engine/tree.py",
        "rules_godot/tools/engine/tree_link.py",
        "rules_godot/tools/engine/class_db.py",
    ])

def _test_a_failed_link_fails(env):
    ctx, errors = _build(execute = {_PYTHON + " -P -m tools.engine.tree_link": {"return_code": 1, "stderr": "denied"}})
    env.expect.that_collection(errors).contains_exactly([
        "godot_linux_x86_64_template_release: linking the engine tree failed:\n\ndenied",
    ])
    env.expect.that_bool(_configure(ctx) == None).equals(True)

def _test_build_options_become_sorted_options(env):
    ctx, errors = _build(build_options = {"production": "yes", "lto": "full", "builtin_zlib": "no"})
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(_options(_configure(ctx).args)).contains_exactly(
        ["builtin_zlib=no", "lto=full", "production=yes"],
    ).in_order()

def _test_scons_platform_follows_the_recipe_platform(env):
    for platform, scons, environment in [
        ("linux", "linuxbsd", ""),
        ("macos", "macos", ""),
        ("android", "android", ""),
        ("ios", "ios", "simulator"),
    ]:
        ctx, errors = _build(platform = platform, environment = environment)
        env.expect.where(platform = platform).that_collection(errors).contains_exactly([])
        arguments = _configure(ctx).args
        env.expect.where(platform = platform).that_str(arguments[arguments.index("--platform") + 1]).equals(scons)
        env.expect.where(platform = platform).that_str(arguments[arguments.index("--environment") + 1]).equals(environment)

def _test_import_env_vars_are_read(env):
    ctx, errors = _build(
        build_options = {"import_env_vars": "VULKAN_SDK,,CCACHE"},
        environ = {"VULKAN_SDK": "/sdk"},
    )
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection([call.variable for call in mocks.calls(ctx, "getenv")]).contains_exactly(
        _CONFIGURE_ENVIRONMENT + ["VULKAN_SDK", "CCACHE"],
    ).in_order()
    env.expect.that_collection(_options(_configure(ctx).args)).contains_exactly(
        ["import_env_vars=VULKAN_SDK,,CCACHE"],
    )

def _test_default_modules_reach_configure(env):
    ctx, errors = _build(default_modules = True)
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(_configure(ctx).args).contains("--default-modules")
    ctx, errors = _build()
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(_configure(ctx).args).not_contains("--default-modules")

_RIVE = Label("//third_party/rive:rive")

# What custom_modules.py prints for the rive module: what the recipe watches, and the
# placeholders of its code.
_PREPARED = json.encode({
    "modules": {"rive": {"directories": [".", "shaders"], "files": ["SCsub", "config.py"]}},
    "placeholders": ["_custom_modules/rive/rive.cpp"],
})

def _module_paths(listings, config_exists = True):
    """Bazel's paths: the module's config.py and directories, whose listings are recorded."""

    def directory(name):
        return struct(readdir = lambda watch: listings.append((name, watch)) or [])

    def path(value):
        if str(value) == str(_TREE):
            return mocks.path(value)
        if str(value) == str(_RIVE.same_package_label("config.py")):
            return struct(exists = config_exists, dirname = directory("third_party/rive"))
        if str(value) == str(_RIVE.same_package_label("shaders")):
            return directory("third_party/rive/shaders")
        return str(value)

    return path

def _test_custom_modules_configure_by_structure(env):
    listings = []
    ctx, errors = _build(
        custom_modules = {_RIVE: "rive"},
        path = _module_paths(listings),
        execute = {_PYTHON + " -P -m tools.engine.custom_modules": {"stdout": _PREPARED}},
    )
    env.expect.that_collection(errors).contains_exactly([])
    prepare = [call for call in mocks.calls(ctx, "execute") if call.args[3] == "tools.engine.custom_modules"][0]
    env.expect.that_str(prepare.args[-1]).equals("@@//third_party/rive:rive")
    env.expect.that_str(prepare.args[-3]).equals("rive")

    # The recipe watches the module's directory listings and the files that shape its
    # graph, not its code, which a build takes from the module's target.
    env.expect.that_collection(listings).contains_exactly([
        ("third_party/rive", "yes"),
        ("third_party/rive/shaders", "yes"),
    ])
    env.expect.that_collection([str(call.path) for call in mocks.calls(ctx, "watch")]).contains_at_least([
        "@@//third_party/rive:SCsub",
        "@@//third_party/rive:config.py",
    ])
    env.expect.that_collection(mocks.calls(ctx, "watch_tree")).contains_exactly([])
    arguments = _configure(ctx).args
    env.expect.that_collection([
        arguments[i + 1]
        for i in range(len(arguments))
        if arguments[i] == "--custom-module-name"
    ]).contains_exactly(["rive"])

    # The placeholders go after configuring: the module's target supplies the code.
    env.expect.that_collection([call.path for call in mocks.calls(ctx, "delete")]).contains(
        "_custom_modules/rive/rive.cpp",
    )

def _test_a_custom_module_needs_its_config_py(env):
    ctx, errors = _build(custom_modules = {_RIVE: "rive"}, path = _module_paths([], config_exists = False))
    env.expect.that_collection(errors).contains_exactly([
        "custom module @@//third_party/rive:rive: the package of its target must hold the module's config.py",
    ])
    env.expect.that_bool(_configure(ctx) == None).equals(True)
    env.expect.that_collection(mocks.calls(ctx, "file")).contains_exactly([])

def _test_ios_recipe_without_environment_fails(env):
    ctx, errors = _build(name = "godot_ios_arm64_template_release", platform = "ios", cpu = "arm64")
    env.expect.that_collection(errors).contains_exactly([
        'godot_ios_arm64_template_release: iOS recipes need environment = "device" or "simulator"',
    ])
    env.expect.that_collection([call.method for call in ctx.calls]).contains_exactly(
        _TOOL_WATCHES,
    )

def _test_environment_outside_ios_recipe_fails(env):
    ctx, errors = _build(environment = "device")
    env.expect.that_collection(errors).contains_exactly([
        "godot_linux_x86_64_template_release: environment is only valid for iOS recipes",
    ])
    env.expect.that_collection([call.method for call in ctx.calls]).contains_exactly(
        _TOOL_WATCHES,
    )

# Configuration runs rules_python's interpreter, whatever Python the host's PATH has.
def _test_rules_python_runs_configure(env):
    ctx, errors = _build()
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_str(_configure(ctx).args[0]).equals(_PYTHON)

# Configuration ends after a fixed timeout.
def _test_a_fixed_timeout_bounds_configure(env):
    ctx, errors = _build()
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_dict(_configure(ctx).kwargs).contains_exactly({
        "environment": {"PYTHONPATH": "rules_godot"},
        "timeout": 1800,
        "quiet": True,
    })

def _test_failed_configure_fails(env):
    ctx, errors = _build(execute = {_PYTHON + " -P -m tools.engine.configure": {"return_code": 1, "stdout": "out", "stderr": "err"}})
    env.expect.that_collection(errors).contains_exactly(["Godot graph configuration failed:\nout\nerr"])
    env.expect.that_collection(mocks.calls(ctx, "file")).contains_exactly([])

_LOCK = "engines/godot.lock.json"

def _pinned(files = {}, **overrides):
    return _build(
        lock_file = _LOCK,
        lock_key = "linux_x86_64_template_release",
        repin = "@godot//:pin",
        # configure.py writes the BUILD file: the rendered graph or failing engine targets.
        files = {"BUILD.bazel": "# BUILD from the lock file\n"} | files,
        **overrides
    )

def _written_build(ctx):
    return [call.content for call in mocks.calls(ctx, "file") if call.path == "BUILD.bazel"][0]

def _argument(arguments, name):
    return arguments[arguments.index(name) + 1]

def _test_a_lock_file_renders_without_configuring_on_this_host(env):
    ctx, errors = _pinned()
    env.expect.that_collection(errors).contains_exactly([])

    # Without the host's configure environment, the recipe is the same on every host.
    env.expect.that_collection(mocks.calls(ctx, "getenv")).contains_exactly([])
    env.expect.that_collection([call.path for call in mocks.calls(ctx, "watch")]).contains(_LOCK)
    arguments = _configure(ctx).args
    env.expect.that_str(_argument(arguments, "--lock")).equals(_LOCK)
    env.expect.that_str(_argument(arguments, "--recipe")).equals("linux_x86_64_template_release")
    env.expect.that_str(_argument(arguments, "--pin-bzl")).equals("@@//godot/engine/private:pin.bzl")
    message = _argument(arguments, "--unpinned-message")
    env.expect.that_str(message).contains("{reason} recipe linux_x86_64_template_release")
    env.expect.that_str(message).contains("`bazel run @godot//:pin`")
    build = _written_build(ctx)
    env.expect.that_str(build).contains("# BUILD from the lock file\n")
    env.expect.that_str(build).contains('name = "pin"')
    env.expect.that_str(build).contains('archive = "%s"' % _ARCHIVE)
    env.expect.that_str(build).contains('strip_prefix = "godot-4.7.2-stable"')
    env.expect.that_str(build).contains('exec_compatible_with = ["@@platforms//os:linux"]')
    env.expect.that_str(build).contains('"--platform", "linuxbsd", "--cpu", "x86_64"')
    env.expect.that_collection(mocks.calls(ctx, "delete")).contains_exactly([])

def _test_pins_configure_where_godot_accepts_the_recipe(env):
    for platform, environment, constraints in [
        ("macos", "", '["@@platforms//os:macos"]'),
        ("ios", "device", '["@@platforms//os:macos"]'),
        # Android configures against a stand-in SDK on any execution platform.
        ("android", "", "[]"),
    ]:
        ctx, errors = _pinned(platform = platform, environment = environment)
        env.expect.where(platform = platform).that_collection(errors).contains_exactly([])
        build = _written_build(ctx)
        env.expect.where(platform = platform).that_str(build).contains("exec_compatible_with = " + constraints)

# A recipe configures without a build profile: applications bring theirs.
def _test_a_recipe_configures_without_a_build_profile(env):
    ctx, errors = _pinned()
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_str(_written_build(ctx)).contains('srcs = glob(["_custom_modules/**", "_custom_modules.json", "_scons/**"])')
    env.expect.that_collection(_configure(ctx).args).not_contains("--build-profile")

# A recipe's rendering methods reach configure, which derives the drivers from them.
def _test_renderers_reach_configure(env):
    ctx, errors = _build(renderers = ["gl_compatibility", "mobile"])
    env.expect.that_collection(errors).contains_exactly([])
    arguments = _configure(ctx).args
    env.expect.that_str(_argument(arguments, "--renderers")).equals("gl_compatibility,mobile")
    ctx, _errors = _build()
    env.expect.that_collection(_configure(ctx).args).not_contains("--renderers")

# The build options of the registered runtime profile, as the extension passes them.
_RUNTIME_PROFILES = {"//app:app.gdbuild": json.encode({"disable_navigation_2d": True})}

# A runtime variant's profile has its runtime profile's options.
def _test_a_runtime_variant_configures_with_its_profiles_options(env):
    ctx, errors = _build(runtime_profiles = _RUNTIME_PROFILES)
    env.expect.that_collection(errors).contains_exactly([])
    written = {call.path: call.content for call in mocks.calls(ctx, "file")}
    env.expect.that_dict(json.decode(written["_variant_0.gdbuild"])["disabled_build_options"]).contains_exactly(
        {"disable_navigation_2d": True},
    )

    # Without a lock file, the variants configure together into their pins before the recipe.
    script = written["_variant_pins/configure.sh"]
    env.expect.that_str(script).contains("'--build-profile' '_variant_0.gdbuild' '--pin-output' '_variant_pins/0.json'")
    env.expect.that_str(script).contains("|| mv _variant_pins/0.log _variant_pins/0.error) &")
    env.expect.that_collection([call.args for call in mocks.calls(ctx, "execute")]).contains(
        ["/bin/sh", "_variant_pins/configure.sh"],
    )
    recipe = _configure(ctx).args
    env.expect.that_collection(recipe).not_contains("--build-profile")
    env.expect.that_str(_argument(recipe, "--variant-pins")).equals("_variant_pins")
    env.expect.that_str(_argument(recipe, "--runtime-profile")).equals("//app:app.gdbuild")

def _test_a_runtime_variant_has_its_own_pin(env):
    ctx, errors = _pinned(runtime_profiles = _RUNTIME_PROFILES)
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection([call.args[0] for call in mocks.calls(ctx, "execute")]).not_contains("/bin/sh")
    build = _written_build(ctx)
    env.expect.that_str(build).contains('name = "pin_variant_0"')
    env.expect.that_str(build).contains('"--build-profile", "_variant_0.gdbuild"')
    env.expect.that_str(build).contains('"_scons/**", "_variant_*.gdbuild"])')

# A recipe reads a profile's options as its Godot version does: 4.7 has no renderer
# switches, and 4.7.0 to 4.7.2 cannot build gridmap without 3D physics.
def _test_a_profile_takes_the_options_of_the_recipes_version(env):
    options = {"rendering_device": False, "disable_physics_3d": True}
    env.expect.that_dict(profile_options(options, "4.7.2")).contains_exactly(
        {"disable_physics_3d": True, "module_gridmap_enabled": False},
    )
    env.expect.that_dict(profile_options(options, "4.7.3-rc")).contains_exactly({"disable_physics_3d": True})
    env.expect.that_dict(profile_options(options, "4.8.0-beta")).contains_exactly(options)
    explicit = {"disable_physics_3d": True, "module_gridmap_enabled": True}
    env.expect.that_dict(profile_options(explicit, "4.7.2")).contains_exactly(explicit)

def engine_build_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_configure_command_carries_the_recipe,
            _test_build_options_become_sorted_options,
            _test_scons_platform_follows_the_recipe_platform,
            _test_import_env_vars_are_read,
            _test_default_modules_reach_configure,
            _test_a_recipe_configures_without_a_build_profile,
            _test_a_runtime_variant_configures_with_its_profiles_options,
            _test_a_runtime_variant_has_its_own_pin,
            _test_a_profile_takes_the_options_of_the_recipes_version,
            _test_renderers_reach_configure,
            _test_custom_modules_configure_by_structure,
            _test_a_custom_module_needs_its_config_py,
            _test_ios_recipe_without_environment_fails,
            _test_environment_outside_ios_recipe_fails,
            _test_rules_python_runs_configure,
            _test_a_fixed_timeout_bounds_configure,
            _test_failed_configure_fails,
            _test_a_recipe_links_its_engine_tree,
            _test_a_failed_link_fails,
            _test_a_lock_file_renders_without_configuring_on_this_host,
            _test_pins_configure_where_godot_accepts_the_recipe,
        ],
    )
