"""
Android runtime toolchain payloads and the runtime bridge that exposes them in the Android split.

The pinned rules_android 0.8.0 aspects do not traverse toolchain edges. Android runtime
components therefore replay the dex/desugar, neverlink and engine-symbol aspects on their
payload attribute; the bridge forwards the enriched providers on the existing android_binary
dependency edge. Its guards rely on upstream implementation details; the Android bridge
regressions pin them for dependency upgrades.
"""

load(
    "@rules_android//providers:providers.bzl",
    "AndroidCcLinkParamsInfo",
    "AndroidIdeInfo",
    "AndroidLibraryResourceClassJarProvider",
    "AndroidLintRulesInfo",
    "AndroidNativeLibsInfo",
    "StarlarkAndroidDexInfo",
    "StarlarkAndroidResourcesInfo",
)
load("@rules_android//rules:android_neverlink_aspect.bzl", "StarlarkAndroidNeverlinkInfo", "android_neverlink_aspect")
load("@rules_android//rules:dex_desugar_aspect.bzl", "dex_desugar_aspect")
load("@rules_java//java/common:java_info.bzl", "JavaInfo")
load("@rules_java//java/common:proguard_spec_info.bzl", "ProguardSpecInfo")
load("//godot/engine/private:generator.bzl", "GodotEngineVersionInfo")
load("//godot/engine/private:resolution.bzl", "RUNTIME_TOOLCHAIN_TYPE", "engine_toolchain")
load(":manifest_graph.bzl", "ManifestGraphInfo", "manifest_graph_aspect")

visibility(["//godot/..."])

# The unstripped native libraries in a packaged ZIP or AAR, by their ABI/name ZIP path.
AndroidSymbolsInfo = provider(
    doc = "Unstripped Android native libraries of packaged extension libraries or an engine AAR.",
    fields = {"files": "Dictionary of <abi>/<name> paths to unstripped .so Files."},
)

def _engine_symbols_impl(_target, ctx):
    # godot_android_runtime's aar_import imports the engine AAR that carries a
    # source-built engine library; prebuilt engines bring no symbols or producer metadata.
    aar = getattr(ctx.rule.attr, "aar", None)
    if not aar:
        return []
    return [aar[provider] for provider in [AndroidSymbolsInfo, GodotEngineVersionInfo] if provider in aar]

engine_symbols = aspect(
    doc = "Read the unstripped engine libraries behind a godot_android_runtime.",
    implementation = _engine_symbols_impl,
)

# Applied on the runtime component's payload, before the target enters ToolchainInfo.
ANDROID_PAYLOAD_ASPECTS = [dex_desugar_aspect, android_neverlink_aspect, engine_symbols, manifest_graph_aspect]

# The supported aar_import provider contract; see the selection contract of feature 007.
_FORWARDED = [
    JavaInfo,
    StarlarkAndroidDexInfo,
    StarlarkAndroidNeverlinkInfo,
    AndroidIdeInfo,
    AndroidLibraryResourceClassJarProvider,
    AndroidNativeLibsInfo,
    StarlarkAndroidResourcesInfo,
    ProguardSpecInfo,
    OutputGroupInfo,
    AndroidCcLinkParamsInfo,
    AndroidLintRulesInfo,
    AndroidSymbolsInfo,
    ManifestGraphInfo,
]

def android_runtime_providers(target):
    """
    Return the supported rules_android providers of an aspect-enriched Android runtime payload.

    Args:
        target: The runtime payload Target from the selected runtime component.

    Returns:
        The provider instances the bridge forwards unchanged.
    """

    # Files only: a payload's executable belongs to the rule that created it.
    return [DefaultInfo(files = target[DefaultInfo].files)] + [
        target[provider]
        for provider in _FORWARDED
        if provider in target
    ]

def _bridge_impl(ctx):
    godot = engine_toolchain(ctx, "runtime", "this Android platform slice and variant")
    return android_runtime_providers(godot.payload) + [godot.provenance]

# The kind must not start with android_ and the rule must have no Android constraints, so
# rules_android's neverlink aspect keeps the replayed provider; the rule is therefore
# runtime_bridge_android, not android_runtime_bridge like its file. incremental_dexing = 0
# makes its dex aspect keep the replayed StarlarkAndroidDexInfo instead of computing a
# duplicate.
runtime_bridge_android = rule(
    doc = "Expose the Android runtime component resolved in this platform slice to rules_android packaging.",
    implementation = _bridge_impl,
    toolchains = [config_common.toolchain_type(RUNTIME_TOOLCHAIN_TYPE, mandatory = False)],
    attrs = {"incremental_dexing": attr.int(default = 0, values = [0])},
)
