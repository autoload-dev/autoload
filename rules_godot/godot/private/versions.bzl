"""Version compatibility policy, separate from the catalogue of pinned downloads."""

visibility(["//godot/..."])

GODOT_MINIMUM_VERSION = "4.7.2"

# The macOS and iOS floors: the default minimums of applications, and the least a
# source-built engine compiles for, since the libc++ of current Xcode supports no earlier
# version. Source recipes carry the target their sources name, which may be lower.
MACOS_MINIMUM_OS = "11.0"
IOS_MINIMUM_OS = "15.0"
GODOT_SUPPORTED_VERSION_RANGE = ">=4.7.2 <5.0.0"

def _parse_version(version):
    parts = version.split("-")
    if len(parts) > 2:
        return None
    numbers = parts[0].split(".")
    if len(numbers) != 3 or any([
        not part.isdigit() or str(int(part)) != part
        for part in numbers
    ]):
        return None
    prerelease = None
    if len(parts) == 2:
        for channel in ["dev", "beta", "rc"]:
            if parts[1].startswith(channel):
                number = parts[1][len(channel):]
                if number.isdigit() and str(int(number)) == number and int(number) > 0:
                    prerelease = struct(channel = channel, number = int(number))
        if prerelease == None:
            return None
    return struct(numbers = [int(part) for part in numbers], prerelease = prerelease)

def dotted_version(version):
    """
    Tell a dotted numeric version, such as 11.0 or 10.15.3, from any other string.

    Args:
        version: The string to check.

    Returns:
        True for one or more decimal numbers joined by dots.
    """
    return bool(version) and all([part.isdigit() for part in version.split(".")])

def version_below(version, other):
    """
    Compare two dotted numeric versions, such as deployment targets.

    Args:
        version: A dotted numeric version, such as 10.15 or 11.0.
        other: The version to compare against.

    Returns:
        True when version is lower than other; a missing part counts as zero.
    """
    left = [int(part) for part in version.split(".")]
    right = [int(part) for part in other.split(".")]
    width = max(len(left), len(right))
    left += [0] * (width - len(left))
    right += [0] * (width - len(right))
    return left < right

def godot_version_error(version):
    """
    Check an engine version against the supported compatibility range.

    Args:
        version: Canonical major.minor.patch, optionally with -devN/-betaN/-rcN.

    Returns:
        A useful diagnostic, or None for a version in the compatibility range.
    """
    parsed = _parse_version(version)
    if parsed == None:
        return (
            "Godot version must be canonical major.minor.patch with optional -devN, " +
            "-betaN or -rcN, for example 4.7.2 or 4.8.0-beta1; got %r" % version
        )
    if (
        parsed.numbers[0] != 4 or
        parsed.numbers < [4, 7, 2] or
        (parsed.numbers == [4, 7, 2] and parsed.prerelease != None)
    ):
        return "rules_godot requires Godot 4.7.2 or newer within Godot 4 (%s); got %s" % (
            GODOT_SUPPORTED_VERSION_RANGE,
            version,
        )
    return None

def godot_minimum_error(version):
    """
    Check a stable GDExtension compatibility minimum, not an editor pin.

    Args:
        version: Stable canonical major.minor.patch runtime minimum.

    Returns:
        A useful diagnostic, or None for a supported stable minimum.
    """
    error = godot_version_error(version)
    if error:
        return error
    if _parse_version(version).prerelease != None:
        return (
            "GDExtension compatibility_minimum must be a stable major.minor.patch " +
            "version; got %r" % version
        )
    return None

def godot_series(version):
    """
    Return the major.minor series of a canonical engine version.

    Args:
        version: Canonical version such as 4.7.2, 4.8.0-beta1 or a source's 4.7.3-rc.

    Returns:
        For example 4.7 or 4.8.
    """
    return ".".join(version.split("-")[0].split(".")[:2])

def godot_version_name(version):
    """
    Return a canonical engine version the way Godot names its builds.

    Godot's engine libraries and Android library metadata carry this name.

    Args:
        version: Canonical version such as 4.7.2 or 4.8.0-beta1.

    Returns:
        For example 4.7.2.stable or 4.8.beta1: Godot omits a zero patch.
    """
    number, _, status = version.partition("-")
    major, minor, patch = number.split(".")
    name = "%s.%s" % (major, minor) if patch == "0" else number
    return "%s.%s" % (name, status or "stable")

def require_supported_godot_version(version, *, _fail = fail):
    """
    Reject unsupported versions before downloading or creating actions.

    Args:
        version: Canonical engine version, optionally with a prerelease suffix.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        True for a supported version; False after an error.
    """
    error = godot_version_error(version)
    if error:
        _fail(error)
        return False
    return True

def require_supported_godot_minimum(version):
    """
    Validate the stable minimum written to a GDExtension descriptor.

    Args:
        version: Stable canonical major.minor.patch runtime minimum.
    """
    error = godot_minimum_error(version)
    if error:
        fail(error)

def require_supported_source_version(version, *, _fail = fail):
    """
    Validate producer-derived source versions without inventing a prerelease number.

    Args:
        version: Actual version.py version; source channels may be unnumbered.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        True for a supported version; False after an error.
    """
    number, separator, status = version.partition("-")
    if separator and status in ["dev", "alpha", "beta", "rc"]:
        if not require_supported_godot_version(number, _fail = _fail):
            return False
        if number == GODOT_MINIMUM_VERSION:
            _fail("Source prerelease is older than the supported stable floor: " + version)
            return False
        return True
    return require_supported_godot_version(version, _fail = _fail)
