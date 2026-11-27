"""
Build an application under an export platform and build settings of its own, instead of a
`--config`.

`godot_configured_app` names the configuration of a `godot_app`, such as a multi-ABI release
App Bundle or an iOS Simulator build, in a BUILD file. The repository builds and tests such
applications in the same invocation as the desktop targets, without a Bazel configuration or
server of their own: the examples' releases (`releases.bzl`) and the mobile smoke scenarios
of `e2e/rules_godot/smoke/`. It uses only public labels and providers of the ruleset. The
ruleset's platform tests keep a copy of the transition and its attributes
(`rules_godot/godot/platforms/private/tests/configured_app.bzl`); change both together.
"""

load("@rules_android//providers:providers.bzl", "AndroidBundleInfo", "ApkInfo")
load("@rules_apple//apple:providers.bzl", "AppleBundleInfo")

_PLATFORMS = "//command_line_option:platforms"
_STRIP = "//command_line_option:strip"
_VARIANT = str(Label("@autoload_rules_godot//godot:variant"))
_COMPILATION_MODE = "//command_line_option:compilation_mode"
_COPT = "//command_line_option:copt"
_DSYM = "//command_line_option:apple_generate_dsym"
_OBJCSTRIP = "//command_line_option:objc_enable_binary_stripping"
_ANDROID_FORMAT = str(Label("@autoload_rules_godot//godot:android_format"))
_MACOS_SIGNING = str(Label("@autoload_rules_godot//godot:macos_signing"))

# The settings the transition reads and writes.
_CONFIGURED_SETTINGS = [
    _PLATFORMS,
    _COMPILATION_MODE,
    _STRIP,
    _COPT,
    _DSYM,
    _OBJCSTRIP,
    _ANDROID_FORMAT,
    _MACOS_SIGNING,
    _VARIANT,
]

# The attributes that replace a setting when they are set, by attribute name.
_REPLACED = {
    "compilation_mode": _COMPILATION_MODE,
    "strip": _STRIP,
    "apple_generate_dsym": _DSYM,
    "objc_enable_binary_stripping": _OBJCSTRIP,
    "android_format": _ANDROID_FORMAT,
    "macos_signing": _MACOS_SIGNING,
    "variant": _VARIANT,
}

def _configured_settings(settings, attr):
    """
    The settings of _CONFIGURED_SETTINGS under the attributes of _CONFIGURED_ATTRS.

    Args:
        settings: the incoming settings, at least those of _CONFIGURED_SETTINGS.
        attr: the attributes of the rule whose transition this is.

    Returns:
        The outgoing value of each setting of _CONFIGURED_SETTINGS.
    """
    result = {setting: settings[setting] for setting in _CONFIGURED_SETTINGS}
    if attr.platform:
        result[_PLATFORMS] = [str(attr.platform)]
    if attr.copts:
        result[_COPT] = list(settings[_COPT]) + attr.copts
    for name, setting in _REPLACED.items():
        value = getattr(attr, name)
        if value:
            result[setting] = value
    return result

# The attributes of the configuration; an unset one keeps the build's own setting.
_CONFIGURED_ATTRS = {
    "platform": attr.label(
        doc = """
        The export platform or platform slice, such as `//examples:android_distribution`; the
        build's own target platform by default.
        """,
    ),
    "compilation_mode": attr.string(
        doc = "C++ optimization, `--compilation_mode`, such as `opt` for a release build.",
        values = ["", "fastbuild", "dbg", "opt"],
    ),
    "strip": attr.string(
        doc = """
        `--strip`: whether linking strips the libraries, such as `always` for release
        libraries whose debug symbols ship apart.
        """,
        values = ["", "always", "sometimes", "never"],
    ),
    "copts": attr.string_list(
        doc = "C++ options appended to `--copt`, such as `-g` for debug symbols of an optimized build.",
    ),
    "apple_generate_dsym": attr.bool(
        doc = "`--apple_generate_dsym`: Apple applications get their debug symbols as `.dSYM` directories.",
    ),
    "objc_enable_binary_stripping": attr.bool(
        doc = "`--objc_enable_binary_stripping`: Apple binaries are stripped of their debug symbols.",
    ),
    "android_format": attr.string(
        doc = "The Android delivery format, `//godot:android_format`: `apk` or `aab`.",
        values = ["", "apk", "aab"],
    ),
    "macos_signing": attr.string(
        doc = "How macOS applications are signed, `//godot:macos_signing`, such as `adhoc`.",
        values = ["", "unsigned", "adhoc"],
    ),
    "variant": attr.string(
        doc = "The `//godot:variant` setting: which of Godot's binaries the build is for.",
        values = ["", "debug", "editor", "release"],
    ),
}

# The native settings of a release build whose debug symbols ship apart, as the
# configurations android-release and ios-release of the repository's .bazelrc set them.
ANDROID_RELEASE = {
    "compilation_mode": "opt",
    # Do not encode a changing sandbox directory in DWARF.
    "copts": [
        "-g",
        "-fdebug-compilation-dir=.",
    ],
    "strip": "always",
}

APPLE_RELEASE = {
    # Match the stripped application to its retained DWARF by executable/dSYM UUID.
    "apple_generate_dsym": True,
    "compilation_mode": "opt",
    "objc_enable_binary_stripping": True,
}

# Providers of applications that inspection rules, such as android_bundle_test, read.
_FORWARDED = [AndroidBundleInfo, ApkInfo, AppleBundleInfo, OutputGroupInfo]

def _forwarded_providers(target):
    """
    The application providers of a target, which inspection rules read.

    Args:
        target: the configured target.

    Returns:
        A list of providers.
    """
    return [target[provider] for provider in _FORWARDED if provider in target]

def _configured_providers(ctx):
    """
    The default outputs and application providers of the target a rule's `target` carries.

    Args:
        ctx: the context of the rule.

    Returns:
        A list of providers.
    """
    target = ctx.attr.target[0]
    files = target[DefaultInfo].files
    providers = [DefaultInfo(files = files, runfiles = ctx.runfiles(transitive_files = files))]
    return providers + _forwarded_providers(target)

_configured = transition(
    implementation = _configured_settings,
    inputs = _CONFIGURED_SETTINGS,
    outputs = _CONFIGURED_SETTINGS,
)

_configured_target = rule(
    doc = "The default outputs and application providers of a target built under an export platform and build settings of its own.",
    implementation = _configured_providers,
    attrs = _CONFIGURED_ATTRS | {
        "target": attr.label(doc = "The target to build.", mandatory = True, cfg = _configured),
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
        **kwargs: the attributes of _CONFIGURED_ATTRS, and common attributes such as `tags`
            and `visibility`, of both targets.
    """
    label = native.package_relative_label(app)
    _configured_target(name = name, target = label, **kwargs)
    _configured_target(
        name = name + ".debug_symbols",
        target = label.same_package_label(label.name + ".debug_symbols"),
        **kwargs
    )
