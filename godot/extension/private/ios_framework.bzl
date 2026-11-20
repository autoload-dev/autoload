"""
The files of the iOS framework that godot_cc_extension wraps its dynamic library in.

An iOS application embeds and signs the framework; Godot loads it when it loads the
extension. Each framework links its own godot-cpp and exports only the entry symbol, so
extensions from different modules never share or collide on godot-cpp's symbols.

rules_apple's ios_dynamic_framework would relink the binary from deps under its own
transition, without the extension's export list and configuration; this rule lays out
the binary godot_cc_extension already linked. Its Info.plist has fixed string keys, so it
is written here rather than by a plist tool action.
"""

load("@apple_support//lib:apple_support.bzl", "apple_support")
load("@rules_apple//apple:apple.bzl", "apple_dynamic_framework_import")
load("//godot/private/config:settings.bzl", "PLATFORM_ATTRS", "target_platform")

visibility(["//godot/extension/..."])

def _sanitize(text, allowed, replacement):
    """Text with every character but letters, digits and those in allowed replaced."""
    return "".join([char if char.isalnum() or char in allowed else replacement for char in text.elems()])

def framework_name(name):
    """
    Return the framework and binary name of extension name: letters, digits and _ only.

    Args:
        name: The extension's target name.

    Returns:
        The name, with every other character replaced by _.
    """
    return _sanitize(name, "_", "_")

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
    return ".".join(["rules-godot", "extension"] + [_sanitize(segment, ".-", "-") for segment in segments])

def _plist_string(value):
    return "<string>%s</string>" % value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _plist_value(value):
    if type(value) == "list":
        return "<array>%s</array>" % "".join([_plist_string(item) for item in value])
    return _plist_string(value)

def _info_plist(entries):
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
    xcode_config = ctx.attr._xcode_config[apple_common.XcodeVersionConfig]

    # rules_cc's toolchain sets the install name after the target's linkopts, from the
    # shared library's own file name; a framework's binary carries its framework path.
    # The application signs the framework when it embeds it.
    apple_support.run_shell(
        actions = ctx.actions,
        xcode_config = xcode_config,
        apple_fragment = ctx.fragments.apple,
        command = 'cp "$1" "$2" && chmod u+w "$2" && xcrun install_name_tool -id "$3" "$2"',
        arguments = [ctx.file.binary.path, binary.path, "@rpath/%s.framework/%s" % (name, name)],
        inputs = [ctx.file.binary],
        outputs = [binary],
        mnemonic = "GodotFrameworkInstallName",
        progress_message = "Setting the install name of %{output}",
    )
    plist = ctx.actions.declare_file(directory + "Info.plist")
    ctx.actions.write(plist, _info_plist({
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
            doc = "The dynamic library; its copy in the framework gets the framework's install name.",
            allow_single_file = True,
            mandatory = True,
        ),
        "framework_name": attr.string(doc = "Name of the framework and its binary.", mandatory = True),
        "bundle_id": attr.string(doc = "CFBundleIdentifier of the framework.", mandatory = True),
    } | PLATFORM_ATTRS | apple_support.action_required_attrs(),
    fragments = ["apple"],
)

def ios_framework(name, shared, bundle_id, generated):
    """
    Declare the iOS framework of extension name around its shared library.

    Args:
        name: The extension's target name.
        shared: Name of the extension's shared library target in this package.
        bundle_id: CFBundleIdentifier of the framework; empty derives one from the
            extension's label.
        generated: The attributes of the private targets godot_cc_extension generates.

    Returns:
        The name of the framework import that iOS applications embed.
    """
    files = name + ".ios_framework_files"
    ios_framework_files(
        name = files,
        binary = ":" + shared,
        framework_name = framework_name(name),
        bundle_id = bundle_id or default_bundle_id(native.package_name(), name),
        **generated
    )
    framework = name + ".ios_framework"

    # Godot loads the framework, so nothing links it: the application embeds and signs it.
    apple_dynamic_framework_import(
        name = framework,
        bundle_only = True,
        framework_imports = [":" + files],
        **generated
    )
    return framework
