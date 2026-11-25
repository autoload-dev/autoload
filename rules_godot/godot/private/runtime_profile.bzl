"""
Derive what an application's runtime leaves out from its project, and keep it in the checkout.

Sections: Derivation, Writer and test.
"""

load("@platforms//host:constraints.bzl", "HOST_CONSTRAINTS")
load("//godot/engine/private:selection.bzl", "ENGINE_ATTRS", "engine_transition")
load("//godot/private:actions.bzl", "run_editor_action")
load("//godot/private:execution.bzl", "EDITOR_TOOLCHAIN")
load("//godot/private:macros.bzl", "common_kwargs")
load("//godot/private:paths.bzl", "exec_paths")
load("//godot/private:run.bzl", "launcher")
load("//godot/private:view.bzl", "GodotViewInfo", "declare_view")
load("//godot/private/engine:profiles.bzl", "engine_profile")

visibility("//godot/...")

GodotRuntimeProfileInfo = provider(
    doc = "The profile godot_runtime_profile derives, which its writer and test compare with the checkout.",
    fields = {
        "profile": "File: the build profile (.gdbuild) of the classes and build options the runtime leaves out",
    },
)

# ==== Derivation ==============================================================

def _derived_impl(ctx):
    tc = ctx.toolchains[EDITOR_TOOLCHAIN].godot
    view = ctx.attr.view[GodotViewInfo]
    defaults = engine_profile(tc.version)["runtime_profile"]
    profile = ctx.actions.declare_file(ctx.label.name + ".gdbuild")

    # The editor opens the project as an editor view does, with the editor part of its
    # add-ons, so plugins and extensions register the classes the project's files use.
    members = view.editor_resource_paths
    run_editor_action(
        ctx,
        "derive",
        ".derive",
        profile,
        {
            "project_file": view.editor_project_file.path,
            "member_resource_paths": exec_paths(members),
            "keep_classes": sorted({name: True for name in defaults["keep_classes"] + ctx.attr.keep_classes}),
            "unknown_options": defaults["unknown_options"],
            "implied_options": defaults["implied_options"],
        },
        depset([view.editor_project_file] + members.values()),
        view.editor_imports,
        "GodotRuntimeProfile",
        "Deriving the runtime profile of %{label}",
    )
    return [
        DefaultInfo(files = depset([profile])),
        GodotRuntimeProfileInfo(profile = profile),
    ]

_godot_runtime_profile_derived = rule(
    doc = "Derive a runtime profile from a project with the selected engine's editor; the rule behind godot_runtime_profile.",
    implementation = _derived_impl,
    attrs = {
        "view": attr.label(
            doc = "The view of the project to derive from.",
            mandatory = True,
            providers = [GodotViewInfo],
        ),
        "keep_classes": attr.string_list(
            doc = "Classes the profile never disables, besides the ruleset's own list.",
        ),
        "_actions": attr.label(
            default = Label("//tools:runtime_profile"),
            executable = True,
            cfg = "exec",
        ),
    } | ENGINE_ATTRS,
    toolchains = [EDITOR_TOOLCHAIN],
    cfg = engine_transition,
)

# ==== Writer and test =========================================================

def _target_path(ctx, name):
    """The workspace path of a checked-in file named relative to the package."""
    return "/".join([part for part in [ctx.label.package, name] if part])

def _sync_impl(ctx, test):
    derived = ctx.attr.derived[GodotRuntimeProfileInfo]
    checked_in = {file.short_path: file for file in ctx.files.checked_in}
    target = _target_path(ctx, ctx.attr.profile)
    entries = [{
        "built": derived.profile.short_path,
        "checked_in": checked_in[target].short_path if target in checked_in else "",
        "target": target,
    }]
    executable, manifest = launcher(ctx, {
        "workspace": ctx.workspace_name,
        "files": entries,
        "test": test,
        "writer": ctx.attr.writer,
    })
    runfiles = ctx.runfiles(
        files = [manifest, derived.profile, ctx.executable._runner] + ctx.files.checked_in,
    )
    runfiles = runfiles.merge(ctx.attr._runner[DefaultInfo].default_runfiles)
    return [DefaultInfo(executable = executable, runfiles = runfiles)]

def _writer_impl(ctx):
    return _sync_impl(ctx, test = False)

def _test_impl(ctx):
    return _sync_impl(ctx, test = True)

# The godot_runtime_profile macro documents these attributes.
_SYNC_ATTRS = {
    "derived": attr.label(mandatory = True, providers = [GodotRuntimeProfileInfo]),
    "checked_in": attr.label_list(allow_files = True),
    "profile": attr.string(mandatory = True),
    "writer": attr.string(),
    "_launcher_template": attr.label(
        default = Label("//godot/private:run_launcher.sh.tpl"),
        allow_single_file = True,
    ),
}

def _runner(group):
    """The runner, built for the execution platform of the run's or test's exec group."""
    return {"_runner": attr.label(
        default = Label("//tools:runtime_profile"),
        executable = True,
        cfg = config.exec(group),
    )}

