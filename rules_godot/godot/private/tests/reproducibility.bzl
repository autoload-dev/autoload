"""
A test that imports and exports a pack's project twice and compares the results' bytes.

The action runs the import of each named unit and the pack's export twice, each run from a
fresh staged project and editor home, with the manifests a build of the pack writes. The
test passes when both runs give byte-identical import archives and packs, so an unchanged
input gives an unchanged output and the actions downstream of it stay cached.
"""

load("//godot/private:paths.bzl", "mapped_path")
load(":action_inputs.bzl", "GodotActionsInfo", "godot_actions")
load(":pack_forms.bzl", "godot_export_transition")

visibility("private")

_TOOLCHAIN = "//godot:editor_toolchain_type"

# The archive an import writes into its unit's result directory.
_IMPORT_ARCHIVE = "import.tar"

def _produced(entries, basename, mnemonic, directory = None):
    files = [
        output
        for entry in entries
        if entry.action.mnemonic == mnemonic
        for output in entry.action.outputs.to_list()
        if output.basename == basename and directory in [None, output.dirname]
    ]
    if len(files) != 1:
        fail("Expected one %s output named %s, found %s" % (mnemonic, basename, files))
    return files[0]

def _write_content(entries, file):
    return [
        entry.action.content
        for entry in entries
        if entry.action.mnemonic == "FileWrite" and entry.action.outputs.to_list()[0] == file
    ][0]

def _pack_action(entries):
    packs = [entry.action for entry in entries if entry.action.mnemonic == "GodotPack"]
    if len(packs) != 1:
        fail("Expected one GodotPack action, found %d" % len(packs))
    return packs[0]

def _import_manifests(entries, units):
    """
    Return the manifests of the units' imports and the import configuration they name.

    Each unit imports in the pack's project context only, under the project's import
    configuration of that context; outside it the units write their staging alone.
    """
    manifests = {unit: _produced(entries, unit + ".import.json", "FileWrite") for unit in units}
    resource_paths = {
        unit: _produced(entries, unit + ".resource_paths.json", "FileWrite", directory = manifest.dirname)
        for unit, manifest in manifests.items()
    }
    configurations = {
        json.decode(_write_content(entries, manifest))["project_file"]: True
        for manifest in manifests.values()
    }
    if len(configurations) != 1:
        fail("Expected the units to share one import configuration, found %s" % sorted(configurations))
    import_configuration = [
        output
        for entry in entries
        if entry.action.mnemonic == "GodotImportConfig"
        for output in entry.action.outputs.to_list()
        if mapped_path(output) in configurations
    ]
    return struct(manifests = manifests, resource_paths = resource_paths, import_configuration = import_configuration)

def _declare_run(ctx, run, shared):
    """Declare one run's import archives and pack; return its commands, outputs and compared files."""
    prefix = "%s/%s" % (ctx.label.name, run)
    archives = {}
    commands = []
    for unit in ctx.attr.units:
        archive = ctx.actions.declare_file("%s/%s/%s" % (prefix, unit, _IMPORT_ARCHIVE))
        archives[unit] = archive
        commands.append(" ".join([
            ctx.executable._import_tool.path,
            "import",
            "--manifest",
            shared.imports.manifests[unit].path,
            "--output",
            archive.path,
            "--resource-path-manifest",
            shared.imports.resource_paths[unit].path,
            shared.roots,
        ]))
    exported = ctx.actions.declare_file(prefix + "/pack.pck")
    report = ctx.actions.declare_file(prefix + "/pack.json")
    commands.append(" ".join([
        ctx.executable._export_tool.path,
        "pack",
        "--manifest",
        shared.pack_manifest,
        "--output",
        exported.path,
        "--report",
        report.path,
        shared.roots,
    ] + ["--import " + archives[unit].dirname for unit in ctx.attr.units]))
    return struct(
        commands = commands,
        outputs = archives.values() + [exported, report],
        compared = [archives[unit] for unit in ctx.attr.units] + [exported],
    )

def _comparison_script(ctx, first_run, second_run):
    """Return a test script that compares the two runs' files byte for byte."""
    script = ["#!/usr/bin/env bash", "set -eu", "status=0"]
    for first, second in zip(first_run, second_run):
        script.append(
            "if cmp -s '{a}' '{b}'; then echo 'identical: {name}'; else echo 'differs: {name}'; status=1; fi".format(
                a = first.short_path,
                b = second.short_path,
                name = first.short_path.removeprefix(ctx.label.package + "/" + ctx.label.name + "/first/"),
            ),
        )
    script.append("exit $status")
    return "\n".join(script) + "\n"

def _import_and_pack_reproducibility_test_impl(ctx):
    entries = ctx.attr.pack[0][GodotActionsInfo].every.to_list()
    pack = _pack_action(entries)
    tc = ctx.toolchains[_TOOLCHAIN].godot
    imports = _import_manifests(entries, ctx.attr.units)
    inputs = depset(
        imports.manifests.values() + imports.resource_paths.values() + imports.import_configuration,
        transitive = [pack.inputs, tc.files],
    )

    # The editor and the output roots that resolve the manifests' mapped paths, as the
    # actions pass them.
    roots = " ".join(["--editor", tc.editor.executable.path] + sorted({
        "--root " + file.root.path: None
        for file in inputs.to_list()
        if not file.is_source
    }))
    shared = struct(imports = imports, pack_manifest = pack.argv[pack.argv.index("--manifest") + 1], roots = roots)
    runs = [_declare_run(ctx, run, shared) for run in ["first", "second"]]
    ctx.actions.run_shell(
        command = "\n".join(["set -eu"] + runs[0].commands + runs[1].commands),
        inputs = inputs,
        tools = [ctx.attr._import_tool[DefaultInfo].files_to_run, ctx.attr._export_tool[DefaultInfo].files_to_run, tc.editor],
        outputs = runs[0].outputs + runs[1].outputs,
        mnemonic = "GodotReproducibility",
        progress_message = "Validating %{label}",
        toolchain = _TOOLCHAIN,
    )
    executable = ctx.actions.declare_file(ctx.label.name + ".sh")
    ctx.actions.write(executable, _comparison_script(ctx, runs[0].compared, runs[1].compared), is_executable = True)
    return [DefaultInfo(
        executable = executable,
        runfiles = ctx.runfiles(files = runs[0].compared + runs[1].compared),
    )]

import_and_pack_reproducibility_test = rule(
    implementation = _import_and_pack_reproducibility_test_impl,
    test = True,
    doc = "Import the named units of a pack's project and export the pack twice; pass when both runs give the same bytes.",
    attrs = {
        "pack": attr.label(
            mandatory = True,
            aspects = [godot_actions],
            # The test exports with Godot, as an optimized build does; the writer's
            # determinism test is in tools/pack/tests/writer_test.py.
            cfg = godot_export_transition,
            doc = "The godot_pack whose import manifests and export manifest the runs use.",
        ),
        "units": attr.string_list(
            mandatory = True,
            doc = "The names of the godot_resources targets whose units have files with an importer.",
        ),
        "_export_tool": attr.label(
            default = "//tools/editor_action:godot_export",
            executable = True,
            cfg = "exec",
        ),
        "_import_tool": attr.label(
            default = "//tools/editor_action:project_actions",
            executable = True,
            cfg = "exec",
        ),
    },
    toolchains = [_TOOLCHAIN],
)
