"""How engine_optimize and engine_lto become a source-built engine's compiler and linker options."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/engine/private:optimization.bzl", "engine_optimization")

_COPT = "//command_line_option:copt"
_LINKOPT = "//command_line_option:linkopt"
_RELEASE = struct(role = "runtime", variant = "release")
_DEBUG = struct(role = "runtime", variant = "debug")
_EDITOR = struct(role = "editor", variant = "")

def _settings(mode = "opt", optimize = "auto", lto = "none"):
    return {
        "//command_line_option:compilation_mode": mode,
        _COPT: ["-g"],
        _LINKOPT: ["-Wl,-v"],
        str(Label("//godot:engine_optimize")): optimize,
        str(Label("//godot:engine_lto")): lto,
    }

# auto is Godot's choice: -O3 for release runtimes, -O2 for debug runtimes and editors. The
# options follow the build's own, so they win over the toolchain's and the command line's.
def _test_auto_follows_godots_choice_per_build_target(env):
    for attr, level in [(_RELEASE, "-O3"), (_DEBUG, "-O2"), (_EDITOR, "-O2")]:
        options = engine_optimization(_settings(), attr)
        expect = env.expect.where(role = attr.role, variant = attr.variant)
        expect.that_collection(options[_COPT]).contains_exactly(["-g", level]).in_order()
        expect.that_collection(options[_LINKOPT]).contains_exactly(["-Wl,-v"])

# Godot's levels keep Godot's meaning; size_min is the ruleset's smallest engine.
def _test_levels_keep_godots_meaning(env):
    for level, options in [
        ("speed", ["-O3"]),
        ("speed_trace", ["-O2"]),
        ("size", ["-Os"]),
        ("size_extra", ["-Os", "-DSIZE_EXTRA"]),
        ("size_min", ["-Oz", "-DSIZE_EXTRA"]),
    ]:
        copts = engine_optimization(_settings(optimize = level), _DEBUG)[_COPT]
        env.expect.where(level = level).that_collection(copts).contains_exactly(["-g"] + options).in_order()

# LTO compiles bitcode and links it: Android and desktop engines link below the engine's edge.
def _test_lto_compiles_and_links(env):
    for lto, options in [("thin", ["-flto=thin"]), ("full", ["-flto"])]:
        result = engine_optimization(_settings(optimize = "size_min", lto = lto), _RELEASE)
        expect = env.expect.where(lto = lto)
        expect.that_collection(result[_COPT]).contains_exactly(["-g", "-Oz", "-DSIZE_EXTRA"] + options).in_order()
        expect.that_collection(result[_LINKOPT]).contains_exactly(["-Wl,-v"] + options).in_order()

# Other compilation modes keep Bazel's levels, so -c dbg debugs the engine unoptimized.
def _test_other_compilation_modes_keep_bazels_levels(env):
    for mode in ["dbg", "fastbuild"]:
        options = engine_optimization(_settings(mode = mode, optimize = "size_min", lto = "full"), _RELEASE)
        expect = env.expect.where(mode = mode)
        expect.that_collection(options[_COPT]).contains_exactly(["-g"])
        expect.that_collection(options[_LINKOPT]).contains_exactly(["-Wl,-v"])

def optimization_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_auto_follows_godots_choice_per_build_target,
            _test_levels_keep_godots_meaning,
            _test_lto_compiles_and_links,
            _test_other_compilation_modes_keep_bazels_levels,
        ],
    )
