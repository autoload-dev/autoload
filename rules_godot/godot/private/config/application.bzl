"""The application context of a godot_app, on its dependency to the pack it ships."""

load("//godot:providers.bzl", "GodotPackInfo")
load("//godot/private:resources.bzl", "unique_extensions", "unique_platform_libraries")
load("//godot/private:versions.bzl", "IOS_MINIMUM_OS", "MACOS_MINIMUM_OS", "dotted_version")
load(":settings.bzl", "APPLICATION_CONTEXT", "MERGE_ANDROID_MANIFEST_PERMISSIONS", "OPERATING_SYSTEM")
load(":transitions.bzl", "project_transition")

visibility(["//godot/..."])

def _android_values(attr):
    if attr.android_min_sdk_version < 0 or attr.android_target_sdk_version < 0:
        fail("Android SDK values must be zero or positive")
    return {
        "android_min_sdk_version": attr.android_min_sdk_version,
        "android_target_sdk_version": attr.android_target_sdk_version,
    }

def _macos_values(attr):
    version = attr.macos_minimum_os_version
    if not dotted_version(version):
        fail("macos_minimum_os_version must be a dotted numeric version")
    return {"macos_minimum_os_version": version}

def _unique_subset(values, allowed):
    if not values or len({value: True for value in values}) != len(values):
        return False
    return all([value in allowed for value in values])

def _ios_values(attr):
    version = attr.ios_minimum_os_version
    if not dotted_version(version):
        fail("ios_minimum_os_version must be a dotted numeric version")
    families = attr.ios_families
    if not _unique_subset(families, ["iphone", "ipad"]):
        fail("ios_families must be a nonempty unique subset of iphone, ipad")
    return {"ios_minimum_os_version": version, "ios_families": sorted(families)}

# The values the export for each operating system uses. A host build without --platforms
# carries no operating system, so it gets the macOS values. A Linux pack of such a build
# ignores them, as it ignores application_id.
_EXPORT_VALUES = {
    "android": _android_values,
    "macos": _macos_values,
    "": _macos_values,
    "ios": _ios_values,
}

def application_context(settings, attr):
    """
    Validate the application's values and derive the application context of its pack.

    Args:
        settings: Transition input settings, including the operating system.
        attr: application_pack attributes.

    Returns:
        The transition's application context output, with the Android application's
        permission merging reset.
    """
    operating_system = settings[OPERATING_SYSTEM]

    # Only values the export for the operating system uses, so apps that share them share
    # one export; a Linux app shares the standalone pack's.
    values = {}
    if operating_system in ["android", "ios"] and not attr.application_id:
        fail("application_id is required for %s" % operating_system)
    if attr.application_id and operating_system != "linux":
        values["application_id"] = attr.application_id
    export_values = _EXPORT_VALUES.get(operating_system)
    if export_values:
        values.update(export_values(attr))
    return {
        APPLICATION_CONTEXT: json.encode({k: values[k] for k in sorted(values)}),
        MERGE_ANDROID_MANIFEST_PERMISSIONS: False,
    }

_application_transition = transition(
    implementation = application_context,
    inputs = [APPLICATION_CONTEXT, OPERATING_SYSTEM],
    outputs = [APPLICATION_CONTEXT, MERGE_ANDROID_MANIFEST_PERMISSIONS],
)

def _pack_impl(ctx):
    pack = ctx.attr.deps[0]
    start = pack[GodotPackInfo]

    # The application delivers the native code of the add-ons of every pack it ships:
    # the start pack and the packs it may load later.
    packs = [target[GodotPackInfo] for target in ctx.attr.deps]
    delivered = struct(
        member_resource_paths = start.project.member_resource_paths,
        runtime_extensions = unique_extensions([extension for each in packs for extension in each.project.runtime_extensions]),
        export_extensions = unique_extensions([extension for each in packs for extension in each.project.export_extensions]),
        platform_libraries = unique_platform_libraries([library for each in packs for library in each.project.platform_libraries]),
        infoplists = depset(transitive = [each.project.infoplists for each in packs]),
    )
    return [
        pack[DefaultInfo],
        # The start pack, with the native code of every pack as its project.
        GodotPackInfo(
            pack_file = start.pack_file,
            pack_files = start.pack_files,
            project = delivered,
            operating_system = start.operating_system,
            cpus = start.cpus,
            environment = start.environment,
            available = start.available,
            export_options = start.export_options,
            facts = start.facts,
            version = start.version,
            editor_component = start.editor_component,
            variant = start.variant,
            icons = start.icons,
            splash = start.splash,
        ),
        pack[OutputGroupInfo],
    ]

def _loadable_pack_impl(ctx):
    return [ctx.attr.deps[0][GodotPackInfo]]

# A pack an application may load later. Only its native code reaches the application, so
# it keeps the configuration of the standalone pack, whatever the application's context.
loadable_pack = rule(
    implementation = _loadable_pack_impl,
    attrs = {
        # Named deps so rules_android's and rules_apple's aspects reach the pack's native code.
        "deps": attr.label_list(mandatory = True, cfg = project_transition, providers = [GodotPackInfo]),
    },
)

def _application_id_impl(ctx):
    return [platform_common.TemplateVariableInfo({"GODOT_APPLICATION_ID": ctx.attr.application_id})]

# A select() of godot_app.application_id cannot sit inside the dictionary of an attribute,
# such as android_binary's manifest_values; the application's rules read it as this make
# variable instead. It carries only the ID, so reading it reaches no pack.
application_id = rule(
    implementation = _application_id_impl,
    doc = "The application ID of a godot_app as the make variable GODOT_APPLICATION_ID.",
    attrs = {"application_id": attr.string()},
)

application_pack = rule(
    implementation = _pack_impl,
    attrs = {
        # The start pack, then loadable_pack targets; named deps so rules_android's and
        # rules_apple's aspects reach the native code of each.
        "deps": attr.label_list(mandatory = True, cfg = _application_transition, providers = [GodotPackInfo]),
        "application_id": attr.string(),
        "macos_minimum_os_version": attr.string(default = MACOS_MINIMUM_OS),
        "ios_minimum_os_version": attr.string(default = IOS_MINIMUM_OS),
        "ios_families": attr.string_list(default = ["iphone", "ipad"]),
        "android_min_sdk_version": attr.int(),
        "android_target_sdk_version": attr.int(),
    },
)
