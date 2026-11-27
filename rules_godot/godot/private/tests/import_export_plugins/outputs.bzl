"""What Godot reported about a pack's imports and export, for tests inspecting them."""

load("//godot:providers.bzl", "GodotPackInfo")
load("//godot/private:view.bzl", "GodotViewInfo")

visibility("private")

_VARIANT = str(Label("//godot:variant"))

def _variant_transition_impl(_settings, attr):
    return {_VARIANT: attr.variant}

_variant_transition = transition(
    implementation = _variant_transition_impl,
    inputs = [],
    outputs = [_VARIANT],
)

def _shell_images_impl(ctx):
    pack = ctx.attr.pack[0][GodotPackInfo]
    listing = ctx.actions.declare_file(ctx.label.name + ".json")
    files = pack.icons + pack.splash
    ctx.actions.write(listing, json.encode({
        "icons": [icon.short_path for icon in pack.icons],
        "splash": [image.short_path for image in pack.splash],
    }))
    return [DefaultInfo(
        files = depset([listing]),
        runfiles = ctx.runfiles(files = [listing] + files),
    )]

shell_images = rule(
    doc = "List the icons and splash images Godot rendered for a pack's shell, built with a template variant.",
    implementation = _shell_images_impl,
    attrs = {
        "pack": attr.label(
            doc = "The pack, exported with variant.",
            mandatory = True,
            providers = [GodotPackInfo],
            cfg = _variant_transition,
        ),
        "variant": attr.string(
            doc = "Value of //godot:variant for the pack.",
            default = "release",
            values = ["debug", "release"],
        ),
    },
)

def _import_results_impl(ctx):
    view = ctx.attr.view[GodotViewInfo]
    results = depset(transitive = [view.imports, view.importer_imports]).to_list()
    listing = ctx.actions.declare_file(ctx.label.name + ".json")
    ctx.actions.write(listing, json.encode(sorted([result.short_path for result in results])))
    return [DefaultInfo(
        files = depset([listing]),
        runfiles = ctx.runfiles(files = [listing] + results),
    )]

import_results = rule(
    doc = "List the import results an operation's view stages, those of its importers' editor parts included.",
    implementation = _import_results_impl,
    attrs = {
        "view": attr.label(
            doc = "The view of the operation, `<name>.view`.",
            mandatory = True,
            providers = [GodotViewInfo],
        ),
    },
)
