"""
The libraries a Godot COPYRIGHT.txt lists, which godot_bundled_packages declares once and
the engine targets carry.

Each library is a target of its own that carries its package metadata. The engine's
targets depend on the repository's :bundled_packages, so SBOM tools reach every library
beside Godot's metadata.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/engine/private:bundled_packages.bzl", "bundled_packages_impl")
load("//godot/private/tests:copyright_excerpt.bzl", "COPYRIGHT_EXCERPT")
load("//godot/private/tests:mocks.bzl", "mocks")

visibility("private")

_PackageMetadataLabelsInfo = provider(
    doc = "The labels of the package metadata a target and its bundled packages carry.",
    fields = {"labels": "A depset of label strings."},
)

_TREE = Label("//godot/engine/private/tests:tree.json")

def _repository(files = {}, **attr):
    ctx = mocks.repository_ctx(
        attr = {"name": "godot_bundled_packages", "urls": [], "sha256": "", "tree": None} | attr,
        files = files,
        tree = [],
    )
    errors, fail_ = mocks.errors()
    bundled_packages_impl(ctx, _fail = fail_)
    return ctx, errors

def _written(ctx):
    return sorted([call.path for call in mocks.calls(ctx, "file")])

# The repository of an engine tree reads the COPYRIGHT.txt beside the tree's descriptor.
def _test_a_trees_libraries_come_from_its_copyright(env):
    copyright = mocks.path(_TREE).dirname + "/COPYRIGHT.txt"
    ctx, errors = _repository(files = {copyright: COPYRIGHT_EXCERPT}, tree = _TREE)
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(_written(ctx)).contains_at_least(["BUILD.bazel", "zlib.txt"])

# The repository of a catalogued release downloads the file the catalogue pins.
def _test_a_releases_libraries_come_from_the_pinned_file(env):
    ctx, errors = _repository(
        files = {"COPYRIGHT.txt": COPYRIGHT_EXCERPT},
        urls = ["https://example.com/COPYRIGHT.txt"],
        sha256 = "cb" * 32,
    )
    env.expect.that_collection(errors).contains_exactly([])
    downloads = mocks.calls(ctx, "download")
    env.expect.that_collection(downloads).has_size(1)
    env.expect.that_str(downloads[0].sha256).equals("cb" * 32)
    env.expect.that_collection(_written(ctx)).contains_at_least(["BUILD.bazel", "zlib.txt"])

def _test_exactly_one_source_is_required(env):
    for attr in [{}, {"urls": ["https://example.com/COPYRIGHT.txt"], "tree": _TREE}]:
        ctx, errors = _repository(**attr)
        env.expect.where(attr = attr).that_collection(errors).contains_exactly([
            "godot_bundled_packages: set exactly one of urls and tree",
        ])
        env.expect.where(attr = attr).that_collection(_written(ctx)).contains_exactly([])

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
        # The host's editor of Godot's official 4.7.2, which MODULE.bazel registers and
        # the host's builds fetch anyway.
        target = select({
            "@platforms//os:macos": "@godot_editor_macos//:editor",
            "//conditions:default": "@godot_editor_linux_x86_64//:editor",
        }),
        impl = _the_editor_carries_the_bundled_libraries,
        extra_target_under_test_aspects = [_package_metadata_labels],
    )

def _the_editor_carries_the_bundled_libraries(env, target):
    labels = target[_PackageMetadataLabelsInfo].labels.to_list()
    env.expect.that_collection(labels).contains("@@%s//_package_metadata:package_metadata" % target.label.repo_name)

    # The libraries, of thirdparty/ and of Godot's modules, are the release's repository's.
    names = [label.rpartition(":")[2] for label in labels if "godot_release_packages_" in label]
    env.expect.that_collection(names).contains_at_least([
        "zlib.metadata",
        "the_freetype_project.metadata",
        "bullet_continuous_collision_detection_and_physics_library.metadata",
    ])

    # Godot 4.7.2's COPYRIGHT.txt names 102 libraries besides Godot itself.
    env.expect.that_collection(labels).has_size(103)

def bundled_packages_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_a_trees_libraries_come_from_its_copyright,
            _test_a_releases_libraries_come_from_the_pinned_file,
            _test_exactly_one_source_is_required,
        ],
        tests = [_test_the_editor_carries_the_bundled_libraries],
    )
