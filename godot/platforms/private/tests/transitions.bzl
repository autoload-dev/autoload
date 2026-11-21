"""
Build a fixture under the configuration a platform test needs, instead of a `--config`.

`configured_outputs` builds its target under an export platform and optional settings, so a
build-output test names its configuration itself and runs in one `bazel test` invocation
with every other variant.
"""

load("@rules_android//providers:providers.bzl", "AndroidBundleInfo", "ApkInfo")
load("@rules_apple//apple:providers.bzl", "AppleBundleInfo")

visibility([
    "//godot/engine/private/tests/...",
    "//godot/extension/tests/...",
    "//godot/platforms/private/tests/...",
])

_PLATFORMS = "//command_line_option:platforms"
_EXTRA_TOOLCHAINS = "//command_line_option:extra_toolchains"
_COMPILATION_MODE = "//command_line_option:compilation_mode"
_STRIP = "//command_line_option:strip"
_COPT = "//command_line_option:copt"
_DSYM = "//command_line_option:apple_generate_dsym"
_OBJC_STRIP = "//command_line_option:objc_enable_binary_stripping"
_ANDROID_FORMAT = str(Label("//godot:android_format"))
_ANDROID_API_LEVEL = "@androidsdk//:api_level"
_VARIANT = str(Label("//godot:variant"))
_ENGINE = str(Label("//godot:engine"))

_SETTINGS = [
    _PLATFORMS,
    _EXTRA_TOOLCHAINS,
    _COMPILATION_MODE,
    _STRIP,
    _COPT,
    _DSYM,
    _OBJC_STRIP,
    _ANDROID_FORMAT,
    _ANDROID_API_LEVEL,
    _VARIANT,
    _ENGINE,
]

def _configured_impl(settings, attr):
    result = {setting: settings[setting] for setting in _SETTINGS}
    if attr.platform:
        result[_PLATFORMS] = [str(attr.platform)]
    result[_EXTRA_TOOLCHAINS] = settings[_EXTRA_TOOLCHAINS] + attr.extra_toolchains
    if attr.compilation_mode:
        result[_COMPILATION_MODE] = attr.compilation_mode
    if attr.strip:
        result[_STRIP] = attr.strip
    if attr.copts:
        result[_COPT] = list(settings[_COPT]) + attr.copts
    if attr.apple_generate_dsym:
        result[_DSYM] = True
    if attr.objc_enable_binary_stripping:
        result[_OBJC_STRIP] = True
    if attr.android_format:
        result[_ANDROID_FORMAT] = attr.android_format
    if attr.android_api_level:
        result[_ANDROID_API_LEVEL] = attr.android_api_level
    if attr.variant:
        result[_VARIANT] = attr.variant
    if attr.engine:
        result[_ENGINE] = attr.engine
    return result

_configured = transition(
    implementation = _configured_impl,
    inputs = _SETTINGS,
    outputs = _SETTINGS,
)

# Providers of applications that inspection rules, such as android_bundle_test, read.
_FORWARDED = [AndroidBundleInfo, ApkInfo, AppleBundleInfo, OutputGroupInfo]

def _configured_outputs_impl(ctx):
    target = ctx.attr.target[0]
    files = target[DefaultInfo].files
    if ctx.attr.output_group:
        files = getattr(target[OutputGroupInfo], ctx.attr.output_group)
    runfiles = ctx.runfiles(transitive_files = files)
    if ctx.attr.runfiles:
        runfiles = runfiles.merge(target[DefaultInfo].default_runfiles)
    providers = [DefaultInfo(
        files = files,
        runfiles = runfiles,
    )]
    if not ctx.attr.output_group:
        providers.extend([target[provider] for provider in _FORWARDED if provider in target])
    return providers

configured_outputs = rule(
    implementation = _configured_outputs_impl,
    doc = "The default outputs and application providers, or one output group, of a target built under an export platform.",
    attrs = {
        "target": attr.label(mandatory = True, cfg = _configured, doc = "The fixture to build."),
        "platform": attr.label(doc = "The export platform or platform slice; the build's own target platform by default."),
        "extra_toolchains": attr.string_list(doc = "Further toolchain patterns as absolute labels, such as a source-built engine's `@<hub>//toolchains:all`."),
        "engine": attr.string(doc = "The `//godot:engine` setting, such as `beta` for a registered named engine; a build setting keeps the exec configuration of the tools unchanged, unlike `extra_toolchains`."),
        "compilation_mode": attr.string(values = ["", "fastbuild", "dbg", "opt"]),
        "strip": attr.string(values = ["", "always", "sometimes", "never"]),
        "copts": attr.string_list(doc = "Appended to `--copt`."),
        "apple_generate_dsym": attr.bool(),
        "objc_enable_binary_stripping": attr.bool(),
        "android_format": attr.string(values = ["", "apk", "aab"]),
        "android_api_level": attr.string(doc = "The `@androidsdk//:api_level` setting, such as 36."),
        "variant": attr.string(values = ["", "debug", "editor", "release"], doc = "The `//godot:variant` setting."),
        "output_group": attr.string(doc = "An output group of the target instead of its default outputs; it forwards no providers."),
        "runfiles": attr.bool(doc = "Forward the target's runfiles too, which running an executable target needs."),
    },
)
