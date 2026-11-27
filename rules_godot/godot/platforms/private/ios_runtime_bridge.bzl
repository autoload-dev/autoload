"""
iOS runtime toolchain payloads and the runtime bridge that exposes them in the Apple split.

The aspects of rules_apple (5.4.0) do not traverse toolchain edges. iOS runtime components
therefore replay the Swift-usage, resource and framework-provider aspects on their payload
attribute; the bridge forwards the enriched public providers on ios_application's existing
dependency edge. Linking, bundling and dSYM generation stay with rules_apple; the
private AppleDebugInfo is not loaded.
"""

load("@rules_apple//apple:aspects.bzl", "framework_provider_aspect")
load(
    "@rules_apple//apple:providers.bzl",
    "AppleDsymBundleInfo",
    "AppleFrameworkImportInfo",
    "AppleResourceInfo",
)

# ios_application applies these internal aspects to its deps; they have no public export,
# and replaying them is the bridge's purpose. The iOS bridge regressions pin the contract.
# buildifier: disable=bzl-visibility
load("@rules_apple//apple/internal/aspects:resource_aspect.bzl", "apple_resource_aspect")

# buildifier: disable=bzl-visibility
load("@rules_apple//apple/internal/aspects:swift_usage_aspect.bzl", "SwiftUsageInfo", "swift_usage_aspect")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("@rules_swift//swift:swift.bzl", "SwiftInfo")
load("//godot/engine/private:optimization.bzl", "ENGINE_SETTINGS_ATTRS", "engine_settings", "require_tunable_runtime")
load("//godot/engine/private:resolution.bzl", "RUNTIME_TOOLCHAIN_TYPE", "engine_toolchain")
load("//godot/private:providers.bzl", "GodotRuntimeInfo")

visibility(["//godot/..."])

# Applied on the runtime component's payload, before the target enters ToolchainInfo.
IOS_PAYLOAD_ASPECTS = [swift_usage_aspect, apple_resource_aspect, framework_provider_aspect]

_FORWARDED = [
    CcInfo,
    OutputGroupInfo,
    GodotRuntimeInfo,
    SwiftInfo,
    SwiftUsageInfo,
    AppleResourceInfo,
    AppleFrameworkImportInfo,
    AppleDsymBundleInfo,
]

def _bridge_impl(ctx):
    godot = engine_toolchain(ctx, "runtime", "this iOS platform slice, its iOS environment and the variant")
    require_tunable_runtime(ctx.label, ctx.attr, godot.provenance)
    target = godot.payload

    # Files only: a payload's executable belongs to the rule that created it.
    return [DefaultInfo(files = target[DefaultInfo].files)] + [
        target[provider]
        for provider in _FORWARDED
        if provider in target
    ] + [godot.provenance]

runtime_bridge_ios = rule(
    doc = "Expose the iOS runtime component resolved in this platform slice to rules_apple's linking and bundling.",
    implementation = _bridge_impl,
    toolchains = [config_common.toolchain_type(RUNTIME_TOOLCHAIN_TYPE, mandatory = False)],
    attrs = ENGINE_SETTINGS_ATTRS,
    cfg = engine_settings,
)
