"""Add-ons: a runtime part, an editor part with its roles, extensions, platform libraries and contributions, declared once."""

load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("@rules_java//java/common:java_info.bzl", "JavaInfo")
load("//godot/platforms/private:manifest_graph.bzl", "manifest_graph_aspect")
load("//godot/private:actions.bzl", "write_manifest")
load("//godot/private:configuration.bzl", "validate_autoloads", "validate_settings")
load("//godot/private:context.bzl", "TRANSITION_ATTRS", "is_context", "reset_transition")
load("//godot/private:execution.bzl", "EDITOR_TOOLCHAIN")
load("//godot/private:import_units.bzl", "VALIDATION_ATTRS", "class_fragment", "import_unit", "unit_interface", "validate_unit")
load("//godot/private:paths.bzl", "directory_prefix", "explicit_resource_paths", "godot_ignore_markers", "godot_ignored", "mapped_paths", "merge_resource_paths", "placed_resource_paths", "sidecar_source", "validate_namespace", "with_extensions_for")
load("//godot/private:providers.bzl", "GodotAddonInfo", "GodotExtensionInfo", "GodotProjectInfo", "GodotResourcesInfo")
load("//godot/private:resources.bzl", "addon_closure", "configuration_contributions", "import_staged", "unique_extensions", "unique_platform_libraries")

visibility(["//godot/..."])

_PlatformLibrariesInfo = provider(
    doc = "The platform libraries of an add-on, reached through its <name>.platform_libraries helper.",
    fields = {"libraries": "list[Target] of Android and Apple libraries"},
)

def _platform_libraries_impl(ctx):
    return [_PlatformLibrariesInfo(libraries = ctx.attr.deps)]

# The add-on's path to its platform libraries. Its deps edge is what rules_android's and
# rules_apple's aspects follow, and the reset builds the libraries once, in the
# configuration a direct dependency has, whatever the number of contexts reaching it.
_addon_platform_libraries = rule(
    implementation = _platform_libraries_impl,
    cfg = reset_transition,
    attrs = {
        "deps": attr.label_list(providers = [[JavaInfo], [CcInfo]], aspects = [manifest_graph_aspect]),
    } | TRANSITION_ATTRS,
)

def _part(owner, files, imports = depset(), resource_path_manifests = depset(), relationships = [], deps = [], class_fragments = depset(), interfaces = depset(), interfaced = depset(), validations = depset(), ignored = None):
    """The GodotResourcesInfo of one part: its files as one import unit, and those of them Godot ignores."""
    if ignored == None:
        ignored = {path: files[path] for path in godot_ignored(files)}
    return GodotResourcesInfo(
        imports = imports,
        units = [{"owner": owner, "outputs": sorted(files), "deps": deps}] if files else [],
        unit_heads = [owner] if files else [],
        resource_path_manifests = resource_path_manifests,
        member_resource_paths = files,
        import_resource_paths = {},
        member_owners = {path: owner for path in files},
        import_owners = {},
        ignored_resource_paths = ignored,
        relationships = depset(relationships),
        addons = depset(),
        class_fragments = class_fragments,
        interfaces = interfaces,
        interfaced_resource_paths = interfaced,
        validations = validations,
    )

def extension_addon(label, extension):
    """
    The add-on an extension is by itself: only that extension (FR-025).

    Args:
        label: Label of the extension target.
        extension: Its GodotExtensionInfo.

    Returns:
        The GodotAddonInfo the extension rules provide.
    """
    owner = str(label)
    return GodotAddonInfo(
        label = label,
        directory = "",
        runtime_files = _part(owner, {}),
        editor_files = _part(owner, {}),
        plugin_config = "",
        importer_suffixes = [],
        importer_resource_paths = {},
        importer_resource_path_manifest = None,
        import_settings = [],
        extensions = [extension],
        platform_libraries = unique_platform_libraries(extension.platform_libraries),
        platform_contributions = extension.platform_contributions,
        autoloads = [],
        settings = [],
        addons = depset(),
    )

