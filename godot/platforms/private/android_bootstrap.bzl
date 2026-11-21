"""The bootstrap of Godot Android applications: the shell files, manifests and resources."""

load("@rules_android//rules:android_split_transition.bzl", "android_split_transition")
load("//godot:providers.bzl", "GodotPackInfo")
load("//godot/platforms/private:maven.bzl", "MavenCoordinatesInfo", "maven_coordinates_aspect")
load("//godot/platforms/private:shell.bzl", "SHELL_ATTRS", "release_values", "shell_file")
load("//godot/private:release.bzl", "RELEASE_ATTRS")
load("//godot/private:versions.bzl", "godot_series", "godot_version_name")
load("//godot/private/config:transitions.bzl", "content_transition")
load("//godot/private/engine:profiles.bzl", "engine_profile")

visibility("private")

# Manifest value keys that rules_android's manifest processor turns into merger overrides
# instead of placeholders: the camel-case names of the ManifestSystemProperty constants of
# the manifest merger bundled with rules_android 0.8.0 (manifest-merger 30.1.3), with
# `applicationId` for its PACKAGE, and `packageName`, which the merger derives from it.
# Each maps to what owns the value in godot_app.
_RESERVED_MANIFEST_VALUES = {
    "applicationId": "the application_id attribute",
    "packageName": "the application_id attribute",
    "minSdkVersion": "the android_min_sdk_version attribute",
    "targetSdkVersion": "the android_target_sdk_version attribute",
    "versionCode": "the pack's version/code export option or --@autoload_rules_godot//godot:build_number",
    "versionName": "the pack's version/name export option or --@autoload_rules_godot//godot:app_version",
    "maxSdkVersion": "the manifest merger, as an override godot_app does not expose",
}

# The manifest attributes rules_godot writes into the main manifest, with their owners;
# an application's own manifest must not set them.
_OWNED_MANIFEST_ATTRIBUTES = {
    key: _RESERVED_MANIFEST_VALUES[key]
    for key in ["versionCode", "versionName", "minSdkVersion", "targetSdkVersion"]
}

def _check_manifest_values(ctx):
    """Reject manifest values whose keys the merger treats as overrides, naming the owner."""
    for key in sorted(ctx.attr.manifest_values):
        if key in _RESERVED_MANIFEST_VALUES:
            fail("%s: android_manifest_values must not set %r; it belongs to %s" %
                 (ctx.label, key, _RESERVED_MANIFEST_VALUES[key]))

def _resources_of_type(files, resource_type):
    """The resource files in resource directories of a type, such as mipmap-hdpi."""
    return [
        file
        for file in files
        if file.dirname.rpartition("/")[2].partition("-")[0] == resource_type
    ]

def _yield_resources(ctx, trees, candidates, name):
    """
    Return shell resource trees without the resources the application's files define.

    Args:
        ctx: godot_android_bootstrap rule context.
        trees: Shell asset directories with resource directories at their root.
        candidates: The application's resource files of the trees' resource type.
        name: Name of the yielded directories beside the rule's outputs.

    Returns:
        The trees, filtered by an action only when the application has resources of
        their type.
    """
    if not candidates:
        return trees
    yielded = []
    for index, tree in enumerate(trees):
        output = ctx.actions.declare_directory("%s/%s_%d" % (ctx.label.name, name, index))
        args = ctx.actions.args()
        args.add("android-resources")
        args.add("--input", tree.path)
        args.add("--output", output.path)
        args.add_all(candidates, before_each = "--override")
        ctx.actions.run(
            executable = ctx.executable._shell_overrides,
            arguments = [args],
            inputs = [tree] + candidates,
            outputs = [output],
            mnemonic = "GodotShellYield",
            progress_message = "Generating %{label}",
        )
        yielded.append(output)
    return yielded

def _android_bootstrap_impl(ctx):
    _check_manifest_values(ctx)
    # A transitioned attribute holds a list, here of the one pack.
    pack = ctx.attr.pack[0][GodotPackInfo]
    engine = engine_profile(pack.version)
    profile = engine["android"]

    # Godot's template activity of the pack's minor runs unchanged; it reads the
    # export's command line from assets/_cl_ as in Godot's own export.
    sources = {file.owner.name: file for file in ctx.files._android_sources}
    activity = profile["template_activity"]
    java = [_check_maven_minimums(ctx, pack, engine["android_shell"], sources[activity["path"]])]
    if activity["build_config"]:
        java.append(sources["android/BuildConfig.java"])

    # rules_android makes every build but -c opt debuggable; those get the plugin that
    # passes bazel run's Godot arguments, and release builds leave it out.
    launch_arguments = ctx.var["COMPILATION_MODE"] != "opt"
    if launch_arguments:
        java.append(ctx.file._launch_arguments_plugin)

    # With the application's own manifest, that manifest is the main manifest and the
    # shell manifest merges below it as a library manifest.
    main = ctx.actions.declare_file(ctx.label.name + "/AndroidManifest.xml")
    shell_manifest = ctx.actions.declare_file(ctx.label.name + "/shell/AndroidManifest.xml") if ctx.file.manifest_override else main
    asset = ctx.actions.declare_file(ctx.label.name + "/assets/main.pck")
    ctx.actions.symlink(output = asset, target_file = pack.pack_file)
    command_line = ctx.actions.declare_file(ctx.label.name + "/assets/_cl_")
    shell_file(ctx, "android-command-line", command_line, pack, {"profile": profile})
    manifest_values = {
        "profile": profile,
        "fallback_name": ctx.attr.app_name,
        "editor_version": godot_version_name(pack.version),
        "launch_arguments": launch_arguments,
    } | release_values(ctx, pack)
    shell_file(ctx, "android-manifest", shell_manifest, pack, manifest_values)
    if ctx.file.manifest_override:
        shell_file(
            ctx,
            "android-main-manifest",
            main,
            pack,
            manifest_values | {"owned_attributes": _OWNED_MANIFEST_ATTRIBUTES},
            overrides = [ctx.file.manifest_override],
        )

    # The application's resources replace the shell's resources of the same type, name
    # and qualifiers; its unqualified styles replace the shell's styles.
    overrides = ctx.files.resource_overrides
    themes = ctx.actions.declare_file(ctx.label.name + "/res/values/themes.xml")
    shell_file(ctx, "android-themes", themes, pack, {}, overrides = [
        file
        for file in overrides
        if file.dirname.rpartition("/")[2] == "values"
    ])
    icons = _yield_resources(ctx, pack.icons, _resources_of_type(overrides, "mipmap"), "icons")
    splash = _yield_resources(ctx, pack.splash, _resources_of_type(overrides, "drawable"), "splash")
    return [
        DefaultInfo(files = depset([asset, command_line])),
        OutputGroupInfo(
            java = depset(java),
            manifest = depset([main]),
            shell_manifest = depset([shell_manifest]),
            resources = depset(icons + splash + [themes]),
        ),
    ]

