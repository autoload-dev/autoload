"""The project context an operation sets for the resources it reaches.

`//godot/private:project_setting` names the `godot_project` whose configuration the imports of the current
configuration use. Operations write it on the edge to their view; native code is reached
with it reset, so it builds once whatever the number of contexts.

The context keeps the operation's platform: resources reach Android and Apple libraries,
which only analyze for their own platforms. A unit therefore imports and validates once per
project and target platform. Settings an application's edge to its pack sets for the
native code it builds, such as macOS's minimum version, return to the build's values, so a
host test and a macOS application of one project share each unit's actions; the native
code takes them on the pack's native path, outside the context.
"""

load("//godot/engine/private:selection.bzl", "ENGINE")
load("//godot/private:providers.bzl", "GodotProjectInfo")
load("//godot/private/config:native.bzl", "APPLICATION_SCOPED_OPTIONS", "outside_application_options")
load("//godot/private/config:settings.bzl", "APPLICATION_CONTEXT")

visibility(["//godot/..."])

PROJECT_SETTING = str(Label("//godot/private:project_setting"))
NO_PROJECT = str(Label("//godot/private:no_project"))

# The attribute every rule with a transition of its own declares.
TRANSITION_ATTRS = {
    "_allowlist_function_transition": attr.label(
        default = "@bazel_tools//tools/allowlists/function_transition_allowlist",
    ),
}

def _context_impl(settings, attr):
    project = getattr(attr, "project", None)
    return {
        PROJECT_SETTING: str(project) if project else NO_PROJECT,
        # The operation's engine, so a view built by itself, as `bazel build //...` builds
        # it, imports with the same engine as under its operation.
        ENGINE: getattr(attr, "engine", "") or settings[ENGINE],
        # An application's context belongs to its pack export, not to the imports.
        APPLICATION_CONTEXT: "{}",
    } | outside_application_options(settings)

context_transition = transition(
    implementation = _context_impl,
    inputs = [ENGINE] + APPLICATION_SCOPED_OPTIONS,
    outputs = [PROJECT_SETTING, APPLICATION_CONTEXT, ENGINE] + APPLICATION_SCOPED_OPTIONS,
)

def _reset_impl(_settings, _attr):
    return {PROJECT_SETTING: NO_PROJECT}

reset_transition = transition(
    implementation = _reset_impl,
    inputs = [],
    outputs = [PROJECT_SETTING],
)

def _no_project_impl(ctx):
    return [GodotProjectInfo(
        label = ctx.label,
        import_configuration = None,
        importable = None,
        importers = {},
        authored_project_file = None,
        authored_autoloads = None,
        settings = {},
        setting_overrides = {},
        autoloads = {},
        autoload_overrides = {},
        main_scene = "",
        context_files = {},
        named_addons = depset(),
        custom_features = [],
        flag_settings = {},
    )]

no_project = rule(
    doc = "The default of //godot:project: a context that imports nothing.",
    implementation = _no_project_impl,
)

def is_context(project):
    """Whether a GodotProjectInfo read through //godot:project names a real project."""
    return project.import_configuration != None
