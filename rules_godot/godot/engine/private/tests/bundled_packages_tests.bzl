"""
The engine targets of an official engine carry the package metadata of Godot's bundled libraries.

Each library of the COPYRIGHT.txt the catalogue pins is a target of its own that carries its
package metadata, which the engine's targets depend on, so SBOM tools reach it beside
Godot's metadata.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")

visibility("private")

_PackageMetadataLabelsInfo = provider(
    doc = "The labels of the package metadata a target and its bundled packages carry.",
    fields = {"labels": "A depset of label strings."},
)

def _package_metadata_labels_impl(_target, ctx):
    own = [str(metadata.label) for metadata in getattr(ctx.rule.attr, "package_metadata", [])]
    reached = [
        dependency[_PackageMetadataLabelsInfo].labels
        for name in ["bundled_packages", "srcs"]
        for dependency in getattr(ctx.rule.attr, name, None) or []
        if _PackageMetadataLabelsInfo in dependency
    ]
    return [_PackageMetadataLabelsInfo(labels = depset(own, transitive = reached))]

_package_metadata_labels = aspect(
    implementation = _package_metadata_labels_impl,
    attr_aspects = ["bundled_packages", "srcs"],
)

def _test_the_editor_carries_the_bundled_libraries(name):
    analysis_test(
        name = name,
        # The editor of Godot's official 4.7.2, which MODULE.bazel registers.
        target = "@godot_editor_linux_x86_64//:editor",
        impl = _the_editor_carries_the_bundled_libraries,
        extra_target_under_test_aspects = [_package_metadata_labels],
    )

def _the_editor_carries_the_bundled_libraries(env, target):
    labels = target[_PackageMetadataLabelsInfo].labels.to_list()
    repository = target.label.repo_name
    env.expect.that_collection(labels).contains_at_least([
        "@@%s//_package_metadata:%s" % (repository, name)
        for name in [
            # Godot's own, then libraries of thirdparty/ and of Godot's modules.
            "package_metadata",
            "zlib_metadata",
            "the_freetype_project_metadata",
            "bullet_continuous_collision_detection_and_physics_library_metadata",
        ]
    ])

    # Godot 4.7.2's COPYRIGHT.txt names 102 libraries besides Godot itself.
    env.expect.that_collection(labels).has_size(103)

def bundled_packages_test_suite(name):
    test_suite(
        name = name,
        tests = [_test_the_editor_carries_the_bundled_libraries],
    )
