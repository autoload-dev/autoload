"""Separate complete extraction from the selected primary reference presentation."""

load("@rules_python//python:defs.bzl", "py_test")
load("@stardoc//stardoc:stardoc.bzl", "stardoc")

def reference_name(module):
    """
    Derive the target and page name shared by a module's documentation outputs.

    Args:
        module: Absolute source module label.

    Returns:
        The module label flattened into a target name.
    """
    flat = module.removeprefix("//").replace("/", "_").replace(":", "_")
    return flat.removesuffix(".bzl")

def api_reference(name, apis):
    """
    Declare extraction, coverage, rendering and the assembled site for public entrypoints.

    Also declares coverage_test and bcr_docs, plus per-module extraction and
    rendering targets named after reference_name.

    Args:
        name: Name of the assembled reference site target.
        apis: PUBLIC_APIS from modules.bzl, mapping module labels to their entries.
    """
    for module, entry in apis.items():
        page = reference_name(module)

        # Complete extraction without a symbol selection; the coverage test checks it.
        native.starlark_doc_extract(
            name = page + "_inventory",
            src = module,
            deps = [":sources"],
            render_main_repo_name = True,
        )
        stardoc(
            name = page + "_primary",
            input = module,
            out = "rendered/" + page + ".md",
            symbol_names = entry["symbols"],
            deps = [":sources"],
            stamp = 0,
        )

    pages = [reference_name(module) for module in apis]
    inventories = [":" + page + "_inventory.textproto" for page in pages]
    py_test(
        name = "coverage_test",
        size = "small",
        srcs = ["//tools/docs:coverage_test.py"],
        main = "//tools/docs:coverage_test.py",
        args = [
            arg
            for inventory, module in zip(inventories, apis)
            for arg in ["$(rootpath " + inventory + ")", "$(rootpath " + module + ")"]
        ],
        data = inventories + list(apis),
        deps = ["//tools/docs:coverage_lib"],
    )
    reference_site(
        name = name,
        manifest = "modules.bzl",
        metadata = dict(zip(inventories, apis)),
        rendered = {
            ":rendered/" + page + ".md": module
            for page, module in zip(pages, apis)
        },
    )

    # Only canonical public metadata belongs in a future BCR docs archive.
    # Never archive all starlark_doc_extract targets: that includes inventories,
    # intentionally incomplete fixtures.
    native.filegroup(
        name = "bcr_docs",
        srcs = [":" + page + "_primary.extract.binaryproto" for page in pages],
    )

def _reference_site_impl(ctx):
    output = ctx.actions.declare_directory(ctx.label.name)
    spec = ctx.actions.declare_file(ctx.label.name + ".json")
    values_by_name = {}
    inputs = [ctx.file.manifest, spec]
    for name in ["metadata", "rendered"]:
        values = {}
        for target, module in getattr(ctx.attr, name).items():
            files = target[DefaultInfo].files.to_list()
            if len(files) != 1:
                fail("Expected a single documentation input for " + module)
            inputs.extend(files)
            values[module] = files[0].path
        values_by_name[name] = values
    values_by_name["manifest"] = ctx.file.manifest.path
    values_by_name["names"] = {
        module: reference_name(module)
        for module in ctx.attr.rendered.values()
    }
    ctx.actions.write(spec, json.encode(values_by_name))
    ctx.actions.run(
        executable = ctx.executable._renderer,
        arguments = ["--spec", spec.path, "--output", output.path],
        inputs = depset(inputs),
        outputs = [output],
        mnemonic = "GodotApiReference",
        progress_message = "Generating %{label}",
    )
    return [DefaultInfo(files = depset([output]))]

reference_site = rule(
    implementation = _reference_site_impl,
    attrs = {
        "manifest": attr.label(allow_single_file = [".bzl"], mandatory = True),
        "metadata": attr.label_keyed_string_dict(allow_files = [".textproto"]),
        "rendered": attr.label_keyed_string_dict(allow_files = [".md"]),
        "_renderer": attr.label(
            default = Label("//tools/docs:render_reference"),
            executable = True,
            cfg = "exec",
        ),
    },
)
