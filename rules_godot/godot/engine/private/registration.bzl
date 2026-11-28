"""
The toolchain registrations of engine components.

A component's macro registers its toolchains in its own package, and the godot_engines
extension registers every engine's components in one repository, which rules_godot's module
registers. Generated repositories with consumer-chosen names load this file, so its load
visibility is public.
"""

load("@bazel_skylib//lib:selects.bzl", "selects")
load("//godot/engine/private:resolution.bzl", "EDITOR_TOOLCHAIN_TYPE", "RUNTIME_TOOLCHAIN_TYPE")
load("//godot/extension/private/emscripten:sdk.bzl", "EXECUTION_PLATFORMS", "sdk_repository_name")
load("//godot/private/config:settings.bzl", "CPU_CONSTRAINTS", "ENVIRONMENT_CONSTRAINTS", "OPERATING_SYSTEM_CONSTRAINTS")

visibility("public")

_ENGINE_FLAG = Label("//godot:engine")

_DEFAULT_ENGINE = Label("//godot:default_engine")

_VARIANT_SETTINGS = {
    "debug": Label("//godot:debug"),
    "release": Label("//godot:release"),
}

# The builds a prebuilt runtime serves: its runtime needs no tuning, no build profile and
# outside -c opt or with the default engine optimization. A prebuilt runtime cannot leave
# classes out or compile otherwise, so in any other build the engine's runtime built from
# source, registered after it, serves.
_UNTUNED = Label("//godot/private:untuned")

def _engine_setting(name, engine, default_engine, tags):
    """
    Return the engine setting a component's toolchain requires.

    A component that names no engine belongs to the default engine. A named one requires its
    own private `<name>.engine` setting on --@autoload_rules_godot//godot:engine; a named
    default engine's component also serves builds that name no engine, through
    `<name>.default_engine`, which matches either.
    """
    if not engine:
        return _DEFAULT_ENGINE
    native.config_setting(
        name = name + ".engine",
        flag_values = {_ENGINE_FLAG: engine},
        visibility = ["//visibility:private"],
        tags = tags,
    )
    if not default_engine:
        return ":%s.engine" % name
    selects.config_setting_group(
        name = name + ".default_engine",
        match_any = [":%s.engine" % name, _DEFAULT_ENGINE],
        visibility = ["//visibility:private"],
    )
    return ":%s.default_engine" % name

def _component_toolchains_impl(
        name,
        visibility,
        component,
        role,
        platform,
        cpu,
        environment,
        variant,
        engine,
        default_engine,
        untuned_only,
        tags):
    constraints = [OPERATING_SYSTEM_CONSTRAINTS[platform], CPU_CONSTRAINTS[cpu]]
    if environment:
        constraints.append(ENVIRONMENT_CONSTRAINTS[environment])
    placement = {"exec_compatible_with": constraints}
    common = []
    if role == "runtime":
        placement = {"target_compatible_with": constraints}
        common = [_VARIANT_SETTINGS[variant]]
    settings = common + [_engine_setting(name, engine, default_engine, tags)]
    native.toolchain(
        name = name,
        toolchain = component,
        toolchain_type = EDITOR_TOOLCHAIN_TYPE if role == "editor" else RUNTIME_TOOLCHAIN_TYPE,
        target_settings = settings + ([_UNTUNED] if untuned_only else []),
        visibility = visibility,
        tags = tags,
        **placement
    )

def _emscripten_toolchains_impl(name, visibility, version, engine, default_engine, tags):
    setting = _engine_setting(name, engine, default_engine, tags)
    for execution, platform in EXECUTION_PLATFORMS.items():
        for kind in ["nothreads", "threads"]:
            native.toolchain(
                name = "%s_%s_%s" % (name, execution, kind),
                exec_compatible_with = platform.constraints,
                target_compatible_with = [
                    "@platforms//os:emscripten",
                    "@platforms//cpu:wasm32",
                    Label("//godot/platforms:" + kind),
                ],
                target_settings = [setting],
                toolchain = "@%s//:cc_toolchain_%s" % (sdk_repository_name(version, execution), kind),
                toolchain_type = "@bazel_tools//tools/cpp:toolchain_type",
                visibility = visibility,
                tags = tags,
            )

emscripten_toolchains = macro(
    doc = """
    Register the C/C++ toolchains that build an engine's web extensions.

    Declares one toolchain per execution platform an Emscripten release exists for and per
    threads ABI, `<name>_<execution>_<threads|nothreads>`, of the engine's Emscripten version,
    constrained to the web and the engine.
    """,
    implementation = _emscripten_toolchains_impl,
    attrs = {
        "version": attr.string(doc = "The Emscripten version of the engine's web templates.", mandatory = True, configurable = False),
        "engine": attr.string(doc = "The engine's name; empty for an unnamed default engine.", configurable = False),
        "default_engine": attr.bool(doc = "Whether the named engine is the default one.", configurable = False),
        "tags": attr.string_list(doc = "Tags of every declared target.", configurable = False),
    },
)

component_toolchains = macro(
    doc = """
    Register the toolchain of one engine component.

    Declares the `toolchain()` `<name>`, constrained to the slot's platform and to the
    settings it serves: its engine, through `<name>.engine`, and, with untuned_only, the
    builds whose runtime needs no tuning. A component's macro names it
    `<component>.toolchain`.
    """,
    implementation = _component_toolchains_impl,
    attrs = {
        "component": attr.label(
            doc = "Label of the godot_editor_component or godot_runtime_component.",
            mandatory = True,
            configurable = False,
        ),
        "role": attr.string(
            doc = "editor or runtime.",
            mandatory = True,
            configurable = False,
            values = ["editor", "runtime"],
        ),
        "platform": attr.string(
            doc = "The slot's operating system.",
            mandatory = True,
            configurable = False,
        ),
        "cpu": attr.string(
            doc = "The slot's CPU.",
            mandatory = True,
            configurable = False,
        ),
        "environment": attr.string(doc = "device or simulator for iOS runtimes.", configurable = False),
        "variant": attr.string(doc = "debug or release for runtimes.", configurable = False),
        "engine": attr.string(
            doc = "Name of the engine the component belongs to; empty for the default engine.",
            configurable = False,
        ),
        "default_engine": attr.bool(
            doc = "Whether the named engine is also the default engine.",
            configurable = False,
        ),
        "untuned_only": attr.bool(
            doc = """
            For a prebuilt runtime, whether it serves only builds whose runtime needs no
            tuning: no build profile, and outside -c opt or the default engine optimization.
            """,
            configurable = False,
        ),
        "tags": attr.string_list(doc = "Tags of every declared target.", configurable = False),
    },
)
