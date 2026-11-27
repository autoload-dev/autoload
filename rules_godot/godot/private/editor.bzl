"""Open a project in the Godot editor on an editor view of the checkout, and sync its metadata."""

load("//godot/engine/private:selection.bzl", "ENGINE_ATTRS", "engine_transition")
load("//godot/private:execution.bzl", "RUN_EXEC_GROUPS", "exec_group_editor")
load("//godot/private:metadata.bzl", "METADATA_ATTRS", "metadata_kinds")
load("//godot/private:paths.bzl", "with_extensions_for")
load("//godot/private:run.bzl", "import_results", "launcher")
load("//godot/private:sync.bzl", "declare_sync", "sync_launcher", "sync_rules")
load("//godot/private:view.bzl", "GodotViewInfo", "declare_view")

visibility("//godot/...")

# Where editor views live, relative to the workspace; Bazel must ignore it.
_VIEWS = ".godot-editor"

def _in_checkout(file):
    """Whether a file is a source of the main repository, so an editor view can link it."""
    return file.is_source and not file.owner.repo_name

def _split(resource_paths):
    """
    Split a project's files into checkout sources and the rest.

    Args:
        resource_paths: dicts of resource paths to Files.

    Returns:
        Resource paths of checkout sources to their workspace paths, and resource
        paths of the other files to those Files.
    """
    checkout = {}
    copies = {}
    for files in resource_paths:
        for path, file in files.items():
            if _in_checkout(file):
                checkout[path] = file.path
            else:
                copies[path] = file
    return checkout, copies

def _godot_editor_impl(ctx):
    tc = exec_group_editor(ctx, "run")
    project = ctx.attr.view[GodotViewInfo]

    # Imports and caches stay the build's; the editor on the host loads the extension host
    # editor libraries.
    editor_resource_paths = with_extensions_for(
        project.editor_resource_paths,
        project.export_extensions,
        "host_editor",
    )
    checkout, copies = _split([editor_resource_paths, project.import_resource_paths])
    import_fields, inputs = import_results(ctx, project, project.editor_imports)
    authored = project.project.authored_project_file
    data = dict(
        import_fields,
        label = str(ctx.label),
        workspace = ctx.workspace_name,
        editor = tc.editor.executable.short_path,
        views = _VIEWS,
        view = "/".join([
            part
            for part in [_VIEWS, ctx.label.package, ctx.label.name]
            if part
        ]),
        env = ctx.attr.env,
        project_file = project.editor_project_file.short_path,
        authored_project_file = authored.path if _in_checkout(authored) else "",
        composed_settings = project.composed_settings,
        checkout = checkout,
        metadata = project.metadata.short_path,
        write_sidecars = ctx.attr.write_sidecars,
        copies = {path: file.short_path for path, file in copies.items()},
    )
    executable, manifest = launcher(ctx, data)
    runfiles = ctx.runfiles(
        files = [
            manifest,
            project.editor_project_file,
            project.metadata,
            tc.editor.executable,
            ctx.executable._runner,
        ] + copies.values(),
        transitive_files = depset(transitive = [tc.files, inputs]),
    )
    runfiles = runfiles.merge(ctx.attr._runner[DefaultInfo].default_runfiles)
    return [DefaultInfo(executable = executable, runfiles = runfiles)]

_godot_editor = rule(
    doc = "Open a project in the Godot editor on an editor view; the rule behind godot_editor.",
    implementation = _godot_editor_impl,
    attrs = {
        "view": attr.label(
            doc = "The view of the project to edit.",
            mandatory = True,
            providers = [GodotViewInfo],
        ),
        "env": attr.string_dict(
            doc = "Environment variables set for the editor, besides the user's own.",
        ),
        "write_sidecars": attr.bool(
            doc = """
            Write the sidecars the checkout lacks before the editor opens, as
            godot_metadata_sync does. Without it, the run names them and Godot writes its
            own when it finds the files, reimporting assets.
            """,
            default = True,
        ),
        "_runner": attr.label(
            default = Label("//tools:godot_editor"),
            executable = True,
            cfg = config.exec("run"),
        ),
        "_launcher_template": attr.label(
            default = Label("//godot/private:run_launcher.sh.tpl"),
            allow_single_file = True,
        ),
    } | ENGINE_ATTRS,
    executable = True,
    exec_groups = RUN_EXEC_GROUPS,
    cfg = engine_transition,
)

