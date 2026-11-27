"""
Derive what an application's runtime leaves out from its project, and keep it in the checkout.

Sections: Derivation, Writer and test.
"""

load("//godot/engine/private:selection.bzl", "ENGINE_ATTRS", "ENGINE_DOC", "engine_transition")
load("//godot/private:actions.bzl", "run_editor_action")
load("//godot/private:execution.bzl", "EDITOR_TOOLCHAIN")
load("//godot/private:macros.bzl", "caller_package", "common_kwargs")
load("//godot/private:paths.bzl", "exec_paths")
load("//godot/private:sync.bzl", "TEST_SIZE_ATTRS", "declare_sync", "sync_launcher", "sync_rules")
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

def _sync_impl(ctx, test):
    derived = ctx.attr.derived[GodotRuntimeProfileInfo].profile
    checked_in = ctx.file.profile
    if checked_in.short_path.startswith("../") or not checked_in.is_source:
        fail("%s: profile must be a file of this repository's checkout" % ctx.label)
    return sync_launcher(
        ctx,
        test,
        {
            "built": derived.short_path,
            "checked_in": checked_in.short_path,
        },
        ctx.runfiles(files = [derived, checked_in]),
    )

_SYNC = sync_rules(
    implementation = _sync_impl,
    runner = Label("//tools:runtime_profile"),
    # The godot_runtime_profile macro documents these attributes.
    attrs = {
        "derived": attr.label(mandatory = True, providers = [GodotRuntimeProfileInfo]),
        "profile": attr.label(allow_single_file = True, mandatory = True),
    },
    docs = (
        "Write a derived runtime profile into the checkout; the rule behind godot_runtime_profile.",
        "Fail while a checked-in runtime profile differs from its derivation; the test behind godot_runtime_profile.",
    ),
    # The derivation ran the editor; the runner only compares and copies files.
    editor = False,
)

_godot_runtime_profile_writer = rule(**_SYNC.writer)

_godot_runtime_profile_test = rule(**_SYNC.test)

_SYNC_RULES = struct(writer = _godot_runtime_profile_writer, test = _godot_runtime_profile_test)

def _runtime_profile_impl(
        name,
        visibility,
        project,
        deps,
        profile,
        keep_classes,
        size,
        timeout,
        engine,
        **kwargs):
    derived = name + ".derived"
    _godot_runtime_profile_derived(
        name = derived,
        view = declare_view(name, project, deps, kwargs, engine = engine),
        keep_classes = keep_classes,
        engine = engine,
        # The caller's package may inspect the derivation, as its analysis tests do.
        **(common_kwargs(kwargs) | {"visibility": caller_package()})
    )
    declare_sync(
        _SYNC_RULES,
        name,
        {"derived": ":" + derived, "profile": profile},
        {"size": size or None, "timeout": timeout or None},
        kwargs | {"visibility": visibility},
    )

godot_runtime_profile = macro(
    doc = """
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
    `bazel run :<name>` writes the file to `profile` and says to commit it; create it empty
    before the first run, since `profile` names a file of the checkout. Register the file
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

    The macro declares the writer `<name>`, its test `<name>.test`, the derivation
    `<name>.derived` and `<name>.view`, the project the derivation reads.
    """,
    implementation = _runtime_profile_impl,
    inherit_attrs = "common",
    attrs = {
        "project": attr.label(
            doc = "The godot_project whose configuration the project is derived under.",
            mandatory = True,
            configurable = False,
        ),
        "profile": attr.label(
            doc = """
            The checked-in build profile this target writes and tests, a file of the
            package such as `release.gdbuild`.
            """,
            allow_single_file = True,
            mandatory = True,
            configurable = False,
        ),
        "deps": attr.label_list(
            doc = """
            The godot_resources and add-ons that make up the project, as for godot_pack;
            detection reads their files.
            """,
        ),
        "keep_classes": attr.string_list(
            doc = """
            Classes the profile never disables, beyond the ruleset's own list for the
            engine's minor. Name those the game creates by name or loads on some paths.
            """,
        ),
        "engine": attr.string(doc = ENGINE_DOC),
    } | TEST_SIZE_ATTRS,
)