def _check_maven_minimums(ctx, pack, shell, activity):
    """
    Gate the template activity on the Maven minimums of Godot's Maven graph.

    The check reads the coordinates of the application's Java closure in every platform
    slice and writes the activity source unchanged when no module lies below its minimum,
    so javac never compiles the activity against an older module, and a passing check
    leaves the compile cached.
    """
    graphs = {file.owner.name: file for file in ctx.files._maven_graphs}
    graph = graphs[shell["maven_graph"]]
    coordinates = ctx.actions.declare_file(ctx.label.name + "/maven_coordinates.txt")
    listing = ctx.actions.args()
    listing.set_param_file_format("multiline")
    listing.add_all(
        depset(transitive = [dep[MavenCoordinatesInfo].coordinates for dep in ctx.attr.maven_deps]),
    )
    ctx.actions.write(coordinates, listing)
    output = ctx.actions.declare_file("%s/checked/%s" % (ctx.label.name, activity.basename))

    # The application's own name; godot_app nests its Android backends as <name>.<backend>/<name>.
    application = "//%s:%s" % (ctx.label.package, ctx.attr.app_name)
    if ctx.label.repo_name:
        application = "@%s%s" % (ctx.label.repo_name, application)
    args = ctx.actions.args()
    args.add("--coordinates", coordinates)
    args.add("--graph", graph)
    args.add("--source", activity)
    args.add("--output", output)
    args.add("--application", application)
    args.add("--engine-minor", godot_series(pack.version))
    ctx.actions.run(
        executable = ctx.executable._check_maven_minimums,
        arguments = [args],
        inputs = [coordinates, graph, activity],
        outputs = [output],
        mnemonic = "GodotMavenMinimums",
        progress_message = "Validating %{label}",
    )
    return output

godot_android_bootstrap = rule(
    implementation = _android_bootstrap_impl,
    attrs = {
        "pack": attr.label(
            doc = """
            PCK target providing GodotPackInfo. The bootstrap reads the export's files
            and facts, which the pack's content configuration holds, so it reaches the
            pack there: android_binary's own configuration and rules_android's split then
            analyze no native code of the pack for it.
            """,
            mandatory = True,
            providers = [GodotPackInfo],
            cfg = content_transition,
        ),
        "app_name": attr.string(
            doc = "Label when neither package/name nor config/name sets one.",
            mandatory = True,
        ),
        "manifest_values": attr.string_dict(
            doc = """
            The application's placeholder values, checked here so that select() values are
            resolved; the android_binary receives them with the applicationId override.
            """,
        ),
        "maven_deps": attr.label_list(
            doc = """
            The application's Java dependencies whose Maven modules the minimum check
            reads: the runtime's Maven dependencies, the template activity's and the
            application's deps.
            """,
            aspects = [maven_coordinates_aspect],
            cfg = android_split_transition,
        ),
        "manifest_override": attr.label(
            doc = "The application's own manifest, which becomes the main manifest.",
            allow_single_file = [".xml"],
        ),
        "resource_overrides": attr.label_list(
            doc = "The application's resource files, whose resources the shell leaves out.",
            allow_files = True,
        ),
        "_android_sources": attr.label(
            default = Label("//godot/private/engine:android_sources"),
        ),
        "_launch_arguments_plugin": attr.label(
            default = Label("//godot/platforms/private:android/LaunchArgumentsPlugin.java"),
            allow_single_file = True,
        ),
        "_check_maven_minimums": attr.label(
            default = Label("//tools/platforms:check_maven_minimums"),
            cfg = "exec",
            executable = True,
        ),
        "_maven_graphs": attr.label(
            default = Label("//godot/private/engine:android_maven_graphs"),
        ),
        "_shell_overrides": attr.label(
            default = Label("//tools/platforms:shell_overrides"),
            cfg = "exec",
            executable = True,
        ),
    } | SHELL_ATTRS | RELEASE_ATTRS,
)
