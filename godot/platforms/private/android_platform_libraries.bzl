"""The platform libraries of Godot Android applications and the order of their manifests."""

load(
    "@rules_android//providers:providers.bzl",
    "AndroidLibraryResourceClassJarProvider",
    "AndroidNativeLibsInfo",
    "StarlarkAndroidResourcesInfo",
)
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("@rules_cc//cc/common:objc_info.bzl", "ObjcInfo")
load("@rules_java//java/common:java_common.bzl", "java_common")
load("@rules_java//java/common:java_info.bzl", "JavaInfo")
load("@rules_java//java/common:proguard_spec_info.bzl", "ProguardSpecInfo")
load("//godot:providers.bzl", "GodotPackInfo")
load("//godot/platforms/private:manifest_graph.bzl", "manifest_graph_aspect", "ranked_resources_nodes")

visibility("private")

# The depset fields of StarlarkAndroidResourcesInfo; packages_to_r_txts and package are
# its others.
_RESOURCE_DEPSET_FIELDS = [
    "direct_resources_nodes",
    "transitive_resources_nodes",
    "transitive_assets",
    "transitive_assets_symbols",
    "transitive_compiled_assets",
    "direct_compiled_resources",
    "transitive_compiled_resources",
    "transitive_compiled_resources_with_public_xml",
    "transitive_manifests",
    "transitive_r_txts",
    "transitive_resource_files",
    "transitive_resource_apks",
]

def _resources_info(depsets, packages_to_r_txts = {}):
    """StarlarkAndroidResourcesInfo of no package, with every depset field given."""
    return StarlarkAndroidResourcesInfo(packages_to_r_txts = packages_to_r_txts, package = "", **depsets)

def _merge_resources(infos):
    """Combine Android resource providers as android_binary does for its deps."""
    packages = {}
    for info in infos:
        for package, r_txts in info.packages_to_r_txts.items():
            packages.setdefault(package, []).append(r_txts)
    return _resources_info(
        {
            field: depset(transitive = [getattr(info, field) for info in infos])
            for field in _RESOURCE_DEPSET_FIELDS
        },
        packages_to_r_txts = {
            package: depset(transitive = r_txts)
            for package, r_txts in packages.items()
        },
    )

def _merge_field(info_type, field):
    """A merge of instances of a provider whose only field is a depset."""
    return lambda infos: info_type(**{
        field: depset(transitive = [getattr(info, field) for info in infos]),
    })

# The providers android_binary reads from its direct deps only, with their merge, in the
# order the platform libraries' target returns them; its dexing and neverlink aspects
# reach the libraries themselves through deps.
_PLATFORM_LIBRARY_MERGES = [
    (JavaInfo, java_common.merge),
    (StarlarkAndroidResourcesInfo, _merge_resources),
    (AndroidLibraryResourceClassJarProvider, _merge_field(AndroidLibraryResourceClassJarProvider, "jars")),
    (AndroidNativeLibsInfo, _merge_field(AndroidNativeLibsInfo, "native_libs")),
    (ProguardSpecInfo, _merge_field(ProguardSpecInfo, "specs")),
]

def _android_platform_libraries_impl(ctx):
    libraries = ctx.attr.deps[0][GodotPackInfo].project.platform_libraries
    providers = [cc_common.merge_cc_infos(cc_infos = [
        target[CcInfo]
        for target in libraries
        if CcInfo in target
    ])]
    for provider, merge in _PLATFORM_LIBRARY_MERGES:
        infos = [target[provider] for target in libraries if provider in target]
        if infos:
            providers.append(merge(infos))
    return providers

godot_android_platform_libraries = rule(
    implementation = _android_platform_libraries_impl,
    attrs = {
        "deps": attr.label_list(
            doc = """
            The application's pack. Named deps so rules_android's aspects follow it to
            the platform libraries of the pack's project.
            """,
            mandatory = True,
            providers = [GodotPackInfo],
        ),
    },
)

def _is_android_library(target):
    """Whether a platform library is an Android Java or native library."""
    if ObjcInfo in target:
        return False
    return JavaInfo in target or CcInfo in target

def _android_manifest_order_impl(ctx):
    libraries = ctx.attr.pack[GodotPackInfo].project.platform_libraries + ctx.attr.application_deps
    for target in libraries:
        if not _is_android_library(target):
            fail("Android platform_deps does not support input %s; expected Android Java/native libraries" % target.label)

    # Only the order of the direct resource nodes: android_binary merges the library
    # manifests of its deps' nodes in their order, the first of each node counting.
    nodes = depset(ranked_resources_nodes(ctx.attr.leading + libraries), order = "preorder")
    return [CcInfo(), _resources_info(
        {field: depset() for field in _RESOURCE_DEPSET_FIELDS} | {"direct_resources_nodes": nodes},
    )]

godot_android_manifest_order = rule(
    doc = """
    The manifest priority of an Android application's libraries, as a Gradle build has it.

    Godot's Gradle template declares the activity's androidx libraries, then the Godot
    library, then the plugins' dependencies; the Android Gradle plugin ranks these in that
    order, then their dependencies breadth-first. As android_binary's first dep, this target
    sets the order in which rules_android merges the library manifests.
    """,
    implementation = _android_manifest_order_impl,
    attrs = {
        "leading": attr.label_list(
            doc = "The template activity's libraries, then the Android runtime.",
            aspects = [manifest_graph_aspect],
        ),
        "pack": attr.label(
            doc = "The application's pack, whose platform libraries come next.",
            mandatory = True,
            providers = [GodotPackInfo],
        ),
        "application_deps": attr.label_list(
            doc = "The application's own platform libraries, which come last.",
            aspects = [manifest_graph_aspect],
        ),
    },
)