def _placed(ctx, srcs, resource_paths, prefix):
    """Place a part's files below the add-on's directory, as srcs and resource_paths place resources."""
    outside = "every file of the add-on %s lives below its directory res://%s" % (ctx.label, prefix)
    paths = placed_resource_paths(ctx, srcs, prefix, outside)
    explicit = explicit_resource_paths(ctx, resource_paths)
    for path in explicit:
        if not path.startswith(prefix):
            fail("%s: res://%s is outside res://%s; %s" % (ctx.label, path, prefix, outside))
    merge_resource_paths(paths, explicit, owner = str(ctx.label))
    return paths

def _passed_on(part, field):
    """The field of each part this one uses, when it passes them on as resources pass on their dependencies'."""
    return [getattr(used, field) for used in part.parts] if part.passes_on_imports else []

def _own_results(ctx, context, part, staging):
    """
    Import the part's own files under the context and derive what reads the import.

    Returns:
        A struct of the part's import result, class fragments, interface and validations;
        none of them without a context or files.
    """
    if not part.files or not is_context(context):
        return struct(result = None, fragments = [], interface = None, interfaced = [], validations = [])
    unit = struct(suffix = part.suffix, owner = str(ctx.label), files = part.files, ignored = staging.ignored)
    result = import_unit(ctx, context, unit, struct(
        resource_path_manifests = staging.resource_path_manifests,
        inputs = staging.inputs,
        imports = staging.used_imports,
    ))
    fragments = class_fragment(ctx, unit)
    interface = unit_interface(ctx, unit, result)
    validations = validate_unit(ctx, context, unit, struct(
        own_import = result,
        fragments = fragments,
        uses = part.parts,
        extensions = part.used.extensions,
        autoloads = part.used.autoloads,
        runs_in_editor = part.runs_in_editor,
    ))
    return struct(
        result = result,
        fragments = fragments,
        interface = interface.interface,
        interfaced = interface.interfaced,
        validations = validations,
    )

def _import_part(ctx, context, part):
    """
    Import one part under the context after the parts it uses, as resources import after their dependencies, and validate it.

    Args:
        ctx: Analysis context of the add-on.
        context: GodotProjectInfo of the context, or no context.
        part: struct of the part: suffix, distinguishing its outputs; files, its resource
            paths to Files; parts, GodotResourcesInfo of the parts it uses (FR-024),
            whose assets, never scripts or scenes, its import stages and whose import
            results it reads; used, the extensions and autoload contributions of the
            add-on and the add-ons it needs, which its validation loads;
            passes_on_imports, whether its imports and class fragments also hold those
            of the parts it uses, as those of resources hold their dependencies' (a view
            stages only the editor parts of its roles, so an editor part passes on
            none); relationships, its edges; and runs_in_editor, whether it runs only in
            the editor, which loads every extension's tool library.

    Returns:
        The part's GodotResourcesInfo; its own import result is empty without a context
        or files.
    """
    files = part.files

    # The part decides once which of its files Godot ignores.
    ignored = {path: files[path] for path in godot_ignored(files)}
    staged = import_staged(files, ignored)
    manifests = [write_manifest(ctx, part.suffix + ".resource_paths", mapped_paths(staged))] if staged else []
    staging = struct(
        ignored = ignored,
        resource_path_manifests = depset(manifests, transitive = [used.resource_path_manifests for used in part.parts]),
        inputs = depset(
            staged.values(),
            transitive = [depset(import_staged(used.member_resource_paths, used.ignored_resource_paths).values()) for used in part.parts],
        ),
        used_imports = depset(transitive = [used.imports for used in part.parts]),
    )
    own = _own_results(ctx, context, part, staging)
    return _part(
        str(ctx.label),
        files,
        imports = depset(
            [own.result] if own.result else [],
            transitive = [staging.used_imports] if part.passes_on_imports else [],
        ),
        resource_path_manifests = staging.resource_path_manifests,
        relationships = part.relationships,
        deps = sorted({head: True for used in part.parts for head in used.unit_heads}),
        class_fragments = depset(own.fragments, transitive = _passed_on(part, "class_fragments")),
        interfaces = depset(
            [own.interface] if own.interface else [],
            transitive = _passed_on(part, "interfaces"),
        ),
        interfaced = depset(own.interfaced, transitive = _passed_on(part, "interfaced_resource_paths")),
        validations = depset(own.validations),
        ignored = ignored,
    )

