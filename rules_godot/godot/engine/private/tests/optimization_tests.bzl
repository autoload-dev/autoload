"""How the engine settings become a source-built engine's compiler and linker options."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/engine/private:optimization.bzl", "editor_debugging", "engine_optimization", "optimization_error")
load("//godot/private/config:native.bzl", "COMPILATION_MODE", "COPT", "LINKOPT")

_RELEASE = struct(role = "runtime", variant = "release")
_DEBUG = struct(role = "runtime", variant = "debug")
_EDITOR = struct(role = "editor", variant = "")

_ENGINE_OPTIMIZE = str(Label("//godot:engine_optimize"))
_ENGINE_LTO = str(Label("//godot:engine_lto"))
_ENGINE_VFE = str(Label("//godot:engine_vfe"))
_EDITOR_DEBUG = str(Label("//godot:editor_debug"))

_VFE_OPTIONS = [
    "-DTYPED_METHOD_BIND",
    "-fvisibility=hidden",
    "-fwhole-program-vtables",
    "-fvirtual-function-elimination",
]

def _settings(mode = "opt", optimize = "auto", lto = "none", vfe = False):
    return {
        COMPILATION_MODE: mode,
        COPT: ["-g"],
        LINKOPT: ["-Wl,-v"],
        _ENGINE_OPTIMIZE: optimize,
        _ENGINE_LTO: lto,
        _ENGINE_VFE: vfe,
    }

# auto is Godot's choice: -O3 for release runtimes, -O2 for debug runtimes and editors. The
# options follow the build's own, so they win over the toolchain's and the command line's.
def _test_auto_follows_godots_choice_per_build_target(env):
    for attr, level in [(_RELEASE, "-O3"), (_DEBUG, "-O2"), (_EDITOR, "-O2")]:
        options = engine_optimization(_settings(), attr)
        expect = env.expect.where(role = attr.role, variant = attr.variant)
        expect.that_collection(options[COPT]).contains_exactly(["-g", level]).in_order()
        expect.that_collection(options[LINKOPT]).contains_exactly(["-Wl,-v"])

# Godot's levels keep Godot's meaning; size_min is the ruleset's smallest engine.
def _test_levels_keep_godots_meaning(env):
    for level, options in [
        ("speed", ["-O3"]),
        ("speed_trace", ["-O2"]),
        ("size", ["-Os"]),
        ("size_extra", ["-Os", "-DSIZE_EXTRA"]),
        ("size_min", ["-Oz", "-DSIZE_EXTRA"]),
    ]:
        copts = engine_optimization(_settings(optimize = level), _DEBUG)[COPT]
        env.expect.where(level = level).that_collection(copts).contains_exactly(["-g"] + options).in_order()

# LTO compiles bitcode and links it: Android and desktop engines link below the engine's edge.
def _test_lto_compiles_and_links(env):
    for lto, options in [("thin", ["-flto=thin"]), ("full", ["-flto"])]:
        result = engine_optimization(_settings(optimize = "size_min", lto = lto), _RELEASE)
        expect = env.expect.where(lto = lto)
        expect.that_collection(result[COPT]).contains_exactly(["-g", "-Oz", "-DSIZE_EXTRA"] + options).in_order()
        expect.that_collection(result[LINKOPT]).contains_exactly(["-Wl,-v"] + options).in_order()

# Virtual function elimination compiles with TYPED_METHOD_BIND, without which Godot's method
# binds lose their virtual setters, and with Clang's options; the full LTO link needs only -flto.
def _test_virtual_function_elimination_compiles_with_typed_method_binds(env):
    result = engine_optimization(_settings(optimize = "size_min", lto = "full", vfe = True), _RELEASE)
    env.expect.that_collection(result[COPT]).contains_exactly(
        ["-g", "-Oz", "-DSIZE_EXTRA", "-flto"] + _VFE_OPTIONS,
    ).in_order()
    env.expect.that_collection(result[LINKOPT]).contains_exactly(["-Wl,-v", "-flto"]).in_order()

# The engine's graph resets the settings, so engines that compile alike share a configuration.
def _test_the_engine_graph_resets_the_settings(env):
    for mode, optimize in [("opt", "speed"), ("dbg", "size_min")]:
        options = engine_optimization(_settings(mode = mode, optimize = optimize, lto = "full", vfe = True), _RELEASE)
        expect = env.expect.where(mode = mode)
        expect.that_str(options[_ENGINE_OPTIMIZE]).equals("auto")
        expect.that_str(options[_ENGINE_LTO]).equals("none")
        expect.that_bool(options[_ENGINE_VFE]).equals(False)

# Other compilation modes keep Bazel's levels, so -c dbg debugs the engine unoptimized; there
# virtual function elimination neither applies nor needs full LTO.
def _test_other_compilation_modes_keep_bazels_levels(env):
    for mode, lto in [("dbg", "full"), ("fastbuild", "full"), ("dbg", "none")]:
        options = engine_optimization(_settings(mode = mode, optimize = "size_min", lto = lto, vfe = True), _RELEASE)
        expect = env.expect.where(mode = mode, lto = lto)
        expect.that_collection(options[COPT]).contains_exactly(["-g"])
        expect.that_collection(options[LINKOPT]).contains_exactly(["-Wl,-v"])

# Elimination happens in the full LTO link, so the build fails without one instead of
# compiling options the compiler rejects; other compilation modes apply no settings.
def _test_virtual_function_elimination_needs_full_lto(env):
    for mode, lto, error in [
        ("opt", "none", 'engine_vfe needs engine_lto = "full", on the command line or the godot_app, not "none"'),
        ("opt", "thin", 'engine_vfe needs engine_lto = "full", on the command line or the godot_app, not "thin"'),
        ("opt", "full", None),
        ("dbg", "none", None),
        ("fastbuild", "thin", None),
    ]:
        env.expect.where(mode = mode, lto = lto).that_str(
            str(optimization_error(mode, lto, True)),
        ).equals(str(error))
    env.expect.that_str(str(optimization_error("opt", "none", False))).equals("None")

# editor_debug compiles a source-built editor for a debugger, and only an editor.
def _test_editor_debug_compiles_editors_without_optimization(env):
    for attr, mode in [(_EDITOR, "dbg"), (_RELEASE, "opt"), (_DEBUG, "opt")]:
        settings = editor_debugging({COMPILATION_MODE: "opt", _EDITOR_DEBUG: True}, attr)
        expect = env.expect.where(role = attr.role, variant = attr.variant)
        expect.that_str(settings[COMPILATION_MODE]).equals(mode)

        # The graph resets the setting, so runtimes compile alike with and without it.
        expect.that_bool(settings[_EDITOR_DEBUG]).equals(False)
    settings = editor_debugging({COMPILATION_MODE: "fastbuild", _EDITOR_DEBUG: False}, _EDITOR)
    env.expect.that_str(settings[COMPILATION_MODE]).equals("fastbuild")

def optimization_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_auto_follows_godots_choice_per_build_target,
            _test_levels_keep_godots_meaning,
            _test_lto_compiles_and_links,
            _test_virtual_function_elimination_compiles_with_typed_method_binds,
            _test_the_engine_graph_resets_the_settings,
            _test_other_compilation_modes_keep_bazels_levels,
            _test_virtual_function_elimination_needs_full_lto,
            _test_editor_debug_compiles_editors_without_optimization,
        ],
    )
