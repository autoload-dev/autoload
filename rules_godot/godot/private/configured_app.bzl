"""
Build an application under an export platform and build settings of its own, instead of a
`--config`.

`godot_configured_app` names the configuration of a `godot_app`, such as a multi-ABI release
App Bundle or an iOS Simulator build, in a BUILD file. The repository builds and tests such
applications in the same invocation as the desktop targets, without a Bazel configuration or
server of their own. It is not supported API: the repository's other modules load it across
repositories. The ruleset's tests extend the same transition (`configured_settings`).
"""

load("@rules_android//providers:providers.bzl", "AndroidBundleInfo", "ApkInfo")
load("@rules_apple//apple:providers.bzl", "AppleBundleInfo")
load("//godot/private/config:native.bzl", "PLATFORMS", "STRIP")
load("//godot/private/config:settings.bzl", "VARIANT")

# The repository's root and add-on modules load it; it is not supported API.
visibility("public")

_COMPILATION_MODE = "//command_line_option:compilation_mode"
_COPT = "//command_line_option:copt"
_DSYM = "//command_line_option:apple_generate_dsym"
_OBJCSTRIP = "//command_line_option:objc_enable_binary_stripping"
_ANDROID_FORMAT = str(Label("//godot:android_format"))
_MACOS_SIGNING = str(Label("//godot:macos_signing"))

# The settings the transition reads and writes.
CONFIGURED_SETTINGS = [
    PLATFORMS,
    _COMPILATION_MODE,
    STRIP,
    _COPT,
    _DSYM,
    _OBJCSTRIP,
    _ANDROID_FORMAT,
    _MACOS_SIGNING,
    VARIANT,
]

# The attributes that replace a setting when they are set, by attribute name.
_REPLACED = {
    "compilation_mode": _COMPILATION_MODE,
    "strip": STRIP,
    "apple_generate_dsym": _DSYM,
    "objc_enable_binary_stripping": _OBJCSTRIP,
    "android_format": _ANDROID_FORMAT,
    "macos_signing": _MACOS_SIGNING,
    "variant": VARIANT,
}

def configured_settings(settings, attr):
    """
    The settings of CONFIGURED_SETTINGS under the attributes of CONFIGURED_ATTRS.

    Args:
        settings: the incoming settings, at least those of CONFIGURED_SETTINGS.
        attr: the attributes of the rule whose transition this is.

    Returns:
        The outgoing value of each setting of CONFIGURED_SETTINGS.
    """
    result = {setting: settings[setting] for setting in CONFIGURED_SETTINGS}
    if attr.platform:
        result[PLATFORMS] = [str(attr.platform)]
    if attr.copts:
        result[_COPT] = list(settings[_COPT]) + attr.copts
    for name, setting in _REPLACED.items():
        value = getattr(attr, name)
        if value:
            result[setting] = value
    return result

# The attributes of the configuration; an unset one keeps the build's own setting.
CONFIGURED_ATTRS = {
    "platform": attr.label(doc = "The export platform or platform slice, such as `//examples:android_distribution`; the build's own target platform by default."),
    "compilation_mode": attr.string(doc = "C++ optimization, `--compilation_mode`, such as `opt` for a release build.", values = ["", "fastbuild", "dbg", "opt"]),
    "strip": attr.string(doc = "`--strip`: whether linking strips the libraries, such as `always` for release libraries whose debug symbols ship apart.", values = ["", "always", "sometimes", "never"]),
    "copts": attr.string_list(doc = "C++ options appended to `--copt`, such as `-g` for debug symbols of an optimized build."),
    "apple_generate_dsym": attr.bool(doc = "`--apple_generate_dsym`: Apple applications get their debug symbols as `.dSYM` directories."),
    "objc_enable_binary_stripping": attr.bool(doc = "`--objc_enable_binary_stripping`: Apple binaries are stripped of their debug symbols."),
    "android_format": attr.string(doc = "The Android delivery format, `//godot:android_format`: `apk` or `aab`.", values = ["", "apk", "aab"]),
    "macos_signing": attr.string(doc = "How macOS applications are signed, `//godot:macos_signing`, such as `adhoc`.", values = ["", "unsigned", "adhoc"]),
    "variant": attr.string(doc = "The `//godot:variant` setting: which of Godot's binaries the build is for.", values = ["", "debug", "editor", "release"]),
}

# Providers of applications that inspection rules, such as android_bundle_test, read.
_FORWARDED = [AndroidBundleInfo, ApkInfo, AppleBundleInfo, OutputGroupInfo]

def configured_providers(ctx):
    """
    The providers of a rule whose `target` attribute carries the configuration.

    They are the target's default outputs and the application providers, or the files of
    one output group when the rule has a set `output_group` attribute; the runfiles too when
    it has a set `runfiles` attribute.

    Args:
        ctx: the context of the rule.

    Returns:
        A list of providers.
    """
    target = ctx.attr.target[0]
    output_group = getattr(ctx.attr, "output_group", "")
    files = target[DefaultInfo].files
    if output_group:
        files = getattr(target[OutputGroupInfo], output_group)
    runfiles = ctx.runfiles(transitive_files = files)
    if getattr(ctx.attr, "runfiles", False):
        runfiles = runfiles.merge(target[DefaultInfo].default_runfiles)
    providers = [DefaultInfo(files = files, runfiles = runfiles)]
    if not output_group:
        providers.extend([target[provider] for provider in _FORWARDED if provider in target])
    return providers

_configured = transition(
    implementation = configured_settings,
    inputs = CONFIGURED_SETTINGS,
    outputs = CONFIGURED_SETTINGS,
)

_configured_target = rule(
    implementation = configured_providers,
    doc = "The default outputs and application providers of a target built under an export platform and build settings of its own.",
    attrs = CONFIGURED_ATTRS | {
        "target": attr.label(mandatory = True, cfg = _configured, doc = "The target to build."),
    },
)

def godot_configured_app(name, app, **kwargs):
    """
    Build a `godot_app` and its debug symbols under an export platform and build settings.

    The macro declares `<name>`, the application, and `<name>.debug_symbols`, its debug
    symbols, both under the same configuration.

    Args:
        name: the name of the application target.
        app: the label of a `godot_app`.
        **kwargs: the attributes of CONFIGURED_ATTRS, and common attributes such as `tags`
            and `visibility`, of both targets.
    """
    label = native.package_relative_label(app)
    _configured_target(name = name, target = label, **kwargs)
    _configured_target(
        name = name + ".debug_symbols",
        target = label.same_package_label(label.name + ".debug_symbols"),
        **kwargs
    )
