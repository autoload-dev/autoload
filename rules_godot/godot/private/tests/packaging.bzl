"""Packaging test fixtures; deliberately do not claim to be Godot runtime tests."""

load("//godot:providers.bzl", "GodotPackInfo")
load("//godot/private:providers.bzl", "GodotAddonInfo", "GodotExtensionInfo")
load("//godot/private/engine:profiles.bzl", "engine_profile")

visibility([
    "//godot/platforms/private/tests/...",
    "//godot/private/engine/tests",
    "//godot/private/tests/...",
])

def _fixture_pack_impl(ctx):
    pack = ctx.actions.declare_file(ctx.label.name + ".pck")
    ctx.actions.write(pack, "package fixture\n")
    return [
        DefaultInfo(files = depset([pack])),
        OutputGroupInfo(),
        GodotPackInfo(
            pack_file = pack,
            pack_files = depset([pack]),
            project = struct(
                member_resource_paths = {},
                runtime_extensions = [target[GodotExtensionInfo] for target in ctx.attr.extensions],
                export_extensions = [target[GodotExtensionInfo] for target in ctx.attr.extensions],
                platform_libraries = [],
                infoplists = depset(),
            ),
            export_options = {},
            facts = None,
            operating_system = ctx.attr.operating_system,
            cpus = ctx.attr.cpus,
            environment = "",
            version = ctx.attr.version,
            variant = ctx.attr.variant,
            icons = [],
            splash = [],
        ),
    ]

fixture_pack = rule(
    doc = "A pack without Godot facts, for packaging rules that need none.",
    implementation = _fixture_pack_impl,
    attrs = {
        "operating_system": attr.string(default = "linux"),
        "cpus": attr.string_list(default = ["x86_64"]),
        "extensions": attr.label_list(providers = [GodotExtensionInfo]),
        "variant": attr.string(default = "release"),
        "version": attr.string(
            doc = "Canonical version of the editor that exported the pack.",
            default = "4.7.2",
        ),
    },
)

def _pack_facts_impl(ctx):
    facts = ctx.actions.declare_file(ctx.label.name + ".json")
    ctx.actions.symlink(output = facts, target_file = ctx.attr.pack[GodotPackInfo].facts)
    return [DefaultInfo(files = depset([facts]))]

pack_facts = rule(
    doc = "The JSON of what Godot decided for the export of a pack for one operating system.",
    implementation = _pack_facts_impl,
    attrs = {
        "pack": attr.label(mandatory = True, providers = [GodotPackInfo]),
    },
)

def _profile_json_impl(ctx):
    output = ctx.actions.declare_file(ctx.label.name + ".json")
    ctx.actions.write(output, json.encode(engine_profile(ctx.attr.version)))
    return [DefaultInfo(files = depset([output]))]

profile_json = rule(
    doc = "The engine profile of a Godot version as JSON, as rules pass it to the build tools.",
    implementation = _profile_json_impl,
    attrs = {
        "version": attr.string(default = "4.7.2"),
    },
)

def _generate_dsym_transition_impl(_settings, _attr):
    return {"//command_line_option:apple_generate_dsym": True}

_generate_dsym_transition = transition(
    implementation = _generate_dsym_transition_impl,
    inputs = [],
    outputs = ["//command_line_option:apple_generate_dsym"],
)

def _generate_dsym_extension_impl(ctx):
    extension = ctx.attr.extension[0]
    return [
        DefaultInfo(files = extension[DefaultInfo].files),
        extension[GodotExtensionInfo],
        extension[GodotAddonInfo],
    ]

generate_dsym_extension = rule(
    doc = """
    An extension built with --apple_generate_dsym, for applications built without it.

    Only the extension's libraries build in the other configuration, so the
    application's pack is not exported again.
    """,
    implementation = _generate_dsym_extension_impl,
    attrs = {
        "extension": attr.label(
            mandatory = True,
            cfg = _generate_dsym_transition,
            providers = [GodotExtensionInfo],
        ),
    },
)

def _export_platform_transition_impl(_settings, attr):
    return {"//command_line_option:platforms": [str(attr.export_platform)]}

_export_platform_transition = transition(
    implementation = _export_platform_transition_impl,
    inputs = ["//command_line_option:platforms"],
    outputs = ["//command_line_option:platforms"],
)

def _in_export_platform_impl(ctx):
    target = ctx.attr.deps[0]
    return [target[DefaultInfo], target[GodotPackInfo], target[OutputGroupInfo]]

in_export_platform = rule(
    doc = "Select an export platform for build tool regressions that inspect several exporters in one build.",
    implementation = _in_export_platform_impl,
    attrs = {
        "deps": attr.label_list(mandatory = True, providers = [GodotPackInfo], cfg = _export_platform_transition),
        "export_platform": attr.label(mandatory = True),
    },
)
