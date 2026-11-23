"""
The Bazel options with which the ruleset's transitions configure native code.

It decides the options of these edges: an application's own edge (the iOS application's),
the content configuration and the platform slices of a pack, an extension's library and
the macOS minimum that an application sets for its pack and the project context restores.
Each of those transitions takes its options from here, so that the native code of one
application is configured once for each platform slice.

Two places set native options elsewhere, for their own reasons. The `_floor` transitions of
source-built engines (godot/engine/private/generator.bzl) compile an engine for Godot's
own deployment target, whatever an application's; they take only the option labels and
UNSTRIPPED from here. `_split_flags` in settings.bzl writes the split options of a platform
slice as the export platform's command-line flags, which no transition can read.
"""

load(
    ":settings.bzl",
    "ANDROID_PLATFORMS_SETTING",
    "CPUS",
    "ENVIRONMENT",
    "EXPORT_PLATFORM",
    "MACOS_MINIMUM_OS_OUTSIDE_APPLICATION",
    "OPERATING_SYSTEM",
    "PLATFORM_SLICES",
    "ios_cpu",
)

visibility(["//godot/..."])

PLATFORMS = "//command_line_option:platforms"
STRIP = "//command_line_option:strip"
MACOS_MINIMUM_OS_OPTION = "//command_line_option:macos_minimum_os"
IOS_MINIMUM_OS_OPTION = "//command_line_option:ios_minimum_os"
COMPILATION_MODE = "//command_line_option:compilation_mode"
COPT = "//command_line_option:copt"
LINKOPT = "//command_line_option:linkopt"
_CPU = "//command_line_option:cpu"
_APPLE_CPU = "//command_line_option:apple_split_cpu"

# rules_apple's application rules set it on their own edge; a pack built directly for an
# iOS platform needs it too, or apple_support derives a macOS CPU name such as
# darwin_sim_arm64 from the iOS split CPU.
_APPLE_PLATFORM_TYPE = "//command_line_option:apple_platform_type"
_ANDROID_PLATFORMS = "//command_line_option:android_platforms"
_DYNAMIC = "//command_line_option:dynamic_mode"

# Native code that links without Bazel's --strip.
UNSTRIPPED = {STRIP: "never"}

# The options content_options and platform_slice_options set, which a transition calling
# them declares as outputs, and as inputs together with PLATFORM_INPUTS.
PLATFORM_OPTIONS = [PLATFORMS, _CPU, _APPLE_CPU, _APPLE_PLATFORM_TYPE, _ANDROID_PLATFORMS, ANDROID_PLATFORMS_SETTING, _DYNAMIC, STRIP]
PLATFORM_INPUTS = PLATFORM_OPTIONS + [CPUS, ENVIRONMENT, EXPORT_PLATFORM, OPERATING_SYSTEM, PLATFORM_SLICES]

# The native options every native configuration of an operating system's applications has,
# by operating system; the build's own values apply to the others. An iOS application sets
# them on its own edge for its whole graph, and the content and platform slice options
# include them, so a pack or extension built by itself for iOS is configured as in an
# application. iOS builds without --strip: rules_apple strips the executable with
# --objc_enable_binary_stripping and ignores --strip, and the extension frameworks it
# embeds link without it anyway.
APPLICATION_OPTIONS = {"ios": UNSTRIPPED}

def content_options(settings):
    """
    Return the native options of the content configuration of the build's export platform.

    Args:
        settings: Transition input settings, with PLATFORM_INPUTS.

    Returns:
        A dictionary of PLATFORM_OPTIONS to values; empty without an export platform.
    """
    export_platform = settings[EXPORT_PLATFORM]
    if not export_platform:
        return {}
    operating_system = settings[OPERATING_SYSTEM]
    values = {PLATFORMS: [export_platform]} | APPLICATION_OPTIONS.get(operating_system, {})
    if operating_system == "ios":
        values[_CPU] = "ios_" + ios_cpu(settings[ENVIRONMENT], settings[CPUS].split(",")[0])
        values[_APPLE_CPU] = ""
        values[_APPLE_PLATFORM_TYPE] = "ios"
    elif operating_system == "android":
        # The content configuration is the same whether an application's configuration
        # or a platform slice's reached it; the slices take this linking mode from
        # rules_android's split.
        platform_slices = settings[PLATFORM_SLICES].split(",")
        values[_DYNAMIC] = "off"
        values[_ANDROID_PLATFORMS] = platform_slices
        values[ANDROID_PLATFORMS_SETTING] = platform_slices
    return values

