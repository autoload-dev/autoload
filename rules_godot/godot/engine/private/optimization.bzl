"""
How a source-built engine compiles under -c opt: the engine_optimize and engine_lto settings.

The engine rules' transitions apply these options to the engine's native graph only, so
extensions and application code keep the build's own levels.
"""

load("//godot/private/config:native.bzl", "COMPILATION_MODE", "COPT", "LINKOPT")

visibility(["//godot/engine/private/..."])

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

OPTIMIZATION_OUTPUTS = [COPT, LINKOPT]
OPTIMIZATION_INPUTS = OPTIMIZATION_OUTPUTS + [COMPILATION_MODE, _ENGINE_OPTIMIZE, _ENGINE_LTO]

def engine_optimization(settings, attr):
    """
    Return the engine's --copt and --linkopt: under -c opt, engine_optimize's and engine_lto's.

    They follow the build's own options, so the engine's level wins over the toolchain's.

    Args:
        settings: Transition inputs, OPTIMIZATION_INPUTS among them.
        attr: Attributes of the engine rule: role and variant.

    Returns:
        The --copt and --linkopt values of the engine's native graph.
    """
    copts, linkopts = settings[COPT], settings[LINKOPT]

    # Bazel passes the compilation mode to transitions as an enum, not as a string.
    if str(settings[COMPILATION_MODE]) != "opt":
        return {COPT: copts, LINKOPT: linkopts}
    level = settings[_ENGINE_OPTIMIZE]
    if level == "auto":
        level = "speed" if attr.role == "runtime" and attr.variant == "release" else "speed_trace"
    lto = _LTO_OPTIONS[settings[_ENGINE_LTO]]
    return {COPT: copts + _OPTIMIZE_OPTIONS[level] + lto, LINKOPT: linkopts + lto}
