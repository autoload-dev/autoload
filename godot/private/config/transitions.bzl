"""Platform slice and content configuration transitions of a pack."""

load(
    ":settings.bzl",
    "APPLICATION_CONTEXT",
    "CPUS",
    "ENVIRONMENT",
    "EXPORT_PLATFORM",
    "OPERATING_SYSTEM",
    "PLATFORM_SLICES",
    "TOOL",
    "VARIANT",
    "ios_cpu",
)

visibility(["//godot/..."])

_PLATFORMS = "//command_line_option:platforms"
_CPU = "//command_line_option:cpu"
_APPLE_CPU = "//command_line_option:apple_split_cpu"

# rules_apple's application rules set it on their own edge; a pack built directly for an
# iOS platform needs it too, or apple_support derives a macOS CPU name such as
# darwin_sim_arm64 from the iOS split CPU.
_APPLE_PLATFORM_TYPE = "//command_line_option:apple_platform_type"
_ANDROID_PLATFORMS = "//command_line_option:android_platforms"
_ANDROID_SETTING = str(Label("@rules_android//flags:android_platforms"))
_DYNAMIC = "//command_line_option:dynamic_mode"

# iOS applications build their native code without --strip (godot/platforms/private/ios.bzl);
# a pack's iOS native code takes the same value when the pack is built by itself, so it
# needs no second configuration for the build's --strip.
_STRIP = "//command_line_option:strip"
_OUTPUTS = [_PLATFORMS, _CPU, _APPLE_CPU, _APPLE_PLATFORM_TYPE, _ANDROID_PLATFORMS, _ANDROID_SETTING, _DYNAMIC, _STRIP]
_INPUTS = _OUTPUTS + [CPUS, ENVIRONMENT, EXPORT_PLATFORM, OPERATING_SYSTEM, PLATFORM_SLICES]

def _ios_cpu(environment, cpu):
    return "ios_" + ios_cpu(environment, cpu)

def _content_impl(settings, _attr):
    values = {key: settings[key] for key in _OUTPUTS}
    export_platform = settings[EXPORT_PLATFORM]
    if not export_platform:
        return values
    operating_system = settings[OPERATING_SYSTEM]
    cpus = settings[CPUS].split(",")
    values[_PLATFORMS] = [export_platform]
    if operating_system == "ios":
        values[_CPU] = _ios_cpu(settings[ENVIRONMENT], cpus[0])
        values[_APPLE_CPU] = ""
        values[_APPLE_PLATFORM_TYPE] = "ios"
        values[_STRIP] = "never"
    elif operating_system == "android":
        values[_DYNAMIC] = "off"
        values[_ANDROID_PLATFORMS] = settings[PLATFORM_SLICES].split(",")
        values[_ANDROID_SETTING] = settings[PLATFORM_SLICES].split(",")
    return values

def _shared_slices_impl(settings, attr):
    # What a library shared by every platform slice is analyzed in: the content
    # configuration, whichever slice reached it, and without the application's context,
    # which belongs to the pack export.
    values = _content_impl(settings, attr)
    values[APPLICATION_CONTEXT] = "{}"
    return values

def _platform_slice_impl(settings, _attr):
    current = {key: settings[key] for key in _OUTPUTS}

    # The application context belongs to the pack export, not its imported project or
    # extension libraries; those stay shared across applications.
    current[APPLICATION_CONTEXT] = "{}"
    platform_slices = settings[PLATFORM_SLICES]
    if not platform_slices:
        return {"current": current}
    cpus = settings[CPUS].split(",")
    operating_system = settings[OPERATING_SYSTEM]
    results = {}
    for cpu, platform_slice in zip(cpus, platform_slices.split(",")):
        values = dict(current)
        values[_PLATFORMS] = [platform_slice]
        if operating_system == "ios":
            bazel_cpu = _ios_cpu(settings[ENVIRONMENT], cpu)
            values[_CPU] = bazel_cpu
            values[_APPLE_CPU] = bazel_cpu.removeprefix("ios_")
            values[_APPLE_PLATFORM_TYPE] = "ios"
            values[_STRIP] = "never"
        elif operating_system == "android":
            values[_DYNAMIC] = "off"
            values[_ANDROID_PLATFORMS] = []
            values[_ANDROID_SETTING] = []
        results[cpu] = values
    return results

def _project_impl(_settings, _attr):
    return {APPLICATION_CONTEXT: "{}"}

content_transition = transition(implementation = _content_impl, inputs = _INPUTS, outputs = _OUTPUTS)

# The incoming-edge transition of a rule that splits its own inputs by platform slice, so
# that every slice of an application reaches one configured target.
shared_slices_transition = transition(
    implementation = _shared_slices_impl,
    inputs = _INPUTS,
    outputs = _OUTPUTS + [APPLICATION_CONTEXT],
)
platform_slice_transition = transition(
    implementation = _platform_slice_impl,
    inputs = _INPUTS,
    outputs = _OUTPUTS + [APPLICATION_CONTEXT],
)
project_transition = transition(
    implementation = _project_impl,
    inputs = [],
    outputs = [APPLICATION_CONTEXT],
)

def _tool_impl(_settings, _attr):
    # Godot's editor is the editor variant, whatever the variant of the export it runs.
    return {TOOL: True, VARIANT: "editor"}

# The tool configuration of an extension's tool view, which editor actions and the host
# editor reach through an execution transition.
tool_transition = transition(
    implementation = _tool_impl,
    inputs = [],
    outputs = [TOOL, VARIANT],
)

def _editor_variant_impl(_settings, _attr):
    return {VARIANT: "editor"}

# What a source run stages: it runs the project with the editor, so its extensions are the
# editor variant's. Its units share their actions with those of the build's variant through
# path mapping.
editor_variant_transition = transition(
    implementation = _editor_variant_impl,
    inputs = [],
    outputs = [VARIANT],
)