def _validate_autoloads(label, autoloads, runtime_files, needed):
    """Fail for an autoload naming no file of the runtime part or of the needed add-ons' runtime parts."""
    for name, value in autoloads.items():
        path = value.removeprefix("*").removeprefix("res://")
        if path not in runtime_files and not [addon for addon in needed if path in addon.runtime_files.member_resource_paths]:
            fail((
                "%s: autoload %s names res://%s, which is no file of the add-on's runtime part " +
                "or of the runtime parts of the add-ons it needs"
            ) % (label, name, path))

def _is_file_suffix(suffix):
    """Whether a suffix is lowercase and holds no dot or slash."""
    if not suffix or suffix != suffix.lower():
        return False
    return "." not in suffix and "/" not in suffix

def _importer_suffixes(label, suffixes):
    """Check the declared importer suffixes: lowercase, without a dot, each once."""
    for suffix in suffixes:
        if not _is_file_suffix(suffix):
            fail("%s: importer suffix %r must be a lowercase file suffix without a dot, such as \"md\"" % (label, suffix))
    return sorted({suffix: True for suffix in suffixes})

def _import_settings(label, keys, settings):
    """The keys of the settings the importer reads at import time; each must be one of settings."""
    for key in keys:
        if key not in settings:
            fail("%s: import_settings names %s, which is no key of its settings" % (label, key))
    return sorted(keys)

def _importer_resource_paths(runtime_files, editor_files, extensions, closure):
    """What an importer of the add-on needs to run: both parts of it and of the add-ons it needs, with their extensions' editor files."""
    paths = dict(runtime_files)
    paths.update(editor_files)
    for addon in closure:
        paths.update(addon.runtime_files.member_resource_paths)
        paths.update(addon.editor_files.member_resource_paths)
    return with_extensions_for(paths, extensions, "editor")

def _validate_sidecars(label, runtime_files, editor_files):
    """Fail for a sidecar declared in the other part than its source: it is metadata of that file (FR-032)."""
    for part, other, other_attr in [(runtime_files, editor_files, "editor_srcs"), (editor_files, runtime_files, "srcs")]:
        for path in part:
            source = sidecar_source(path)
            if source and source in other:
                fail("%s: res://%s belongs in %s with res://%s; a sidecar is metadata of its file" % (
                    label,
                    path,
                    other_attr,
                    source,
                ))

def _fail_for_ignored(label, marker, other, part_attr):
    """Fail for a file of the other part in the directory a marker makes Godot skip."""
    directory = marker.rpartition("/")[0] + "/"
    for path in other:
        if path.startswith(directory):
            fail("%s: res://%s is in a directory Godot ignores; it belongs in %s with res://%s" % (
                label,
                path,
                part_attr,
                marker,
            ))

def _validate_ignored(label, runtime_files, editor_files):
    """Fail for a file in the other part than the marker that makes Godot skip its directory."""
    for part, other, part_attr in [(runtime_files, editor_files, "srcs"), (editor_files, runtime_files, "editor_srcs")]:
        for marker in godot_ignore_markers(part):
            _fail_for_ignored(label, marker, other, part_attr)

def _addon_parts(ctx, prefix):
    """
    Place both parts' files below the add-on's directory and check what each part holds.

    Returns:
        A struct of the runtime and editor parts' resource paths to Files and the editor
        part's plugin.cfg res:// path, or empty without an editor part.
    """
    runtime_files = _placed(ctx, ctx.attr.srcs, ctx.attr.resource_paths, prefix)
    editor_files = _placed(ctx, ctx.attr.editor_srcs, ctx.attr.editor_resource_paths, prefix)
    for path in runtime_files:
        if path in editor_files:
            fail("%s: res://%s is in both srcs and editor_srcs; a file belongs to one part" % (ctx.label, path))
        if path.rpartition("/")[2] == "plugin.cfg":
            fail("%s: res://%s belongs in editor_srcs; the editor part holds the plugin" % (ctx.label, path))
    _validate_sidecars(ctx.label, runtime_files, editor_files)
    _validate_ignored(ctx.label, runtime_files, editor_files)
    validate_namespace(runtime_files | editor_files)
    configs = sorted([path for path in editor_files if path.rpartition("/")[2] == "plugin.cfg"])
    if editor_files and len(configs) != 1:
        fail("%s: editor_srcs must contain exactly one plugin.cfg, found %s" % (ctx.label, configs))
    return struct(
        runtime_files = runtime_files,
        editor_files = editor_files,
        plugin_config = configs[0] if configs else "",
    )

