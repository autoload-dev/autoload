"""An application's minimum operating-system version against what it packages."""

load(":versions.bzl", "version_below")

visibility(["//godot/..."])

_NAMES = {"macos": "macOS", "ios": "iOS"}

def check_minimum_os(minimum, attribute, operating_system, runtime, extensions):
    """
    Check an application's minimum version against its runtime and extensions.

    Fails when the minimum falls below the runtime's deployment target or below what one
    of the extensions requires on this operating system.

    Args:
        minimum: The application's minimum version, a dotted numeric string.
        attribute: The godot_app attribute that sets it, for the diagnostic.
        operating_system: macos or ios.
        runtime: GodotRuntimeInfo of the packaged runtime, or None where the runtime is
            an opaque library without one.
        extensions: GodotExtensionInfo of the pack's runtime extensions.
    """
    if runtime and runtime.minimum_os and version_below(minimum, runtime.minimum_os):
        fail("%s %s is below the deployment target %s of the runtime %s" % (
            attribute,
            minimum,
            runtime.minimum_os,
            runtime.origin,
        ))
    for extension in extensions:
        required = extension.minimum_os_versions.get(operating_system, "")
        library = extension.library
        if required and library.operating_system == operating_system and version_below(minimum, required):
            fail("extension %s requires %s %s; %s is %s" % (
                extension.entry_symbol,
                _NAMES[operating_system],
                required,
                attribute,
                minimum,
            ))
