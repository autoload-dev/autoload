"""
How a source-built engine compiles under -c opt: the engine_optimize and engine_lto settings.

The engine rules' transitions apply these options to the engine's native graph only, so
extensions and application code keep the build's own levels.
"""

load("//godot/private/config:native.bzl", "COMPILATION_MODE", "COPT", "LINKOPT")

visibility(["//godot/..."])

_ENGINE_OPTIMIZE = str(Label("//godot:engine_optimize"))
_ENGINE_LTO = str(Label("//godot:engine_lto"))

# The compiler options of Godot's optimize levels, as its SConstruct sets them, and of
# the ruleset's size_min.
_OPTIMIZE_OPTIONS = {
    "speed": ["-O3"],
    "speed_trace": ["-O2"],
    "size": ["-Os"],
    "size_extra": ["-Os", "-DSIZE_EXTRA"],
    "size_min": ["-Oz", "-DSIZE_EXTRA"],
}

# Compile and link options of each engine_lto value: Apple's linker needs only the
# objects' bitcode; Android and desktop engines link themselves below this edge.
_LTO_OPTIONS = {
    "none": [],
    "thin": ["-flto=thin"],
    "full": ["-flto"],
}

# The settings' values, for their flags and godot_app's attributes.
OPTIMIZE_VALUES = ["auto"] + _OPTIMIZE_OPTIONS.keys()
LTO_VALUES = _LTO_OPTIONS.keys()

# The engine's graph takes the settings' options and resets the settings, so engines that
# compile alike share one configuration whatever values led there.
_RESET = {_ENGINE_OPTIMIZE: "auto", _ENGINE_LTO: "none"}

OPTIMIZATION_OUTPUTS = [COPT, LINKOPT] + _RESET.keys()
OPTIMIZATION_INPUTS = OPTIMIZATION_OUTPUTS + [COMPILATION_MODE]

def engine_optimization(settings, attr):
    """
    Return the engine's --copt and --linkopt: under -c opt, engine_optimize's and engine_lto's.

    They follow the build's own options, so the engine's level wins over the toolchain's.

    Args:
        settings: Transition inputs, OPTIMIZATION_INPUTS among them.
        attr: Attributes of the engine rule: role and variant.

    Returns:
        The --copt and --linkopt values of the engine's native graph, and the settings
        reset to their defaults.
    """
    copts, linkopts = settings[COPT], settings[LINKOPT]

    # Bazel passes the compilation mode to transitions as an enum, not as a string.
    if str(settings[COMPILATION_MODE]) != "opt":
        return {COPT: copts, LINKOPT: linkopts} | _RESET
    level = settings[_ENGINE_OPTIMIZE]
    if level == "auto":
        level = "speed" if attr.role == "runtime" and attr.variant == "release" else "speed_trace"
    lto = _LTO_OPTIONS[settings[_ENGINE_LTO]]
    return {COPT: copts + _OPTIMIZE_OPTIONS[level] + lto, LINKOPT: linkopts + lto} | _RESET

# The attributes of the rules that resolve an application's runtime component.
ENGINE_SETTINGS_ATTRS = {
    "engine_optimize": attr.string(
        doc = "The engine_optimize of this application's source-built engine; empty keeps the build's.",
        values = [""] + OPTIMIZE_VALUES,
    ),
    "engine_lto": attr.string(
        doc = "The engine_lto of this application's source-built engine; empty keeps the build's.",
        values = [""] + LTO_VALUES,
    ),
}

def _engine_settings_impl(settings, attr):
    return {
        _ENGINE_OPTIMIZE: attr.engine_optimize or settings[_ENGINE_OPTIMIZE],
        _ENGINE_LTO: attr.engine_lto or settings[_ENGINE_LTO],
    }

# Sets an application's engine settings where its runtime component is resolved, so the
# engine compiles with them and the rest of the application keeps the build's.
engine_settings = transition(
    implementation = _engine_settings_impl,
    inputs = [_ENGINE_OPTIMIZE, _ENGINE_LTO],
    outputs = [_ENGINE_OPTIMIZE, _ENGINE_LTO],
)