def _classified_deps(ctx):
    """
    Classify the add-on's deps: its extensions, the add-ons it needs and its platform libraries.

    Every extension in deps is the add-on's, wherever its descriptor lies.
    """
    extensions = []
    needed = []
    platform_libraries = []
    for target in ctx.attr.deps:
        if GodotExtensionInfo in target:
            extension = target[GodotExtensionInfo]
            extensions.append(extension)
            platform_libraries.extend(extension.platform_libraries)
        elif GodotAddonInfo in target:
            needed.append(target[GodotAddonInfo])
        elif _PlatformLibrariesInfo in target:
            platform_libraries.extend(target[_PlatformLibrariesInfo].libraries)
        else:
            fail((
                "%s: %s in deps is no godot_addon or extension; declare platform libraries " +
                "such as an android_library in platform_deps"
            ) % (ctx.label, target.label))
    return struct(extensions = extensions, needed = needed, platform_libraries = platform_libraries)

def _checked_importer_suffixes(ctx, parts, extensions):
    """The declared importer suffixes, which need an editor part with a plugin.cfg or an extension."""
    importer_suffixes = _importer_suffixes(ctx.label, ctx.attr.importer_suffixes)
    if not importer_suffixes:
        return []
    if not (parts.editor_files or extensions):
        fail("%s: importer_suffixes needs an editor part with a plugin.cfg or an extension" % ctx.label)
    return importer_suffixes

def _used(ctx, extensions, closure):
    """
    What the add-on's parts use: the add-ons it needs, and their and its own extensions and autoloads.

    Returns:
        A struct of the closure of needed add-ons, the unique extensions, the add-on's own
        autoload contributions and those of the closure followed by its own, which the
        parts' validations load.
    """
    own_autoloads = configuration_contributions(ctx.attr.autoloads, str(ctx.label))
    return struct(
        closure = closure,
        extensions = unique_extensions(extensions + [extension for addon in closure for extension in addon.extensions]),
        own_autoloads = own_autoloads,
        autoloads = [autoload for addon in closure for autoload in addon.autoloads] + own_autoloads,
    )

def _importer_staging(ctx, context, parts, used):
    """
    What an importer of the add-on needs to run, and its manifest outside every context.

    Imports find the add-on in their project's index, outside every context.
    """
    paths = _importer_resource_paths(parts.runtime_files, parts.editor_files, used.extensions, used.closure)
    manifest = None
    if not is_context(context):
        manifest = write_manifest(ctx, ".importer.resource_paths", mapped_paths(paths))
    return paths, manifest

def _import_parts(ctx, context, parts, used):
    """
    Import both parts under the context of an operation, each after what it may use.

    Under the context of an operation the add-on imports its parts, whether the
    operation's content uses it or its project names it. The runtime part may use the
    runtime parts of the add-ons it needs, the editor part its runtime part and both
    parts of those add-ons (FR-024).

    Returns:
        The GodotResourcesInfo of the runtime and the editor part.
    """
    needed_runtime = [addon.runtime_files for addon in used.closure]
    runtime = _import_part(ctx, context, struct(
        suffix = ".runtime",
        files = parts.runtime_files,
        parts = needed_runtime,
        used = used,
        passes_on_imports = True,
        relationships = [("", path, "membership", str(ctx.label)) for path in sorted(parts.runtime_files)],
        runs_in_editor = False,
    ))
    editor = _import_part(ctx, context, struct(
        suffix = ".editor",
        files = parts.editor_files,
        parts = [runtime] + needed_runtime + [addon.editor_files for addon in used.closure],
        used = used,
        passes_on_imports = False,
        relationships = [],
        runs_in_editor = True,
    ))
    return runtime, editor

