"""
Build a fixture under the configuration a platform test needs, instead of a `--config`.

`configured_outputs` builds its target under an export platform and optional settings, so a
build-output test names its configuration itself and runs in one `bazel test` invocation
with every other variant. It extends the transition of `godot_configured_app`
(`//godot/private:configured_app.bzl`) with the development engines and the toolchains of
the ruleset's tests.
"""

load(
    "//godot/private:configured_app.bzl",
    "CONFIGURED_ATTRS",
    "CONFIGURED_SETTINGS",
    "configured_providers",
    "configured_settings",
)
load("//godot/private/tests:toolchains.bzl", "DEVELOPMENT_ENGINES", "ENGINE", "development_engine")

visibility([
    "//godot/engine/private/tests/...",
    "//godot/extension/tests/...",
    "//godot/platforms/private/tests/...",
])

_EXTRA_TOOLCHAINS = "//command_line_option:extra_toolchains"
_ANDROID_API_LEVEL = "@androidsdk//:api_level"

_SETTINGS = CONFIGURED_SETTINGS + [_EXTRA_TOOLCHAINS, _ANDROID_API_LEVEL, ENGINE]

def _configured_impl(settings, attr):
    result = configured_settings(settings, attr)
    result[_EXTRA_TOOLCHAINS] = settings[_EXTRA_TOOLCHAINS] + attr.extra_toolchains
    result[_ANDROID_API_LEVEL] = attr.android_api_level or settings[_ANDROID_API_LEVEL]
    result[ENGINE] = settings[ENGINE]
    if attr.engine:
        result.update(development_engine(attr.engine))
    return result

_configured = transition(
    implementation = _configured_impl,
    inputs = _SETTINGS,
    outputs = _SETTINGS,
)

configured_outputs = rule(
    implementation = configured_providers,
    doc = "The default outputs and application providers, or one output group, of a target built under an export platform.",
    attrs = CONFIGURED_ATTRS | {
        "target": attr.label(mandatory = True, cfg = _configured, doc = "The fixture to build."),
        "extra_toolchains": attr.string_list(doc = "Registration sets as absolute labels, appended to `--extra_toolchains` ahead of the registered engines, such as a source-built hub's `@<hub>//toolchains:all`; see the contract in `//godot/private/tests:toolchains.bzl`."),
        "engine": attr.string(
            doc = "The development engine, a key of DEVELOPMENT_ENGINES such as `beta`, selected by its engine name; the build's own by default. See the contract in `//godot/private/tests:toolchains.bzl`.",
            values = [""] + DEVELOPMENT_ENGINES.keys(),
        ),
        "android_api_level": attr.string(doc = "The `@androidsdk//:api_level` setting, such as 36."),
        "output_group": attr.string(doc = "An output group of the target instead of its default outputs; it forwards no providers."),
        "runfiles": attr.bool(doc = "Forward the target's runfiles too, which running an executable target needs."),
    },
)
