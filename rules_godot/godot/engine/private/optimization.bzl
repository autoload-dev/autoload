"""
How a source-built engine compiles: under -c opt, the engine_optimize, engine_lto and
engine_vfe settings, and a source-built editor with editor_debug.

The engine rules' transitions apply these options to the engine's native graph only, so
extensions and application code keep the build's own levels.
"""

load("//godot/engine/private:selection.bzl", "ENGINE", "ENGINE_DOC")
load("//godot/private:flags.bzl", "FlagInfo")
load("//godot/private/config:native.bzl", "COMPILATION_MODE", "COPT", "LINKOPT")

visibility(["//godot/..."])

_ENGINE_OPTIMIZE = str(Label("//godot:engine_optimize"))
_ENGINE_LTO = str(Label("//godot:engine_lto"))
_ENGINE_VFE = str(Label("//godot:engine_vfe"))

# The build profile of the runtime an application packages; see //godot/private:build_profile.
BUILD_PROFILE = str(Label("//godot/private:build_profile"))

_NO_BUILD_PROFILE = str(Label("//godot/private:no_build_profile"))

# Its label as a string, which selects a runtime variant; see //godot/private:build_profile_label.
_BUILD_PROFILE_LABEL = str(Label("//godot/private:build_profile_label"))

# Whether it has one, which keeps prebuilt runtimes out; see //godot/private:profiled_runtime.
_PROFILED_RUNTIME = str(Label("//godot/private:profiled_runtime"))

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

# Compile options of virtual function elimination, which drops the vtable slots no virtual
# call reaches. Clang does it in the full LTO link: the objects carry what it needs, so no
# link needs more than -flto. Elimination tracks calls through member function pointers by
# their class, and Godot's method binds call through pointers it casts to a class that does
# not exist, unless TYPED_METHOD_BIND, its default under MSVC, keeps the bound class.
_VFE_OPTIONS = [
    "-DTYPED_METHOD_BIND",
    "-fvisibility=hidden",
    "-fwhole-program-vtables",
    "-fvirtual-function-elimination",
]

# The settings' values, for their flags and godot_app's attributes.
OPTIMIZE_VALUES = ["auto"] + _OPTIMIZE_OPTIONS.keys()
LTO_VALUES = _LTO_OPTIONS.keys()
VFE_VALUES = ["", "on", "off"]

# The engine's graph takes the settings' options and resets the settings, so engines that
# compile alike share one configuration whatever values led there.
_RESET = {_ENGINE_OPTIMIZE: "auto", _ENGINE_LTO: "none", _ENGINE_VFE: False}

OPTIMIZATION_OUTPUTS = [COPT, LINKOPT] + _RESET.keys()
OPTIMIZATION_INPUTS = OPTIMIZATION_OUTPUTS + [COMPILATION_MODE]