def _addon_impl(ctx):
    owner = str(ctx.label)
    prefix = directory_prefix(ctx.attr.directory)
    if not prefix:
        fail("%s: directory must name a directory below res://" % ctx.label)
    parts = _addon_parts(ctx, prefix)
    deps = _classified_deps(ctx)
    importer_suffixes = _checked_importer_suffixes(ctx, parts, deps.extensions)
    validate_settings(ctx.attr.settings)
    validate_autoloads(ctx.attr.autoloads)
    addons = addon_closure(deps.needed)
    closure = addons.to_list()
    _validate_autoloads(ctx.label, ctx.attr.autoloads, parts.runtime_files, closure)

    context = ctx.attr._project[GodotProjectInfo]
    used = _used(ctx, deps.extensions, closure)
    importer_resource_paths, importer_resource_path_manifest = {}, None
    if importer_suffixes:
        importer_resource_paths, importer_resource_path_manifest = _importer_staging(ctx, context, parts, used)
    runtime, editor = _import_parts(ctx, context, parts, used)
    return [
        DefaultInfo(files = depset(parts.runtime_files.values() + parts.editor_files.values())),
        OutputGroupInfo(_validation = depset(transitive = [runtime.validations, editor.validations])),
        GodotAddonInfo(
            label = ctx.label,
            directory = prefix.rstrip("/"),
            runtime_files = runtime,
            editor_files = editor,
            plugin_config = parts.plugin_config,
            importer_suffixes = importer_suffixes,
            importer_resource_paths = importer_resource_paths,
            importer_resource_path_manifest = importer_resource_path_manifest,
            import_settings = _import_settings(ctx.label, ctx.attr.import_settings, ctx.attr.settings),
            extensions = deps.extensions,
            platform_libraries = unique_platform_libraries(deps.platform_libraries),
            platform_contributions = struct(infoplists = depset(
                ctx.files.infoplists,
                transitive = [extension.platform_contributions.infoplists for extension in deps.extensions],
            )),
            autoloads = used.own_autoloads,
            settings = configuration_contributions(ctx.attr.settings, owner),
            addons = addons,
        ),
    ]

