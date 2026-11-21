"""
Platform slice and content configuration transitions of a pack.

The native options they set come from native.bzl.
"""

load(":native.bzl", "PLATFORM_INPUTS", "PLATFORM_OPTIONS", "content_options", "platform_slice_options")
load(
    ":settings.bzl",
    "APPLICATION_CONTEXT",
    "CPUS",
    "PLATFORM_SLICES",
    "TOOL",
    "VARIANT",
)

visibility(["//godot/..."])

def _content_impl(settings, _attr):
    return {key: settings[key] for key in PLATFORM_OPTIONS} | content_options(settings)

def _shared_slices_impl(settings, attr):
    # What a library shared by every platform slice is analyzed in: the content
    # configuration, whichever slice reached it, and without the application's context,
    # which belongs to the pack export.
    values = _content_impl(settings, attr)
    values[APPLICATION_CONTEXT] = "{}"
    return values

def _platform_slice_impl(settings, _attr):
    current = {key: settings[key] for key in PLATFORM_OPTIONS}

    # The application context belongs to the pack export, not its imported project or
    # extension libraries; those stay shared across applications.
    current[APPLICATION_CONTEXT] = "{}"
    platform_slices = settings[PLATFORM_SLICES]
    if not platform_slices:
        return {"current": current}
    return {
        cpu: current | platform_slice_options(settings, cpu, platform_slice)
        for cpu, platform_slice in zip(settings[CPUS].split(","), platform_slices.split(","))
    }

def _project_impl(_settings, _attr):
    return {APPLICATION_CONTEXT: "{}"}

content_transition = transition(implementation = _content_impl, inputs = PLATFORM_INPUTS, outputs = PLATFORM_OPTIONS)

# The incoming-edge transition of a rule that splits its own inputs by platform slice, so
# that every slice of an application reaches one configured target.
shared_slices_transition = transition(
    implementation = _shared_slices_impl,
    inputs = PLATFORM_INPUTS,
    outputs = PLATFORM_OPTIONS + [APPLICATION_CONTEXT],
)
platform_slice_transition = transition(
    implementation = _platform_slice_impl,
    inputs = PLATFORM_INPUTS,
    outputs = PLATFORM_OPTIONS + [APPLICATION_CONTEXT],
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