def platform_slice_options(settings, cpu, platform_slice):
    """
    Return the native options of one platform slice of the build's export platform.

    Args:
        settings: Transition input settings, with PLATFORM_INPUTS.
        cpu: The platform slice's CPU table key, such as arm64.
        platform_slice: The platform slice's label string.

    Returns:
        A dictionary of PLATFORM_OPTIONS to values.
    """
    operating_system = settings[OPERATING_SYSTEM]
    values = {PLATFORMS: [platform_slice]} | APPLICATION_OPTIONS.get(operating_system, {})
    if operating_system == "ios":
        apple_cpu = ios_cpu(settings[ENVIRONMENT], cpu)
        values[_CPU] = "ios_" + apple_cpu
        values[_APPLE_CPU] = apple_cpu
        values[_APPLE_PLATFORM_TYPE] = "ios"
    elif operating_system == "android":
        # As rules_android's split of an application's deps sets them, so that the
        # application's native code and the pack's share each platform slice.
        values[_DYNAMIC] = "off"
        values[_ANDROID_PLATFORMS] = []
        values[ANDROID_PLATFORMS_SETTING] = []
    return values

# The native options of an extension's library and of the other native code that
# applications package (keep_debug_info in godot/private/symbols.bzl): it links without
# --strip, whose link-time stripping would remove the DWARF the applications' debug
# symbols need; the applications apply --strip to the copy they package. The build's
# macOS minimum that a macOS application keeps for the project context means nothing to
# native code, so the library drops it and shares its configuration with the project
# context's wherever the application's minimum is the build's.
LIBRARY_OPTIONS = UNSTRIPPED | {MACOS_MINIMUM_OS_OUTSIDE_APPLICATION: ""}

# The options an application sets for its pack and outside_application_options restores
# for the project context: today the macOS minimum and the build's own one.
APPLICATION_SCOPED_OPTIONS = [MACOS_MINIMUM_OS_OPTION, MACOS_MINIMUM_OS_OUTSIDE_APPLICATION]

def macos_application_options(settings, minimum_os_version):
    """
    Return the native options a macOS application sets on its edge to its pack.

    The application's minimum is the deployment target of the native code its pack builds
    for macOS, such as extension libraries. The build's own minimum is kept for
    outside_application_options to restore.

    Args:
        settings: Transition input settings, with APPLICATION_SCOPED_OPTIONS.
        minimum_os_version: The application's minimum macOS version.

    Returns:
        A dictionary of APPLICATION_SCOPED_OPTIONS to values.
    """
    build_minimum = settings[MACOS_MINIMUM_OS_OPTION]
    outside = settings[MACOS_MINIMUM_OS_OUTSIDE_APPLICATION] or json.encode(
        str(build_minimum) if build_minimum != None else None,
    )
    return {
        MACOS_MINIMUM_OS_OPTION: minimum_os_version,
        MACOS_MINIMUM_OS_OUTSIDE_APPLICATION: outside,
    }

def outside_application_options(settings):
    """
    Return the native options outside a macOS application: the build's own minimum macOS version.

    Args:
        settings: Transition input settings, with APPLICATION_SCOPED_OPTIONS.

    Returns:
        A dictionary of APPLICATION_SCOPED_OPTIONS to values.
    """
    outside = settings[MACOS_MINIMUM_OS_OUTSIDE_APPLICATION]
    return {
        MACOS_MINIMUM_OS_OPTION: json.decode(outside) if outside else settings[MACOS_MINIMUM_OS_OPTION],
        MACOS_MINIMUM_OS_OUTSIDE_APPLICATION: "",
    }
