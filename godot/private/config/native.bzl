"""
The Bazel options with which the ruleset configures native code, decided in one place.

Native code reaches an application on several edges: the application's own edge, the
content configuration and platform slices of its pack, an extension's library and the
project context of imports. Each of those transitions takes the options it sets for native
code from here, so that the native code of one application is configured once for each
platform slice and an option has one definition for every edge that sets it.
"""

load(
    ":settings.bzl",
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
MACOS_MINIMUM_OS = "//command_line_option:macos_minimum_os"
_CPU = "//command_line_option:cpu"
_APPLE_CPU = "//command_line_option:apple_split_cpu"

# rules_apple's application rules set it on their own edge; a pack built directly for an
# iOS platform needs it too, or apple_support derives a macOS CPU name such as
# darwin_sim_arm64 from the iOS split CPU.
_APPLE_PLATFORM_TYPE = "//command_line_option:apple_platform_type"
_ANDROID_PLATFORMS = "//command_line_option:android_platforms"
_ANDROID_SETTING = str(Label("@rules_android//flags:android_platforms"))
_DYNAMIC = "//command_line_option:dynamic_mode"

# The options content_options and platform_slice_options set, which a transition calling
# them declares as outputs, and as inputs together with PLATFORM_INPUTS.
PLATFORM_OPTIONS = [PLATFORMS, _CPU, _APPLE_CPU, _APPLE_PLATFORM_TYPE, _ANDROID_PLATFORMS, _ANDROID_SETTING, _DYNAMIC, STRIP]
PLATFORM_INPUTS = PLATFORM_OPTIONS + [CPUS, ENVIRONMENT, EXPORT_PLATFORM, OPERATING_SYSTEM, PLATFORM_SLICES]

def application_options(operating_system):
    """
    Return the native options every native configuration of an operating system's applications has.

    An iOS application sets them on its own edge for its whole graph; the content and
    platform slice options include them, so a pack or extension built by itself for the
    operating system is configured as in an application. iOS builds without --strip:
    rules_apple strips the executable with --objc_enable_binary_stripping and ignores
    --strip, and the extension frameworks it embeds link without it anyway.

    Args:
        operating_system: The export platform's operating system, such as ios.

    Returns:
        A dictionary of option labels to values; empty where the build's own values apply.
    """
    if operating_system == "ios":
        return {STRIP: "never"}
    return {}

def _ios_cpu(environment, cpu):
    return "ios_" + ios_cpu(environment, cpu)

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
    values = {PLATFORMS: [export_platform]} | application_options(operating_system)
    if operating_system == "ios":
        values[_CPU] = _ios_cpu(settings[ENVIRONMENT], settings[CPUS].split(",")[0])
        values[_APPLE_CPU] = ""
        values[_APPLE_PLATFORM_TYPE] = "ios"
    elif operating_system == "android":
        # The content configuration is the same whether an application's configuration
        # or a platform slice's reached it; the slices take this linking mode from
        # rules_android's split.
        values[_DYNAMIC] = "off"
        values[_ANDROID_PLATFORMS] = settings[PLATFORM_SLICES].split(",")
        values[_ANDROID_SETTING] = settings[PLATFORM_SLICES].split(",")
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
    values = {PLATFORMS: [platform_slice]} | application_options(operating_system)
    if operating_system == "ios":
        bazel_cpu = _ios_cpu(settings[ENVIRONMENT], cpu)
        values[_CPU] = bazel_cpu
        values[_APPLE_CPU] = bazel_cpu.removeprefix("ios_")
        values[_APPLE_PLATFORM_TYPE] = "ios"
    elif operating_system == "android":
        # As rules_android's split of an application's deps sets them, so that the
        # application's native code and the pack's share each platform slice.
        values[_DYNAMIC] = "off"
        values[_ANDROID_PLATFORMS] = []
        values[_ANDROID_SETTING] = []
    return values

# The native options of an extension's library and of the other native code that
# applications package (keep_debug_info in godot/private/symbols.bzl): it links without
# --strip, whose link-time stripping would remove the DWARF the applications' debug
# symbols need; the applications apply --strip to the copy they package. The build's
# macOS minimum that a macOS application keeps for the project context means nothing to
# native code, so the library drops it and shares its configuration with the project
# context's wherever the application's minimum is the build's.
LIBRARY_OPTIONS = {STRIP: "never", MACOS_MINIMUM_OS_OUTSIDE_APPLICATION: ""}

# The options macos_application_options and outside_application_options set.
MACOS_APPLICATION_OPTIONS = [MACOS_MINIMUM_OS, MACOS_MINIMUM_OS_OUTSIDE_APPLICATION]

def macos_application_options(settings, minimum_os_version):
    """
    Return the native options a macOS application sets on its edge to its pack.

    The application's minimum is the deployment target of the native code its pack builds
    for macOS, such as extension libraries. The build's own minimum is kept for
    outside_application_options to restore.

    Args:
        settings: Transition input settings, with MACOS_APPLICATION_OPTIONS.
        minimum_os_version: The application's minimum macOS version.

    Returns:
        A dictionary of MACOS_APPLICATION_OPTIONS to values.
    """
    build_minimum = settings[MACOS_MINIMUM_OS]
    outside = settings[MACOS_MINIMUM_OS_OUTSIDE_APPLICATION] or json.encode(
        str(build_minimum) if build_minimum != None else None,
    )
    return {
        MACOS_MINIMUM_OS: minimum_os_version,
        MACOS_MINIMUM_OS_OUTSIDE_APPLICATION: outside,
    }

def outside_application_options(settings):
    """
    Return the native options outside a macOS application: the build's own minimum macOS version.

    Args:
        settings: Transition input settings, with MACOS_APPLICATION_OPTIONS.

    Returns:
        A dictionary of MACOS_APPLICATION_OPTIONS to values.
    """
    outside = settings[MACOS_MINIMUM_OS_OUTSIDE_APPLICATION]
    return {
        MACOS_MINIMUM_OS: json.decode(outside) if outside else settings[MACOS_MINIMUM_OS],
        MACOS_MINIMUM_OS_OUTSIDE_APPLICATION: "",
    }