_godot_addon = rule(
    doc = "An add-on; the rule behind godot_addon.",
    implementation = _addon_impl,
    attrs = {
        "directory": attr.string(
            doc = "Resource path of the directory every file of the add-on lives below.",
            mandatory = True,
        ),
        "srcs": attr.label_list(
            doc = """
            The runtime part: scripts, scenes and assets that every operation containing
            the add-on holds as members, from any package or repository: each file's path
            relative to the package of the target that lists it is placed below directory
            after strip_prefix.
            """,
            allow_files = True,
            # Files are the same in every context, so generated ones build once.
            cfg = reset_transition,
        ),
        "editor_srcs": attr.label_list(
            doc = """
            The editor part: its plugin.cfg and the files its editor plugin loads,
            placed like srcs. Editor views load it, and processes that convert files of
            its importer_suffixes stage it; no pack, source run or application
            contains it.
            """,
            allow_files = True,
            cfg = reset_transition,
        ),
        "resource_paths": attr.label_keyed_string_dict(
            doc = """
            Files of the runtime part at explicit resource paths, keyed by single-file
            target, such as `{"@vendor//:settings.cfg": "addons/vendor/settings.cfg"}`.
            Use it for a file whose path relative to its package is not its place in the
            add-on, such as a renamed or generated file. Each path lies below directory.
            """,
            allow_files = True,
            cfg = reset_transition,
        ),
        "editor_resource_paths": attr.label_keyed_string_dict(
            doc = """
            Files of the editor part at explicit resource paths below directory, keyed by
            single-file target, as resource_paths places runtime files.
            """,
            allow_files = True,
            cfg = reset_transition,
        ),
        "strip_prefix": attr.string(
            doc = """
            Directory, relative to the package of each target in srcs and editor_srcs, whose
            contents are placed below directory; empty uses the package root. A file
            outside it fails.
            """,
        ),
        "deps": attr.label_list(
            doc = """
            The add-ons it needs and its extensions: godot_addon, godot_extension and
            godot_cc_extension targets. Every extension here is the add-on's, wherever
            its descriptor lies: the add-on's parts and importer load it. Every
            operation containing this add-on contains its extensions and the add-ons it
            needs. The runtime part may use their runtime parts,
            the editor part both their parts, and each part imports after those.
            Platform libraries go in platform_deps.
            """,
        ),
        "importer_suffixes": attr.string_list(
            doc = """
            The file suffixes, lowercase and without a dot, of the importers the add-on
            registers, such as `["md"]`; it needs an editor part with a plugin.cfg or an
            extension. A project that names the add-on in its deps stages and enables
            the importer in exactly the imports of units with an own file of such a
            suffix, in the initializations and exports of operations with such files,
            and in its editor views. Resources may use the add-on only under a project
            that names it. Each build checks the suffixes against the importers Godot
            reports for the add-on and fails on a difference.
            """,
        ),
        "import_settings": attr.string_list(
            doc = """
            Keys of settings that the add-on's importer reads at import time; they reach
            every import of a project that names the add-on, and a change reimports its
            units. The other settings never reach imports.
            """,
        ),
        "infoplists": attr.label_list(
            doc = """
            Info.plist fragments iOS applications merge into their Info.plist, such as
            usage descriptions the add-on's iOS library needs; those of its extensions
            join them. Two add-ons with
            different values for a key fail; the application's own ios_infoplists win.
            """,
            allow_files = [".plist"],
            cfg = reset_transition,
        ),
        "autoloads": attr.string_dict(
            doc = """
            Autoload name to the res:// path of a file of the runtime part or of the
            runtime part of an add-on it needs, optionally prefixed with '*' for a
            singleton. Every operation containing the add-on has the autoload, after
            those of the add-ons it needs and before the project's own; a conflicting
            value requires the project's autoload_overrides.
            """,
        ),
        "settings": attr.string_dict(
            doc = """
            section/property -> Godot literal string of the operations containing the
            add-on, never of imports; a conflicting value requires the project's
            setting_overrides.
            """,
        ),
        # The context of the operation that reached the add-on; its parts import under it.
        "_project": attr.label(
            default = Label("//godot/private:project"),
            providers = [GodotProjectInfo],
        ),
        "_actions": attr.label(
            default = Label("//tools:godot_actions"),
            executable = True,
            cfg = "exec",
        ),
    } | VALIDATION_ATTRS | TRANSITION_ATTRS,
    toolchains = [config_common.toolchain_type(EDITOR_TOOLCHAIN, mandatory = False)],
)

def _editor_part_impl(ctx):
    addon = ctx.attr.addon[GodotAddonInfo]
    part = addon.editor_files

    # The editor part uses the add-on's runtime part and the add-ons it needs, which the
    # operation contains through the add-on.
    return [GodotResourcesInfo(
        imports = part.imports,
        units = part.units,
        unit_heads = part.unit_heads,
        resource_path_manifests = part.resource_path_manifests,
        member_resource_paths = part.member_resource_paths,
        import_resource_paths = part.import_resource_paths,
        member_owners = part.member_owners,
        import_owners = part.import_owners,
        ignored_resource_paths = part.ignored_resource_paths,
        relationships = part.relationships,
        addons = depset([addon], transitive = [addon.addons]),
        class_fragments = part.class_fragments,
        interfaces = part.interfaces,
        interfaced_resource_paths = part.interfaced_resource_paths,
        validations = part.validations,
    )]

# The editor part of an add-on as resources of test-only operations, such as suites that
# test its editor tooling (FR-015). It is always test-only, so Bazel keeps it out
# of every product.
_editor_part = rule(
    implementation = _editor_part_impl,
    attrs = {"addon": attr.label(providers = [GodotAddonInfo])},
)

