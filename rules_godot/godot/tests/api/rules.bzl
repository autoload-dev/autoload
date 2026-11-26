"""Extract every public entrypoint completely, and its primary symbols for the registry."""

load("@rules_python//python:defs.bzl", "py_test")

# The checks of the documentation, which the repository's root module holds.
DOCS = "@autoload_dev//tools/docs:"
DOCS_DEPS = [
    DOCS + "coverage_lib",
    DOCS + "inventory_lib",
    DOCS + "ruleset_lib",
    DOCS + "surface_lib",
]

def reference_name(module):
    """
    Derive the target name prefix of a module's extractions.

    Args:
        module: Absolute source module label.

    Returns:
        The module label flattened into a target name.
    """
    flat = module.removeprefix("//").replace("/", "_").replace(":", "_")
    return flat.removesuffix(".bzl")

def api_reference(name, apis):
    """
    Declare the extractions of the public entrypoints and the checks of their documentation.

    Declares, per module, `<reference_name>_inventory`, the complete extraction, and
    `<reference_name>_primary`, the extraction of its primary symbols; a coverage test of
    the complete ones; and `name`, the primary ones the registry's documentation archive
    carries.

    Args:
        name: Name of the filegroup of the registry's documentation metadata.
        apis: PUBLIC_APIS from modules.bzl, mapping module labels to their primary symbols.
    """
    for module, symbols in apis.items():
        page = reference_name(module)

        # Complete extraction without a symbol selection; the coverage test checks it.
        native.starlark_doc_extract(
            name = page + "_inventory",
            src = module,
            deps = [":sources"],
            render_main_repo_name = True,
            # The API contract tests read the documented contracts from it.
            visibility = ["//godot/tests/api_contracts:__pkg__"],
        )
        native.starlark_doc_extract(
            name = page + "_primary",
            src = module,
            deps = [":sources"],
            symbol_names = symbols,
            render_main_repo_name = True,
        )

    pages = [reference_name(module) for module in apis]
    inventories = [":" + page + "_inventory.textproto" for page in pages]
    sources = list(apis)
    py_test(
        name = "coverage_test",
        size = "small",
        srcs = [DOCS + "coverage_test.py"],
        main = DOCS + "coverage_test.py",
        args = ["$(rootpath :modules.bzl)"] + [
            arg
            for inventory, source in zip(inventories, sources)
            for arg in ["$(rootpath " + inventory + ")", "$(rootpath " + source + ")"]
        ],
        data = [":modules.bzl"] + inventories + sources,
        deps = DOCS_DEPS,
    )

    # Only canonical public metadata belongs in the registry's documentation archive.
    # Never archive all starlark_doc_extract targets: that includes inventories,
    # intentionally incomplete fixtures.
    native.filegroup(
        name = name,
        srcs = [":" + page + "_primary.binaryproto" for page in pages],
    )
