"""
The files of the iOS framework that godot_cc_extension wraps its dynamic library in.

An iOS application embeds and signs the framework; Godot loads it when it loads the
extension. Each framework links its own godot-cpp and exports only the entry symbol, so
extensions from different modules never share or collide on godot-cpp's symbols.
"""

load("@apple_support//lib:apple_support.bzl", "apple_support")
load("//godot/private/config:settings.bzl", "PLATFORM_ATTRS", "target_platform")

visibility(["//godot/extension/..."])

# Characters CFBundleIdentifier allows besides letters and digits.
_IDENTIFIER_PUNCTUATION = ".-"

def framework_name(name):
    """
    Return the framework and binary name of extension name: letters, digits and _ only.

    Args:
        name: The extension's target name.

    Returns:
        The name, with every other character replaced by _.
    """
    return "".join([char if char.isalnum() or char == "_" else "_" for char in name.elems()])

def default_bundle_id(package, name):
    """
    Return the CFBundleIdentifier of extension name in package.

    Args:
        package: The extension's package, such as addons/sentry.
        name: The extension's target name.

    Returns:
        A reverse-DNS identifier unique per extension label, such as
        rules-godot.extension.addons.sentry.sentry.
    """
    segments = [segment for segment in package.split("/") if segment] + [name]
    cleaned = [
        "".join([char if char.isalnum() or char in _IDENTIFIER_PUNCTUATION else "-" for char in segment.elems()])
        for segment in segments
    ]
    return ".".join(["rules-godot", "extension"] + cleaned)

def _plist_value(value):
    if type(value) == "list":
        return "<array>%s</array>" % "".join([_plist_value(item) for item in value])
    return "<string>%s</string>" % value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def info_plist(entries):
    """
    Return an XML property list of entries, sorted by key.

    Args:
        entries: Dictionary of keys to strings or lists of strings.

    Returns:
        The property list's text.
    """
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
        '<plist version="1.0">',
        "<dict>",
    ]
    for key in sorted(entries):
        lines.append("\t<key>%s</key>" % key)
        lines.append("\t" + _plist_value(entries[key]))
    return "\n".join(lines + ["</dict>", "</plist>", ""])

def _ios_framework_files_impl(ctx):
    platform = target_platform(ctx)
    if platform.operating_system != "ios":
        fail("%s: an iOS extension framework needs an iOS target platform" % ctx.label)
    name = ctx.attr.framework_name
    directory = ctx.label.name + "/" + name + ".framework/"
    binary = ctx.actions.declare_file(directory + name)
    ctx.actions.symlink(output = binary, target_file = ctx.file.binary)
    xcode_config = ctx.attr._xcode_config[apple_common.XcodeVersionConfig]
    plist = ctx.actions.declare_file(directory + "Info.plist")
    ctx.actions.write(plist, info_plist({
        "CFBundleDevelopmentRegion": "en",
        "CFBundleExecutable": name,
        "CFBundleIdentifier": ctx.attr.bundle_id,
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": name,
        "CFBundlePackageType": "FMWK",
        "CFBundleShortVersionString": "1.0",
        "CFBundleSupportedPlatforms": ["iPhoneSimulator" if platform.environment == "simulator" else "iPhoneOS"],
        "CFBundleVersion": "1",
        # The deployment target the binary was linked for, which the App Store checks
        # against this value.
        "MinimumOSVersion": str(xcode_config.minimum_os_for_platform_type(apple_common.platform_type.ios)),
    }))
    return [DefaultInfo(files = depset([binary, plist]))]

ios_framework_files = rule(
    doc = """
    Lay out a dynamic library as <framework_name>.framework with its Info.plist, for an
    apple_dynamic_framework_import with bundle_only to hand to iOS applications.
    """,
    implementation = _ios_framework_files_impl,
    attrs = {
        "binary": attr.label(
            doc = "The dynamic library, linked with the framework's install name.",
            allow_single_file = True,
            mandatory = True,
        ),
        "framework_name": attr.string(doc = "Name of the framework and its binary.", mandatory = True),
        "bundle_id": attr.string(doc = "CFBundleIdentifier of the framework.", mandatory = True),
    } | PLATFORM_ATTRS | apple_support.action_required_attrs(),
    fragments = ["apple"],
)