def _addon_macro_impl(name, visibility, directory, deps, platform_deps, testonly, **kwargs):
    _addon_platform_libraries(
        name = name + ".platform_libraries",
        deps = platform_deps,
        visibility = ["//visibility:private"],
        testonly = testonly,
        tags = ["manual"],
    )
    _godot_addon(
        name = name,
        visibility = visibility,
        testonly = testonly,
        directory = directory or "addons/" + name,
        # Named deps, so the aspects of rules_android and rules_apple reach the libraries.
        deps = (deps or []) + [":" + name + ".platform_libraries"],
        **kwargs
    )
    _editor_part(
        name = name + ".editor",
        addon = ":" + name,
        visibility = visibility,
        testonly = True,
        # It builds nothing of its own; the resources that use it do.
        tags = ["manual"],
    )

godot_addon = macro(
    doc = """
    Declare an add-on once: its runtime part, its editor part with its roles, its
    extensions, platform libraries, Info.plist fragments, autoloads, settings and the
    add-ons it needs.

    Resources whose files use the add-on list it in their deps; a project lists in its
    deps the add-ons no content uses, such as an editor-only add-on, and every add-on
    with importer_suffixes its content needs. Every operation containing those resources,
    or of that project, contains the add-on: its runtime
    part as members, its autoloads and settings merged into the configuration, its
    extensions and platform libraries delivered by the applications shipping its packs.
    The editor part is a tool: editor views load it, imports of files of its
    importer_suffixes run it under a project that names the add-on, and no pack, source
    run or application contains it. No export runs its EditorExportPlugin: what one adds
    to Godot's own export is declared, as platform_deps, infoplists and pack settings.
    Test-only resources that load its scripts, such as suites of its editor tooling, list
    `<name>.editor` in their deps; that target is always test-only. A use
    never makes the add-on's files inputs of the resources' import. Under the context of
    an operation the add-on imports its parts itself, once per project and target
    platform, whether content uses it or the project names it, and validates each part's
    scripts and scenes as godot_resources validates its own.

    Every file lives below directory, by default addons/<name>; srcs and editor_srcs
    from any package or repository are placed there by their path relative to the
    package of the listed target, after strip_prefix, and resource_paths and
    editor_resource_paths at explicit paths. Two add-ons of one operation with overlapping
    directories fail, as does a file in both parts.

    Example:
    ```starlark
    godot_addon(
        name = "inventory",
        srcs = glob(["runtime/**"]),
        editor_srcs = glob(["editor/**"]),
        autoloads = {"Inventory": "*res://addons/inventory/runtime/inventory.gd"},
        platform_deps = select({
            "@platforms//os:android": [":inventory_android"],
            "//conditions:default": [],
        }),
    )

    godot_resources(name = "shop", srcs = ["shop.gd"], deps = [":inventory"])
    ```

    See [add-ons](../../resources.md#add-ons) and [importers](../../resources.md#importers).

    ### Default outputs
    - files (many): build the files of both parts; no run behavior

    ### Generated targets
    - `{name}.editor` (metadata): the editor part as resources of test-only operations, such as suites of its editor tooling, which products cannot reach
      - visibility: caller
      - testonly: true
    """,
    implementation = _addon_macro_impl,
    inherit_attrs = _godot_addon,
    # buildifier: disable=attr-applicable_licenses
    attrs = {
        "directory": attr.string(
            doc = """
            Resource path of the directory every file of the add-on lives below; empty
            uses addons/<name>.
            """,
            configurable = False,
        ),
        "platform_deps": attr.label_list(
            doc = """
            Android or Apple platform libraries the add-on's scripts use, such as an
            Android plugin they fetch through Engine.get_singleton(): an
            android_library, aar_import, Maven artifact, swift_library, objc_library or
            XCFramework import; godot_app links and packages them for every application
            shipping a pack that contains the add-on. A library's Android manifest
            entries reach the application; an android_library needs
            exports_manifest = 1 for that. Use select() with empty branches for other
            operating systems.
            """,
            providers = [[JavaInfo], [CcInfo]],
            default = [],
        ),
        "package_metadata": None,
        "expect_failure": None,
        "transitive_configs": None,
        "compatible_with": None,
        "restricted_to": None,
        "aspect_hints": None,
        "toolchains": None,
        "exec_group_compatible_with": None,
    },
)
