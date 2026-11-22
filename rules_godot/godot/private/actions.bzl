"""Manifests and editor actions shared by the rules that run Godot as a build tool."""

load("//godot/private:execution.bzl", "EDITOR_TOOLCHAIN")

visibility("//godot")

# Execution requirements of actions whose manifests name files by mapped_path, so that
# --experimental_output_paths=strip gives one unit's action one cache key in every target
# configuration.
PATH_MAPPING = {"supports-path-mapping": "1"}

def _output_root(file):
    return None if file.is_source else file.root.path

def add_output_roots(arguments, files):
    """
    Add the output roots of an action's inputs, which resolve its manifests' mapped paths.

    Path mapping rewrites them as it rewrites the inputs' paths.

    Args:
        arguments: The action's Args.
        files: depset of the Files the action stages.
    """
    arguments.add_all(
        files,
        map_each = _output_root,
        uniquify = True,
        expand_directories = False,
        before_each = "--root",
    )

def write_manifest(ctx, suffix, data):
    """Write data as the JSON File named after the target and suffix."""
    out = ctx.actions.declare_file(ctx.label.name + suffix + ".json")
    ctx.actions.write(out, json.encode(data))
    return out

def editor_manifest(ctx, name, data):
    """
    The manifest of every tools/godot_actions.py and tools/godot_export.py mode.

    The editor itself is an argument, --editor, which path mapping rewrites.
    """
    tc = ctx.toolchains[EDITOR_TOOLCHAIN].godot
    return write_manifest(ctx, name, dict(data, version = tc.version))

def run_editor_action(
        ctx,
        mode,
        name,
        output,
        data,
        inputs,
        imports,
        mnemonic,
        progress_message,
        report = None,
        outputs = [],
        path_mapping = False):
    """
    Run the editor through tools/godot_actions.py or tools/godot_export.py.

    Args:
        ctx: Analysis context of a rule with an _actions tool and the editor toolchain.
        mode: The tool's mode, such as initialize or pack.
        name: Suffix of the action's manifest.
        output: The File the action writes.
        data: The manifest's content besides the editor's version.
        inputs: depset of the Files the action stages.
        imports: depset of the import results it stages.
        mnemonic: The action's mnemonic.
        progress_message: The action's progress message.
        report: A further File the action writes as its report, or None.
        outputs: Further Files the action writes.
        path_mapping: Whether the action supports path mapping: data names files by
            mapped_path, and inputs holds every output File it names.
    """
    tc = ctx.toolchains[EDITOR_TOOLCHAIN].godot
    manifest = editor_manifest(ctx, name, data)
    arguments = ctx.actions.args()
    arguments.add_all([mode, "--manifest", manifest, "--output", output], expand_directories = False)
    arguments.add("--editor", tc.editor.executable)
    if report:
        arguments.add("--report", report)

    # Import results stay unexpanded and the depset unflattened until execution.
    arguments.add_all(imports, before_each = "--import", expand_directories = False)
    if path_mapping:
        add_output_roots(arguments, inputs)
    ctx.actions.run(
        executable = ctx.executable._actions,
        arguments = [arguments],
        inputs = depset([manifest], transitive = [tc.files, inputs, imports]),
        tools = [tc.editor],
        outputs = [output] + ([report] if report else []) + outputs,
        mnemonic = mnemonic,
        progress_message = progress_message,
        toolchain = EDITOR_TOOLCHAIN,
        execution_requirements = PATH_MAPPING if path_mapping else {},
    )
