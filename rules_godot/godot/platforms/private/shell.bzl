"""Shell files and engine checks that the application rules of all operating systems share."""

load("//godot/private:providers.bzl", "GodotComponentInfo")
load("//godot/private:release.bzl", "app_version", "build_number")

visibility("//godot/platforms/...")

# Rules that write shell files add these private attributes.
SHELL_ATTRS = {
    "_shell": attr.label(
        default = Label("//tools/platforms:godot_shell"),
        cfg = "exec",
        executable = True,
    ),
}

# Rules that check engine versions add these private attributes.
ENGINE_CHECK_ATTRS = {
    "_check_engine_version": attr.label(
        default = Label("//tools/platforms:check_engine_version"),
        cfg = "exec",
        executable = True,
    ),
}

def release_values(ctx, pack):
    """
    Return the values godot_shell.py takes a version or build number from.

    An export option the pack sets wins over the release build settings, and
    those over Godot's defaults.

    Args:
        ctx: Rule context with RELEASE_ATTRS.
        pack: GodotPackInfo of the exported project.

    Returns:
        A dict of the options the pack sets and the build settings.
    """
    return {
        "explicit": sorted(pack.export_options),
        "app_version": app_version(ctx),
        "build_number": build_number(ctx),
    }

def shell_file(ctx, command, output, pack, values, outputs = [], args = None, infoplists = depset(), overrides = []):
    """
    Write a shell file the way Godot's exporter for the operating system writes it.

    godot_shell.py fills the command's template from what Godot decided for the
    pack's export, its facts, and the values the rule knows, such as an engine
    profile of Godot's exporters and its own attributes.

    Args:
        ctx: Rule context with SHELL_ATTRS.
        command: The godot_shell.py command, such as ios-plist.
        output: The shell file.
        pack: GodotPackInfo of an Android, iOS or macOS pack.
        values: The command's values, written as JSON.
        outputs: Further files the command writes.
        args: Args of the command's further outputs.
        infoplists: Info.plist fragments of the project's resources, merged strictly.
        overrides: Files of the application whose slots the shell file leaves to them.
    """

    data = ctx.actions.declare_file(output.basename + ".json", sibling = output)
    ctx.actions.write(data, json.encode(values))
    common = ctx.actions.args()
    common.add(command)
    common.add("--facts", pack.facts)
    common.add("--values", data)
    common.add("--output", output)
    common.add_all(infoplists, before_each = "--plist")
    common.add_all(overrides, before_each = "--override")
    ctx.actions.run(
        executable = ctx.executable._shell,
        arguments = [common] + ([args] if args else []),
        inputs = depset([pack.facts, data] + overrides, transitive = [infoplists]),
        outputs = [output] + outputs,
        mnemonic = "GodotShellFile",
        progress_message = "Generating %%{label} (%s)" % output.basename,
    )

def pack_facts(pack):
    """
    Return the check_engine files entry of a pack's export facts.

    A text pack, which development builds ship, has no export and so no facts.

    Args:
        pack: GodotPackInfo of the shipped pack.

    Returns:
        A dict of --facts to a depset of the facts, empty without them.
    """
    return {"--facts": depset([pack.facts])} if pack.facts else {}

def _component_values(engine):
    """The check_engine_version.py options from an engine's component provenance."""
    component = engine[GodotComponentInfo] if engine and GodotComponentInfo in engine else None
    if not component:
        return {}
    values = {"--assert-version": component.version} if component.kind == "prebuilt" else {}
    if component.renderers != None:
        values["--renderers"] = ",".join(component.renderers)
    return values

def check_engine(ctx, files, engine = None, values = {}):
    """
    Check an engine's own facts: versions against assertions, platform slices, renderers.

    The version of the editor that exported the pack is not compared; editor and runtime
    are independent. With a pack's export facts among files, see pack_facts, the
    project's rendering method must be one a source-built engine with declared renderers
    runs.

    Args:
        ctx: Rule context with ENGINE_CHECK_ATTRS.
        files: dict of check_engine_version.py options, such as --library, to
            depsets of the engine files that name its version.
        engine: Optional resolved engine target; the declared version of its prebuilt
            runtime component is checked against the inspected artifact.
        values: dict of further check_engine_version.py options to strings.

    Returns:
        The check's outputs, for the _validation output group.
    """
    stamp = ctx.actions.declare_file(ctx.label.name + ".engine_version")
    args = ctx.actions.args()
    values = _component_values(engine) | values

    # Only an engine with declared renderers needs the pack's facts.
    files = {option: depset_ for option, depset_ in files.items() if option != "--facts" or "--renderers" in values}
    for option, option_files in files.items():
        args.add_all(option_files, before_each = option)
    for option, value in values.items():
        args.add(option, value)
    args.add("--output", stamp)
    ctx.actions.run(
        executable = ctx.executable._check_engine_version,
        arguments = [args],
        inputs = depset(transitive = files.values()),
        outputs = [stamp],
        mnemonic = "GodotEngineVersion",
        progress_message = "Validating %{label}",
    )
    return [stamp]

def privacy_manifest(ctx, pack, profile, operating_system, output):
    """
    Write the privacy manifest Godot's Apple exports write from the privacy/* options.

    Args:
        ctx: Rule context with SHELL_ATTRS.
        pack: GodotPackInfo of an iOS or macOS pack.
        profile: The engine profile of the pack's editor.
        operating_system: ios or macos, the profile's section of the export.
        output: The manifest to write.
    """
    shell_file(ctx, "privacy-manifest", output, pack, {
        "profile": profile["privacy"],
        "accessed_apis": profile[operating_system]["declares_accessed_apis"],
    })