def godot_editor(name, project, deps = [], env = {}, write_sidecars = True, engine = "", **kwargs):
    """
    Open a project in the Godot editor with `bazel run`, editing the checkout.

    The editor view is a Godot project under `.godot-editor/<package>/<name>` in the
    workspace. Its files from this repository are symbolic links into the
    checkout, so what the editor saves changes the checkout. A directory whose
    files all come from one checkout directory at the same relative paths is
    linked as a whole, so files the editor creates, renames or deletes there
    change the checkout too. Generated files, files of other repositories, such
    as add-ons, and extension descriptors and libraries are read-only copies;
    the editor loads the extension host editor libraries. The project's imports and
    Godot's caches come from the build, so the editor opens without
    reimporting. Before the editor opens, the run writes the sidecars the
    checkout lacks, as godot_metadata_sync does.

    The editor view holds the editor part of every add-on of the operation, with its
    editor plugin enabled in the view's project.godot. When the editor exits, settings
    it changed that come from the authored project.godot are written back to it;
    settings the project or its add-ons set are reported with the label that sets them. The runner also
    lists files that exist only in the editor view and files in linked directories that
    the project does not declare.

    Bazel must ignore the editor views: add `.godot-editor` to `.bazelignore`, or
    `bazel build //...` finds the linked packages twice. The run fails until it
    does. Arguments after `--` go to the editor.

    Example:
    ```starlark
    godot_editor(
        name = "edit",
        project = ":project",
        deps = [":game"],
    )
    ```

    `bazel run :edit` opens the editor on `.godot-editor/<package>/edit`.

    Args:
        name: Name of the executable target.
        project: The godot_project whose configuration the editor view uses.
        deps: What the editor view lists for editing: godot_resources and add-ons,
            as an IDE project view lists targets.
        env: Environment variables set for the editor, besides the user's own.
        write_sidecars: Write the sidecars the checkout lacks before the editor
            opens, as godot_metadata_sync does. Without it, the run names them and Godot
            writes its own when it finds the files, reimporting assets.
        engine: The engine the operation uses, by engine name; empty keeps the build's
            engine, the default one or the one --@autoload_rules_godot//godot:engine
            names.
        **kwargs: Common attributes, such as tags and visibility.
    """
    _godot_editor(
        name = name,
        view = declare_view(name, project, deps, kwargs, engine = engine),
        env = env,
        write_sidecars = write_sidecars,
        engine = engine,
        **kwargs
    )

def _metadata_sync_impl(ctx, test):
    project = ctx.attr.view[GodotViewInfo]
    return sync_launcher(
        ctx,
        test,
        {
            "metadata": project.metadata.short_path,
            "required": metadata_kinds(ctx, ["require"]),
        },
        ctx.runfiles(files = [project.metadata]),
    )

_METADATA_SYNC = sync_rules(
    implementation = _metadata_sync_impl,
    runner = Label("//tools:godot_metadata_sync"),
    # The godot_metadata_sync macro documents these attributes.
    attrs = {"view": attr.label(mandatory = True, providers = [GodotViewInfo])} | METADATA_ATTRS | ENGINE_ATTRS,
    docs = (
        "Write a project's missing metadata into the checkout; the rule behind godot_metadata_sync.",
        "Fail while a project's checkout lacks metadata; the test behind godot_metadata_sync.",
    ),
    editor = True,
    cfg = engine_transition,
)

_godot_metadata_sync = rule(**_METADATA_SYNC.writer)

_godot_metadata_sync_test = rule(**_METADATA_SYNC.test)

_METADATA_SYNC_RULES = struct(writer = _godot_metadata_sync, test = _godot_metadata_sync_test)

def godot_metadata_sync(name, project, deps = [], size = None, timeout = None, engine = "", **kwargs):
    """
    Write the metadata Godot keeps beside a project's checkout files, and test for it.

    Godot keeps a script's or shader's UID in a `.uid` file beside it and an
    imported asset's import settings, including its UID, in a `.import` file
    beside it; both belong in version control. Where a checkout file has none,
    the build generates them. `bazel run :<name>` writes those beside their
    files in the checkout, where none exists yet, and names the target to
    declare each in: commit them and declare them there, which a `glob` does on
    its own. Existing files are never replaced; the run names the ones that
    exist but are not declared.

    With `--@autoload_rules_godot//godot/metadata:node_ids` or
    `--@autoload_rules_godot//godot/metadata:resource_uids` at `sync` (default) or
    `require`, the run also adds the `unique_id` each node of a checkout `.tscn`
    scene lacks and the named file's UID to each `ext_resource` of a `.tscn` or
    `.tres` file whose `uid` is missing or stale: the values a pack otherwise
    adds only to the copy it exports.

    `<name>.test` fails while the build generates a sidecar for a checkout file
    and, for a metadata flag at `require`, while a file lacks those values, so
    `bazel test //...` keeps the checkout complete. It needs no checkout and
    names each sidecar with the command that writes it.

    Example:
    ```starlark
    godot_metadata_sync(
        name = "metadata",
        project = ":project",
        deps = [":game"],
    )
    ```

    Args:
        name: Name of the writer; the test is `<name>.test`.
        project: The godot_project whose configuration the files are read under.
        deps: The godot_resources whose checkout files get their metadata.
        size: Bazel test size of `<name>.test`; Bazel's default applies when unset.
        timeout: Bazel test timeout of `<name>.test`; derived from size when unset.
        engine: The engine the operation uses, by engine name; empty keeps the build's
            engine, the default one or the one --@autoload_rules_godot//godot:engine
            names.
        **kwargs: Common attributes of both targets, such as tags and visibility.
    """
    declare_sync(
        _METADATA_SYNC_RULES,
        name,
        {"view": declare_view(name, project, deps, kwargs, engine = engine), "engine": engine},
        {"size": size, "timeout": timeout},
        kwargs,
    )
