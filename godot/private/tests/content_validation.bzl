"""
Targets over deliberately broken content, built with failed validations reported, not failing.

A failed per-unit validation fails the build (FR-031). The ruleset's own tests of broken
scripts set //godot/private:content_validation to report for what they build: each
validation then records its failures in its output and succeeds, so a test can read them
and build the operations over the same content.
"""

load("//godot:providers.bzl", "GodotAddonInfo", "GodotProjectInfo", "GodotResourcesInfo")
load("//godot/private:context.bzl", "TRANSITION_ATTRS", "context_transition")

visibility(["//godot/private/tests/..."])

def _report_transition_impl(_settings, _attr):
    return {"//godot/private:content_validation": "report"}

_report_transition = transition(
    implementation = _report_transition_impl,
    inputs = [],
    outputs = ["//godot/private:content_validation"],
)

def _reported_build_impl(ctx):
    files = []
    for target in ctx.attr.deps:
        files.append(target[DefaultInfo].files)
        files.append(target[DefaultInfo].default_runfiles.files)
        if OutputGroupInfo in target and hasattr(target[OutputGroupInfo], "_validation"):
            files.append(target[OutputGroupInfo]._validation)
    return [DefaultInfo(files = depset(transitive = files))]

reported_build = rule(
    doc = """
    The outputs, runfiles and validation outputs of operations whose validations report
    their failures, such as a pack and a source run over a unit with a parse error.
    """,
    implementation = _reported_build_impl,
    attrs = {
        "deps": attr.label_list(mandatory = True, cfg = _report_transition),
        "_allowlist_function_transition": attr.label(default = "@bazel_tools//tools/allowlists/function_transition_allowlist"),
    },
)

def _in_context_impl(ctx):
    files = [target[DefaultInfo].default_runfiles.files for target in ctx.attr.operations]
    for target in ctx.attr.deps:
        parts = [target[GodotAddonInfo].runtime_files, target[GodotAddonInfo].editor_files] if GodotAddonInfo in target else [target[GodotResourcesInfo]]
        for part in parts:
            files.append(part.class_fragments)
            files.append(part.validations)
    return [DefaultInfo(files = depset(transitive = files))]

in_context = rule(
    doc = """
    The class fragments and validation outputs of resources and add-ons under a project's
    context, with the runfiles of operations over them, such as a source run's initialization.
    """,
    implementation = _in_context_impl,
    cfg = context_transition,
    attrs = {
        "project": attr.label(mandatory = True, providers = [GodotProjectInfo]),
        "deps": attr.label_list(providers = [[GodotResourcesInfo], [GodotAddonInfo]]),
        "operations": attr.label_list(),
    } | TRANSITION_ATTRS,
)
