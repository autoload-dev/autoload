"""
How a source-built engine compiles under -c opt: the engine_optimize and engine_lto settings.

The engine rules' transitions apply these options to the engine's native graph only, so
extensions and application code keep the build's own levels.
"""

visibility(["//godot/engine/private/..."])

_COMPILATION_MODE = "//command_line_option:compilation_mode"
_COPT = "//command_line_option:copt"
_LINKOPT = "//command_line_option:linkopt"
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

OPTIMIZATION_INPUTS = [_COMPILATION_MODE, _COPT, _LINKOPT, _ENGINE_OPTIMIZE, _ENGINE_LTO]
OPTIMIZATION_OUTPUTS = [_COPT, _LINKOPT]

def engine_optimization(settings, attr):
    """
    Return the engine's compiler and linker options: engine_optimize and engine_lto under -c opt.

    They follow the build's own --copt and --linkopt, so their level overrides the
    toolchain's and the command line's for engine code only. auto is Godot's own choice:
    speed for release runtimes, speed_trace for debug runtimes and editors.

    Args:
        settings: Transition inputs, OPTIMIZATION_INPUTS among them.
        attr: Attributes of the engine rule: role and variant.

    Returns:
        The --copt and --linkopt values of the engine's native graph.
    """
    copts, linkopts = settings[_COPT], settings[_LINKOPT]

    # Bazel passes the compilation mode to transitions as an enum, not as a string.
    if str(settings[_COMPILATION_MODE]) != "opt":
        return {_COPT: copts, _LINKOPT: linkopts}
    level = settings[_ENGINE_OPTIMIZE]
    if level == "auto":
        level = "speed" if attr.role == "runtime" and attr.variant == "release" else "speed_trace"
    lto = _LTO_OPTIONS[settings[_ENGINE_LTO]]
    return {_COPT: copts + _OPTIMIZE_OPTIONS[level] + lto, _LINKOPT: linkopts + lto}
