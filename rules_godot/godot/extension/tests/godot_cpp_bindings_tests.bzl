"""godot_cpp_bindings fetches godot-cpp and declares the bindings of one API selection."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/extension/private:godot_cpp.bzl", "GODOT_CPP_COMMIT", "GODOT_CPP_SHA256", "godot_cpp_bindings_impl")
load("//godot/private:repository_templates.bzl", "starlark_list")
load("//godot/private/tests:mocks.bzl", "mocks")

visibility("private")

_API_PATH = "gdextension/extension_api-4-7.json"
_PATCH = "/usr/bin/patch"

def _api(major = 4, minor = 7):
    classes = {
        "Object": "",
        "RefCounted": "Object",
        "Resource": "RefCounted",
        "Image": "Resource",
        "FileAccess": "RefCounted",
        "XMLParser": "RefCounted",
        "ClassDB": "Object",
        "OS": "Object",
        "WorkerThreadPool": "Object",
        "Node": "Object",
        "CanvasItem": "Node",
        "Node2D": "CanvasItem",
        "Sprite2D": "Node2D",
        "Node3D": "Node",
        "Camera3D": "Node3D",
    }
    return json.encode({
        "header": {"version_major": major, "version_minor": minor},
        "builtin_classes": [{"name": "int"}, {"name": "Vector2"}, {"name": "String"}],
        "classes": [
            {"name": name, "inherits": parent} if parent else {"name": name}
            for name, parent in classes.items()
        ],
        "native_structures": [{"name": "ObjectID"}, {"name": "AudioFrame"}],
    })

def _bindings(*, api = None, api_path = _API_PATH, execute = {}, **overrides):
    ctx = mocks.repository_ctx(
        attr = {
            "version": GODOT_CPP_COMMIT,
            "urls": ["https://codeload.github.com/godotengine/godot-cpp/tar.gz/{version}"],
            "sha256": GODOT_CPP_SHA256,
            "strip_prefix": "godot-cpp-{version}",
            "patches": [],
            "patch_strip": 1,
            "api_path": api_path,
            "enabled_classes": [],
            "bits": "64",
            "precision": "single",
            "debug_features": True,
            "_defs": "@@//godot/extension/private:bindings.bzl",
            "_cc_library": "@@rules_cc+//cc:cc_library.bzl",
            "_windows_constraint": "@@platforms//os:windows",
            "_build_template": "godot_cpp.BUILD.tpl",
        } | overrides,
        files = {api_path: api or _api(), "LICENSE.md": "Copyright (c) godot-cpp contributors."},
        path = lambda value: mocks.path(value) if str(value) == "LICENSE.md" else str(value),
        which = {"patch": _PATCH},
        execute = execute,
    )
    errors, fail_ = mocks.errors()
    godot_cpp_bindings_impl(ctx, _fail = fail_)
    return ctx, errors

def _substitutions(ctx):
    templates = mocks.calls(ctx, "template")
    return templates[0].substitutions if templates else None

def _class_outputs(ctx):
    """The class names whose header the bindings declare, as snake-case file names."""
    outs = _substitutions(ctx)["{OUTS}"]
    prefix = '"gen/include/godot_cpp/classes/'
    return sorted([
        line.strip().removeprefix(prefix).removesuffix('.hpp",')
        for line in outs.split("\n")
        if line.strip().startswith(prefix)
    ])

_GLOBAL_HEADERS = ["global_constants", "global_constants_binds", "audio_frame"]

def _test_api_path_selects_the_api(env):
    ctx, errors = _bindings(api_path = "gdextension/extension_api-4-8.json", api = _api(minor = 8))
    env.expect.that_collection(errors).contains_exactly([])
    downloads = mocks.calls(ctx, "download_and_extract")
    env.expect.that_collection(downloads).has_size(1)
    env.expect.that_dict({
        "url": downloads[0].url,
        "sha256": downloads[0].sha256,
        "stripPrefix": downloads[0].stripPrefix,
        "type": downloads[0].type,
    }).contains_exactly({
        "url": ["https://codeload.github.com/godotengine/godot-cpp/tar.gz/" + GODOT_CPP_COMMIT],
        "sha256": GODOT_CPP_SHA256,
        "stripPrefix": "godot-cpp-" + GODOT_CPP_COMMIT,
        "type": "tar.gz",
    })
    templates = mocks.calls(ctx, "template")
    env.expect.that_str(templates[0].path).equals("BUILD.bazel")
    env.expect.that_str(templates[0].template).equals("godot_cpp.BUILD.tpl")
    substitutions = _substitutions(ctx)
    env.expect.that_str(substitutions["{API}"]).equals(repr("gdextension/extension_api-4-8.json"))
    env.expect.that_str(substitutions["{BINDINGS_BZL}"]).equals(repr("@@//godot/extension/private:bindings.bzl"))
    env.expect.that_str(substitutions["{CC_LIBRARY_BZL}"]).equals(repr("@@rules_cc+//cc:cc_library.bzl"))
    env.expect.that_str(substitutions["{WINDOWS}"]).equals(repr("@@platforms//os:windows"))
    env.expect.that_str(substitutions["{OUTS}"]).contains('"gen/include/godot_cpp/variant/string.hpp",')
    env.expect.that_str(substitutions["{OUTS}"]).contains('"gen/src/variant/string.cpp",')
    for builtin in ["int", "vector2"]:
        env.expect.where(builtin = builtin).that_bool("variant/%s.hpp" % builtin in substitutions["{OUTS}"]).equals(False)

def _test_version_names_archive_and_package(env):
    ctx, errors = _bindings(version = "10.1.0-stable", sha256 = "ab" * 32)
    env.expect.that_collection(errors).contains_exactly([])
    download = mocks.calls(ctx, "download_and_extract")[0]
    env.expect.that_collection(download.url).contains_exactly([
        "https://codeload.github.com/godotengine/godot-cpp/tar.gz/10.1.0-stable",
    ])
    env.expect.that_str(download.stripPrefix).equals("godot-cpp-10.1.0-stable")
    metadata = [
        call
        for call in mocks.calls(ctx, "file")
        if call.path == "_package_metadata/BUILD.bazel"
    ]
    env.expect.that_str(metadata[0].content).contains(
        repr("pkg:generic/godot-cpp@10.1.0-stable?checksum=sha256:" + "ab" * 32),
    )

def _test_url_without_version_fails(env):
    url = "https://example.com/godot-cpp.tar.gz"
    ctx, errors = _bindings(urls = [url])
    env.expect.that_collection(errors).contains_exactly([
        "godot_cpp_bindings: the URL %s does not name {version}" % url,
    ])
    downloads = mocks.calls(ctx, "download_and_extract")
    env.expect.that_collection(downloads).contains_exactly([])

def _test_bits_and_precision_reach_the_bindings(env):
    ctx, errors = _bindings(bits = "32", precision = "double")
    env.expect.that_collection(errors).contains_exactly([])
    substitutions = _substitutions(ctx)
    env.expect.that_str(substitutions["{BITS}"]).equals(repr("32"))
    env.expect.that_str(substitutions["{PRECISION}"]).equals(repr("double"))
    env.expect.that_str(substitutions["{DEFINES}"]).equals(starlark_list([
        "GDEXTENSION",
        "THREADS_ENABLED",
        "REAL_T_IS_DOUBLE",
        "DEBUG_ENABLED",
        "HOT_RELOAD_ENABLED",
    ], indent = "    "))

def _test_debug_features_define_debug_macros(env):
    for debug_features, defines in [
        (True, ["GDEXTENSION", "THREADS_ENABLED", "DEBUG_ENABLED", "HOT_RELOAD_ENABLED"]),
        (False, ["GDEXTENSION", "THREADS_ENABLED"]),
    ]:
        ctx, errors = _bindings(debug_features = debug_features)
        env.expect.where(debug_features = debug_features).that_collection(errors).contains_exactly([])
        env.expect.where(debug_features = debug_features).that_str(_substitutions(ctx)["{DEFINES}"]).equals(
            starlark_list(defines, indent = "    "),
        )

def _test_enabled_classes_keep_ancestors(env):
    ctx, errors = _bindings(enabled_classes = ["Sprite2D"])
    env.expect.that_collection(errors).contains_exactly([])
    files = {call.path: call.content for call in mocks.calls(ctx, "file")}
    env.expect.that_dict(json.decode(files["rules_godot_profile.json"])).contains_exactly(
        {"enabled_classes": ["Sprite2D", "OS"]},
    )
    substitutions = _substitutions(ctx)
    env.expect.that_str(substitutions["{PROFILE}"]).equals(repr("rules_godot_profile.json"))
    env.expect.that_str(substitutions["{PROFILE_GENERATOR}"]).equals(repr("build_profile.py"))
    env.expect.that_collection(_class_outputs(ctx)).contains_exactly(sorted(_GLOBAL_HEADERS + [
        # Sprite2D and its ancestors.
        "sprite2d",
        "node2d",
        "canvas_item",
        "node",
        "object",
        # The classes the build profile always keeps, and their ancestors.
        "worker_thread_pool",
        "class_db_singleton",
        "file_access",
        "image",
        "resource",
        "ref_counted",
        "xml_parser",
        "os",
    ]))

def _test_no_enabled_classes_generate_every_class(env):
    ctx, errors = _bindings()
    env.expect.that_collection(errors).contains_exactly([])

    # No build profile; the repository writes only its package metadata.
    env.expect.that_collection([call.path for call in mocks.calls(ctx, "file")]).contains_exactly([
        "REPO.bazel",
        "_package_metadata/LICENSE",
        "_package_metadata/BUILD.bazel",
    ])
    substitutions = _substitutions(ctx)
    env.expect.that_str(substitutions["{PROFILE}"]).equals("None")
    env.expect.that_str(substitutions["{PROFILE_GENERATOR}"]).equals("None")
    env.expect.that_collection(_class_outputs(ctx)).contains_at_least(["camera3d", "node3d", "sprite2d"])

def _test_unknown_enabled_class_fails(env):
    ctx, errors = _bindings(enabled_classes = ["Node", "Spriteish"])
    env.expect.that_collection(errors).contains_exactly(["unknown enabled godot-cpp class: Spriteish"])
    env.expect.that_collection(mocks.calls(ctx, "file")).contains_exactly([])
    env.expect.that_collection(mocks.calls(ctx, "template")).contains_exactly([])

def _test_api_before_4_7_fails(env):
    for major, minor in [(4, 6), (3, 9), (5, 0)]:
        ctx, errors = _bindings(api = _api(major = major, minor = minor))
        env.expect.where(major = major, minor = minor).that_collection(errors).contains_exactly([
            "godot_cpp_bindings requires a Godot 4.7 or newer API within Godot 4",
        ])
        env.expect.where(major = major, minor = minor).that_collection(mocks.calls(ctx, "template")).contains_exactly([])

def _test_rejected_patch_stops_the_bindings(env):
    ctx, errors = _bindings(patches = ["cpp.patch"], execute = {_PATCH: {"return_code": 1}})
    env.expect.that_collection(errors).has_size(1)
    env.expect.that_str(errors[0]).contains("Error applying patch cpp.patch")
    env.expect.that_collection(mocks.calls(ctx, "template")).contains_exactly([])

def godot_cpp_bindings_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_api_path_selects_the_api,
            _test_version_names_archive_and_package,
            _test_url_without_version_fails,
            _test_bits_and_precision_reach_the_bindings,
            _test_debug_features_define_debug_macros,
            _test_enabled_classes_keep_ancestors,
            _test_no_enabled_classes_generate_every_class,
            _test_unknown_enabled_class_fails,
            _test_api_before_4_7_fails,
            _test_rejected_patch_stops_the_bindings,
        ],
    )
