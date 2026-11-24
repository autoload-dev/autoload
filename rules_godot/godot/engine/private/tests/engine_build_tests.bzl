"""godot_engine_build extracts and patches one recipe and passes it to the configure-only capture."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")

# buildifier: disable=bzl-visibility
load("//godot/engine/private:source_repositories.bzl", "engine_build_impl")

# buildifier: disable=bzl-visibility
load("//godot/private/tests:mocks.bzl", "mocks")

_SOURCE = Label("//godot/engine/private/tests:source.json")
_SHA256 = "e954996374cbd1cb5d72e0e3781cc537408e6ce73b010b12c6c2f308a820690a"
_PYTHON = "/usr/bin/python3"
_PATCH = "/usr/bin/patch"

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
    "source": _SOURCE,
    "platform": "linux",
    "cpu": "x86_64",
    "build_target": "template_release",
    "environment": "",
    "enabled_modules": ["gdscript", "text_server_fb"],
    "default_modules": False,
    "custom_modules": {},
    "patches": [],
    "patch_strip": 1,
    "renderers": [],
    "build_profile": None,
    "build_options": {},
    "build_name": "custom",
    "python": None,
    "configure_timeout": 600,
    "_configure": "tools/engine/configure.py",
    "_module_graph": "tools/engine/module_graph.py",
    "_include_graph": "tools/engine/include_graph.py",
    "_feature_macros": "tools/engine/feature_macros.py",
    "_render": "tools/engine/render.py",
    "_source_tree": "tools/engine/source_tree.py",
    "_generator": "@@//godot/engine/private:generator.bzl",
    "_cc_rules": "@@rules_cc+//cc:cc_library.bzl",
    "_platforms_constraint": "@@platforms//os:android",
    "_apple_constraint": "@@apple_support+//constraints:device",
    "_swift_library": "@@rules_swift+//swift:swift_library.bzl",
    "_pin_bzl": "@@//godot/engine/private:pin.bzl",
    "lock_file": None,
    "lock_key": "",
    "repin": "",
}

def _build(*, which = {"python3": _PYTHON, "patch": _PATCH}, execute = {}, path = None, environ = {}, files = {}, **overrides):
    ctx = mocks.repository_ctx(
        attr = _ATTRS | overrides,
        files = {str(_SOURCE): json.encode({
            "archive": "source.tar.gz",
            "sha256": _SHA256,
            "strip_prefix": "godot-4.7.2-stable",
            "version": "4.7.2",
        })} | files,
        which = which,
        execute = execute,
        path = path,
        environ = environ,
    )
    errors, fail_ = mocks.errors()
    engine_build_impl(ctx, _fail = fail_)
    return ctx, errors

def _configure(ctx, python = _PYTHON):
    """The arguments of the configure call."""
    calls = [call for call in mocks.calls(ctx, "execute") if call.args[0] == python]
    return calls[0] if calls else None

def _options(arguments):
    return [arguments[i + 1] for i in range(len(arguments)) if arguments[i] == "--option"]

def _test_configure_command_carries_the_recipe(env):
    ctx, errors = _build(
        enabled_modules = ["gdscript", "svg"],
        build_name = "studio",
        patches = ["fork.patch"],
        patch_strip = 2,
    )
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection([call.method for call in ctx.calls]).contains_exactly(
        ["watch"] * 5 + ["getenv"] * len(_CONFIGURE_ENVIRONMENT) + [
            "extract",
            "getenv",
            "watch",
            "execute",
            "download_and_extract",
            "execute",
            "delete",
            "file",
        ],
    ).in_order()
    env.expect.that_str(mocks.calls(ctx, "delete")[0].path).equals(".scons_env.json")
    extract = mocks.calls(ctx, "extract")[0]
    env.expect.that_str(extract.archive).equals(str(_SOURCE.same_package_label("source.tar.gz")))
    env.expect.that_str(extract.stripPrefix).equals("godot-4.7.2-stable")
    env.expect.that_collection(mocks.calls(ctx, "execute")[0].args).contains_exactly(
        [_PATCH, "-p2", "-F0", "-t", "-N", "-i", "fork.patch"],
    ).in_order()
    env.expect.that_str(mocks.calls(ctx, "download_and_extract")[0].output).equals("_scons")
    env.expect.that_collection(_configure(ctx).args).contains_exactly([
        _PYTHON,
        "tools/engine/configure.py",
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
        "fork.patch",
    ]).in_order()
    env.expect.that_collection([call.path for call in mocks.calls(ctx, "file")]).contains_exactly(
        ["WORKSPACE.bazel"],
    )

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

def _module_paths(modules):
    """A path mapping that gives each custom module key a path struct, as Bazel does."""
    return lambda value: mocks.path(value) if str(value) in modules else str(value)

def _test_default_modules_reach_configure(env):
    ctx, errors = _build(default_modules = True)
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(_configure(ctx).args).contains("--default-modules")
    ctx, errors = _build()
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(_configure(ctx).args).not_contains("--default-modules")

def _test_custom_module_sources_are_watched(env):
    modules = {"third_party/rive/config.py": "rive", "third_party/steam/config.py": "steam"}
    ctx, errors = _build(custom_modules = modules, path = _module_paths(modules))
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection([call.path for call in mocks.calls(ctx, "watch_tree")]).contains_exactly(
        ["third_party/rive", "third_party/steam"],
    ).in_order()
    arguments = _configure(ctx).args
    env.expect.that_collection([
        arguments[i + 1]
        for i in range(len(arguments))
        if arguments[i] == "--custom-module-source"
    ]).contains_exactly(["rive=third_party/rive", "steam=third_party/steam"]).in_order()

def _test_custom_module_key_not_config_py_fails(env):
    modules = {"third_party/rive/SCsub": "rive"}
    ctx, errors = _build(custom_modules = modules, path = _module_paths(modules))
    env.expect.that_collection(errors).contains_exactly([
        "custom_modules keys must name each module's config.py: third_party/rive/SCsub",
    ])
    env.expect.that_collection(mocks.calls(ctx, "watch_tree")).contains_exactly([])
    env.expect.that_bool(_configure(ctx) == None).equals(True)
    env.expect.that_collection(mocks.calls(ctx, "file")).contains_exactly([])

def _test_ios_recipe_without_environment_fails(env):
    ctx, errors = _build(name = "godot_ios_arm64_template_release", platform = "ios", cpu = "arm64")
    env.expect.that_collection(errors).contains_exactly([
        'godot_ios_arm64_template_release: iOS recipes need environment = "device" or "simulator"',
    ])
    env.expect.that_collection([call.method for call in ctx.calls]).contains_exactly(
        ["watch"] * 5,
    )

def _test_environment_outside_ios_recipe_fails(env):
    ctx, errors = _build(environment = "device")
    env.expect.that_collection(errors).contains_exactly([
        "godot_linux_x86_64_template_release: environment is only valid for iOS recipes",
    ])
    env.expect.that_collection([call.method for call in ctx.calls]).contains_exactly(
        ["watch"] * 5,
    )

def _test_declared_python_runs_configure(env):
    ctx, errors = _build(python = "@@python_3_12//:python3", which = {})
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_bool(_configure(ctx, "@@python_3_12//:python3") != None).equals(True)
    ctx, errors = _build(which = {"python3": "/opt/bin/python3"})
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_bool(_configure(ctx, "/opt/bin/python3") != None).equals(True)

def _test_missing_python_fails(env):
    ctx, errors = _build(which = {})
    env.expect.that_collection(errors).contains_exactly([
        "Godot source graph configuration needs Python 3.9+; " +
        "set python to a declared executable label",
    ])
    env.expect.that_collection(mocks.calls(ctx, "execute")).contains_exactly([])
    env.expect.that_collection(mocks.calls(ctx, "file")).contains_exactly([])

def _test_configure_timeout_bounds_configure(env):
    ctx, errors = _build(configure_timeout = 45)
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_dict(_configure(ctx).kwargs).contains_exactly({"timeout": 45, "quiet": True})

def _test_failed_configure_fails(env):
    ctx, errors = _build(execute = {_PYTHON: {"return_code": 1, "stdout": "out", "stderr": "err"}})
    env.expect.that_collection(errors).contains_exactly(["Godot graph configuration failed:\nout\nerr"])
    env.expect.that_collection(mocks.calls(ctx, "file")).contains_exactly([])

def _test_rejected_patch_stops_the_recipe(env):
    ctx, errors = _build(
        patches = ["fork.patch"],
        execute = {_PATCH: {"return_code": 1, "stdout": "1 out of 1 hunk FAILED"}},
    )
    env.expect.that_collection(errors).has_size(1)
    env.expect.that_str(errors[0]).contains("Error applying patch fork.patch")
    env.expect.that_collection(mocks.calls(ctx, "download_and_extract")).contains_exactly([])
    env.expect.that_bool(_configure(ctx) == None).equals(True)

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
    env.expect.that_str(build).contains('archive = "%s"' % _SOURCE.same_package_label("source.tar.gz"))
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

# A recipe's build profile lies in the source root, where SCons reads it, and a pin action
# declares it, so the remote configuration reads the same profile.
def _test_a_build_profile_reaches_configure_and_the_pin(env):
    profile = '{"disabled_classes": ["Node3D"]}'
    ctx, errors = _build(build_profile = "size.gdbuild", files = {"size.gdbuild": profile})
    env.expect.that_collection(errors).contains_exactly([])
    written = {call.path: call.content for call in mocks.calls(ctx, "file")}
    env.expect.that_str(written["_build_profile.gdbuild"]).equals(profile)
    env.expect.that_str(_argument(_configure(ctx).args, "--build-profile")).equals("_build_profile.gdbuild")

    ctx, errors = _pinned(build_profile = "size.gdbuild", files = {"size.gdbuild": profile})
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_str(_written_build(ctx)).contains('srcs = glob(["_custom_modules/**", "_scons/**", "_build_profile.gdbuild"])')
    ctx, _errors = _pinned()
    env.expect.that_str(_written_build(ctx)).contains('srcs = glob(["_custom_modules/**", "_scons/**"])')
    env.expect.that_collection(_configure(ctx).args).not_contains("--build-profile")

# A recipe's rendering methods reach configure, which derives the drivers from them.
def _test_renderers_reach_configure(env):
    ctx, errors = _build(renderers = ["gl_compatibility", "mobile"])
    env.expect.that_collection(errors).contains_exactly([])
    arguments = _configure(ctx).args
    env.expect.that_str(_argument(arguments, "--renderers")).equals("gl_compatibility,mobile")
    ctx, _errors = _build()
    env.expect.that_collection(_configure(ctx).args).not_contains("--renderers")

def engine_build_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_configure_command_carries_the_recipe,
            _test_build_options_become_sorted_options,
            _test_scons_platform_follows_the_recipe_platform,
            _test_import_env_vars_are_read,
            _test_default_modules_reach_configure,
            _test_a_build_profile_reaches_configure_and_the_pin,
            _test_renderers_reach_configure,
            _test_custom_module_sources_are_watched,
            _test_custom_module_key_not_config_py_fails,
            _test_ios_recipe_without_environment_fails,
            _test_environment_outside_ios_recipe_fails,
            _test_declared_python_runs_configure,
            _test_missing_python_fails,
            _test_configure_timeout_bounds_configure,
            _test_failed_configure_fails,
            _test_rejected_patch_stops_the_recipe,
            _test_a_lock_file_renders_without_configuring_on_this_host,
            _test_pins_configure_where_godot_accepts_the_recipe,
        ],
    )
