"""Dart scripts for a Godot project, compiled ahead of time into the project's extension."""

load("@autoload_rules_godot//godot/extension:defs.bzl", "godot_cc_extension")
load("@bazel_skylib//rules:copy_file.bzl", "copy_file")
load("@rules_dart//dart:defs.bzl", "dart_binary")

def _script_registry_impl(ctx):
    root = ctx.label.package + "/" if ctx.label.package else ""
    imports = []
    entries = []
    for index, script in enumerate(ctx.files.srcs):
        if not script.short_path.startswith(root):
            fail("%s is not below %s, the package of project.godot" % (script.short_path, ctx.label.package))
        path = script.short_path[len(root):]
        imports.append("import '%s' as script%d;" % (path, index))
        entries.append("    'res://%s': script%d.script," % (path, index))
    ctx.actions.write(ctx.outputs.out, "\n".join([
        "// The project's Dart scripts by resource path, written by godot_dart_extension.",
        "import 'package:godot/src/embedder.dart';",
        "",
    ] + imports + [
        "",
        "@pragma('vm:entry-point')",
        "void main() => registerScripts({",
    ] + entries + [
        "});",
        "",
    ]))

_script_registry = rule(
    implementation = _script_registry_impl,
    attrs = {
        "out": attr.output(mandatory = True),
        "srcs": attr.label_list(allow_files = [".dart"], mandatory = True),
    },
)

def _dart_extension_impl(name, visibility, srcs, deps, **kwargs):
    _script_registry(
        name = name + "_registry",
        srcs = srcs,
        out = name + "_scripts.dart",
    )
    dart_binary(
        name = name + "_scripts",
        compile_mode = "aot-snapshot",
        main = name + "_scripts.dart",
        srcs = srcs,
        deps = [Label("//dart/godot")] + deps,
    )

    # The library loads the snapshot by its file name from beside itself; the directory
    # keeps the file in the macro's namespace.
    copy_file(
        name = name + "_snapshot",
        src = name + "_scripts",
        out = name + "_snapshot/libdart_scripts.so",
    )
    godot_cc_extension(
        name = name,
        srcs = [],
        entry_symbol = "dart_language_init",
        data = [name + "_snapshot"],
        visibility = visibility,
        deps = [Label("//dart")],
        **kwargs
    )

godot_dart_extension = macro(
    doc = """
    The Dart script language of a project, with the project's scripts compiled in.

    Declare it in the package of the project's project.godot and list it in the deps of
    the godot_resources whose scenes use the scripts, so that validating them loads the
    language. Each script's resource path is its path below this package, so declare the
    scripts' godot_resources with the prefix of their directory. Each script file declares
    a top-level `script`, a package:godot `Script`.

    The extension's library loads the scripts' AOT snapshot, libdart_scripts.so, from
    beside itself. One project has one Dart extension. The other attributes are those of
    godot_cc_extension.
    """,
    implementation = _dart_extension_impl,
    inherit_attrs = godot_cc_extension,
    attrs = {
        "srcs": attr.label_list(
            doc = "The project's Dart script files.",
            allow_files = [".dart"],
            mandatory = True,
        ),
        "deps": attr.label_list(doc = "dart_library targets the scripts import, besides package:godot."),
        "entry_symbol": None,
        "data": None,
    },
)