_godot_runtime_profile_writer = rule(
    doc = "Write a derived runtime profile into the checkout; the rule behind godot_runtime_profile.",
    implementation = _writer_impl,
    attrs = _SYNC_ATTRS | _runner("run"),
    executable = True,
    # The writer runs Python on the host; the editor ran in the derivation.
    exec_groups = {"run": exec_group(exec_compatible_with = HOST_CONSTRAINTS)},
)

_godot_runtime_profile_test = rule(
    doc = "Fail while a checked-in runtime profile differs from its derivation; the test behind godot_runtime_profile.",
    implementation = _test_impl,
    attrs = _SYNC_ATTRS | _runner("test"),
    test = True,
    exec_groups = {"test": exec_group(toolchains = [
        config_common.toolchain_type("@bazel_tools//tools/test:default_test_toolchain_type", mandatory = False),
    ])},
)

def godot_runtime_profile(
        name,
        project,
        profile,
        deps = [],
        keep_classes = [],
        size = None,
        timeout = None,
        engine = "",
        **kwargs):
    """
    Derive from a project what an application's runtime leaves out, and keep it in the checkout.

    A runtime that leaves out the engine classes and build options a game never uses is
    smaller; see [engine size](../../engine-size.md#4-use-a-build-profile). Godot's editor finds them:
    its Engine Compilation Configuration editor detects what a project's scenes, resources
    and scripts use, and the rule runs that detection headless, with the editor of the
    engine named by `engine`, on the project as an editor view stages it. It needs no
    engine build, only the editor.

    The result is one build profile (`.gdbuild`), as Godot writes it: `disabled_classes` and
    `disabled_build_options`, which lists the build options and module switches the
    detection turns off, such as `disable_physics_3d` and `module_openxr_enabled`. The
    classes the engine needs whatever the project names, which the ruleset lists for the
    engine's minor, and `keep_classes` are taken out of `disabled_classes`.
    `bazel run :<name>` writes the file to `profile` and says to commit it. Register the file
    in `MODULE.bazel` with a `godot_engines.runtime_profile` tag, and name it as `godot_app`'s
    `build_profile`: the application's runtime then leaves out those classes and options.

    `<name>.test` fails while the file is missing or differs from the derivation, with the
    command that writes it, so `bazel test //...` keeps the profile current when the project
    changes. The derivation is a build action: Bazel caches it with the project's imports
    and the editor, and reruns it when a scene, resource, script or add-on changes.

    Detection reads files, so it does not see a class that code creates by name or that
    only some paths of the game load. Review the classes and name those in `keep_classes`;
    an application that loads a class its runtime lacks fails when it loads it. Detection
    also names classes the engine creates itself; the ruleset's list covers those it knows.

    Example:
    ```starlark
    godot_runtime_profile(
        name = "update_profile",
        project = ":project",
        deps = [":game"],
        profile = "release.gdbuild",
        keep_classes = ["Camera3D"],
    )
    ```

    `bazel run :update_profile` writes `release.gdbuild`.

    ### Default outputs
    - executable (one): run writes the derived profile to the checkout; the derivation is built, not run

    ### Generated targets
    - `{name}.test` (test): Execute the comparison of the checked-in profile with the derivation as a Bazel test; an output group cannot execute tests
      - purpose: test
      - visibility: caller
      - testonly: true
      - prerequisites: the derived profile, which needs the execution-platform editor and the project's imports

    Args:
        name: Name of the writer; the test is `<name>.test`.
        project: The godot_project whose configuration the project is derived under.
        profile: The checked-in build profile this target writes and tests, as a path relative
            to the package, such as `release.gdbuild`.
        deps: The godot_resources and add-ons that make up the project, as for godot_pack;
            detection reads their files.
        keep_classes: Classes the profile never disables, beyond the ruleset's own list for
            the engine's minor. Name those the game creates by name or loads on some paths.
        size: Bazel test size of `<name>.test`; Bazel's default applies when unset.
        timeout: Bazel test timeout of `<name>.test`; derived from size when unset.
        engine: The engine whose editor detects, by engine name; empty keeps the build's
            engine, the default one or the one --@autoload_rules_godot//godot:engine
            names.
        **kwargs: Common attributes of every target, such as tags and visibility.
    """
    derived = name + ".derived"
    _godot_runtime_profile_derived(
        name = derived,
        view = declare_view(name, project, deps, kwargs, engine = engine),
        keep_classes = keep_classes,
        engine = engine,
        **(common_kwargs(kwargs) | {"visibility": ["//visibility:private"]})
    )

    # The label as a user types it: the main repository's `@@` prefix names no repository.
    writer = str(native.package_relative_label(name)).removeprefix("@@")
    checked_in = native.glob([profile], allow_empty = True)
    _godot_runtime_profile_writer(
        name = name,
        derived = ":" + derived,
        checked_in = checked_in,
        profile = profile,
        writer = writer,
        **kwargs
    )
    _godot_runtime_profile_test(
        name = name + ".test",
        size = size,
        timeout = timeout,
        derived = ":" + derived,
        checked_in = checked_in,
        profile = profile,
        writer = writer,
        **kwargs
    )