def engine_optimization(settings, attr):
    """
    Return the engine's --copt and --linkopt: under -c opt, the engine_* settings' options.

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
    vfe = _VFE_OPTIONS if settings[_ENGINE_VFE] else []
    return {COPT: copts + _OPTIMIZE_OPTIONS[level] + lto + vfe, LINKOPT: linkopts + lto} | _RESET

_EDITOR_DEBUG = str(Label("//godot:editor_debug"))

# The settings a source-built editor's native graph reads and resets for debugging.
EDITOR_DEBUG_OUTPUTS = [COMPILATION_MODE, _EDITOR_DEBUG]

def editor_debugging(settings, attr):
    """
    Return the compilation mode of an engine's native graph and reset //godot:editor_debug.

    With editor_debug, a source-built editor compiles in Bazel's dbg mode: with debug
    information, without optimization and unstripped. Runtimes keep the build's mode, and
    the reset setting keeps their graph's configuration whatever its value.

    Args:
        settings: Transition inputs: the compilation mode and editor_debug.
        attr: Attributes of the engine rule: role.

    Returns:
        The compilation mode and editor_debug of the engine's native graph.
    """
    mode = str(settings[COMPILATION_MODE])
    if attr.role == "editor" and settings[_EDITOR_DEBUG]:
        mode = "dbg"
    return {COMPILATION_MODE: mode, _EDITOR_DEBUG: False}

def optimization_error(compilation_mode, lto, vfe):
    """
    Return why the engine settings cannot apply together, or None.

    Elimination happens in the full LTO link, which the objects of thin LTO or of no LTO
    never reach; Clang rejects them. Other compilation modes apply none of the settings.

    Args:
        compilation_mode: The build's compilation mode.
        lto: The engine_lto value.
        vfe: The engine_vfe value.

    Returns:
        The error message, or None.
    """
    if not vfe or compilation_mode != "opt":
        return None
    if lto != "full":
        return 'engine_vfe needs engine_lto = "full", on the command line or the godot_app, not "%s"' % lto
    return None

# The settings the engine rules check before their transition applies and resets them.
OPTIMIZATION_CHECK_ATTRS = {
    "_engine_lto": attr.label(default = Label("//godot:engine_lto"), providers = [FlagInfo]),
    "_engine_vfe": attr.label(default = Label("//godot:engine_vfe"), providers = [FlagInfo]),
}

def check_optimization(ctx):
    """
    Fail the analysis of an engine rule whose engine settings cannot apply together.

    Args:
        ctx: Context of a rule with OPTIMIZATION_CHECK_ATTRS.
    """
    error = optimization_error(
        ctx.var["COMPILATION_MODE"],
        ctx.attr._engine_lto[FlagInfo].value,
        ctx.attr._engine_vfe[FlagInfo].value,
    )
    if error:
        fail("%s: %s" % (ctx.label, error))

# The attributes of the rules that resolve an application's runtime component.
ENGINE_SETTINGS_ATTRS = {
    "engine": attr.string(doc = ENGINE_DOC),
    "engine_optimize": attr.string(
        doc = "The engine_optimize of this application's source-built engine; empty keeps the build's.",
        values = [""] + OPTIMIZE_VALUES,
    ),
    "engine_lto": attr.string(
        doc = "The engine_lto of this application's source-built engine; empty keeps the build's.",
        values = [""] + LTO_VALUES,
    ),
    "engine_vfe": attr.string(
        doc = "Whether this application's source-built engine drops unreachable virtual functions: on, off, or empty to keep the build's.",
        values = VFE_VALUES,
    ),
    "build_profile": attr.label(
        doc = "The build profile whose disabled classes this application's source-built runtime leaves out; None keeps the build's.",
        allow_single_file = [".gdbuild"],
    ),
}

def tuned_engine_settings(settings, attr):
    """
    Return the engine settings an application sets at the edge to its runtime component.

    Args:
        settings: Transition inputs: the engine name, the optimization settings and the
            build profile.
        attr: Attributes of the runtime target, ENGINE_SETTINGS_ATTRS; empty values keep
            the build's.

    Returns:
        The settings the runtime component resolves and compiles with.
    """
    vfe = attr.engine_vfe
    profile = str(attr.build_profile) if attr.build_profile else str(settings[BUILD_PROFILE])
    return {
        ENGINE: attr.engine or settings[ENGINE],
        _ENGINE_OPTIMIZE: attr.engine_optimize or settings[_ENGINE_OPTIMIZE],
        _ENGINE_LTO: attr.engine_lto or settings[_ENGINE_LTO],
        _ENGINE_VFE: vfe == "on" if vfe else settings[_ENGINE_VFE],
        BUILD_PROFILE: profile,
        _BUILD_PROFILE_LABEL: profile if profile != _NO_BUILD_PROFILE else "",
        _PROFILED_RUNTIME: profile != _NO_BUILD_PROFILE,
    }

# Sets an application's engine settings where its runtime component is resolved, so the
# engine compiles with them and the rest of the application keeps the build's.
engine_settings = transition(
    implementation = tuned_engine_settings,
    inputs = [ENGINE, _ENGINE_OPTIMIZE, _ENGINE_LTO, _ENGINE_VFE, BUILD_PROFILE],
    outputs = [
        ENGINE,
        _ENGINE_OPTIMIZE,
        _ENGINE_LTO,
        _ENGINE_VFE,
        BUILD_PROFILE,
        _BUILD_PROFILE_LABEL,
        _PROFILED_RUNTIME,
    ],
)

def require_tunable_runtime(label, attr, provenance):
    """
    Fail for a build profile on a runtime that cannot leave classes out.

    Only a source recipe's class generator reads the profile; a prebuilt runtime would ship
    every class without a word.

    Args:
        label: Label of the runtime target, for the message.
        attr: Its attributes, ENGINE_SETTINGS_ATTRS.
        provenance: GodotComponentInfo of the resolved runtime component.
    """
    if attr.build_profile and provenance.kind != "source":
        fail((
            "%s: build_profile needs a runtime built from source, but the selected runtime " +
            "component %s is prebuilt. Register a source build for the slot, use a " +
            "prebuilt engine whose source_runtimes builds it, or leave build_profile unset."
        ) % (label, provenance.component))
