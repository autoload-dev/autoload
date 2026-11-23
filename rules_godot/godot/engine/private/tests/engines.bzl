"""
Engine resolution probes, payload stand-ins and the generated-repository rules engine
regressions declare.

`prebuilt_runtime` and `godot_source_binary` are re-exported from the files generated
engine repositories load, so that regression projects can declare the same payloads.
"""

load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("//godot/engine/private:generator.bzl", _godot_source_binary = "godot_source_binary")
load("//godot/engine/private:prebuilt.bzl", _prebuilt_runtime = "prebuilt_runtime")
load("//godot/private:providers.bzl", "GodotRuntimeInfo")

visibility([
    "//godot/engine/private/tests/...",
    "//godot/platforms/private/tests/...",
    "//godot/private/config/tests/...",
])

_EDITOR = Label("//godot:editor_toolchain_type")
_RUNTIME = Label("//godot:runtime_toolchain_type")

ResolvedInfo = provider(
    doc = "Toolchain resolution observed by a probe target.",
    fields = ["editor", "runtime"],
)

def _resolved(ctx, toolchain_type):
    toolchain = ctx.toolchains[toolchain_type]
    return toolchain.godot if toolchain else None

def _probe_impl(ctx):
    return [ResolvedInfo(editor = _resolved(ctx, _EDITOR), runtime = _resolved(ctx, _RUNTIME))]

resolution_probe = rule(
    doc = "Resolve both engine roles optionally and expose the selections.",
    implementation = _probe_impl,
    toolchains = [
        config_common.toolchain_type(_EDITOR, mandatory = False),
        config_common.toolchain_type(_RUNTIME, mandatory = False),
    ],
)

def _editor_probe_impl(ctx):
    return [ResolvedInfo(editor = ctx.toolchains[_EDITOR].godot, runtime = None)]

editor_probe = rule(
    doc = """
    Resolve the editor as a mandatory toolchain, as the rules that run it do, so the
    execution platform is the first one with a matching editor.
    """,
    implementation = _editor_probe_impl,
    toolchains = [_EDITOR],
)

# Payload stand-ins: an empty CcInfo without a toolchain, and source-recipe runtime facts.
def _cc_info_stand_in_impl(_ctx):
    return [DefaultInfo(), CcInfo()]

cc_info_stand_in = rule(
    doc = "Provide an empty CcInfo, for iOS runtime components that analysis tests only resolve.",
    implementation = _cc_info_stand_in_impl,
)

def _runtime_info_stand_in_impl(ctx):
    file = ctx.actions.declare_file(ctx.label.name + ".bin")
    ctx.actions.write(file, "")
    return [
        DefaultInfo(files = depset([file])),
        GodotRuntimeInfo(
            executable = file,
            files = depset([file]),
            platform = ctx.attr.platform,
            cpu = ctx.attr.cpu,
            environment = "",
            facts_source = "source",
            origin = str(ctx.label),
            version = "4.7.2",
            bundle_files = {},
            variant = ctx.attr.variant,
            debug_symbols = None,
            minimum_os = "",
        ),
    ]

runtime_info_stand_in = rule(
    doc = "Provide a desktop GodotRuntimeInfo for the given slot facts, as a source recipe does.",
    implementation = _runtime_info_stand_in_impl,
    attrs = {"cpu": attr.string(), "platform": attr.string(), "variant": attr.string()},
)

godot_source_binary = _godot_source_binary
prebuilt_runtime = _prebuilt_runtime
