"""godot_android_toolchains settles one NDK API level and registers host and Linux tools per host."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")

# buildifier: disable=bzl-visibility
load(
    "//godot/platforms/private:android_toolchains.bzl",
    "android_toolchain_declarations",
    "hub_impl",
    "linux_ndk_impl",
    "plan_android_toolchains",
)

# buildifier: disable=bzl-visibility
load("//godot/private:repository_templates.bzl", "starlark_dict")

# buildifier: disable=bzl-visibility
load("//godot/private/tests:mocks.bzl", "mocks")

_LINUX_CLANG = "toolchains/llvm/prebuilt/linux-x86_64"

# The pins the repository rules read from android_linux_toolchains.json.
_PINS = json.encode({
    "build_tools": {
        "version": "35.0.0",
        "archive": "build-tools_r35_linux.zip",
        "integrity": "sha256-build-tools",
        "strip_prefix": "android-15",
    },
    "ndk": {
        "version": "29.0.14206865",
        "archive": "android-ndk-r29-linux.zip",
        "integrity": "sha256-ndk",
        "strip_prefix": "android-ndk-r29",
    },
    "platforms": {
        "35": {"archive": "platform-35_r02.zip", "integrity": "sha256-35"},
        "36": {"archive": "platform-36_r02.zip", "integrity": "sha256-36"},
    },
})

def _module(name, *levels, is_root = False):
    return mocks.module(
        name,
        is_root = is_root,
        configure = [mocks.tag(ndk_api_level = level) for level in levels],
    )

def _plan(modules):
    errors, fail_ = mocks.errors()
    return plan_android_toolchains(modules, _fail = fail_), errors

def _test_root_tag_wins(env):
    level, errors = _plan([_module("root", 26, is_root = True), _module("a", 24), _module("b", 28)])
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_int(level).equals(26)

def _test_agreeing_dependencies_set_the_level(env):
    level, errors = _plan([_module("root", is_root = True), _module("a", 24), _module("b", 24)])
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_int(level).equals(24)

def _test_no_tags_declare_nothing(env):
    level, errors = _plan([_module("root", is_root = True), _module("a")])
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_bool(level == None).equals(True)

def _test_two_root_tags_fail(env):
    level, errors = _plan([_module("root", 24, 26, is_root = True)])
    env.expect.that_collection(errors).contains_exactly([
        "godot_android_toolchains takes at most one configure tag in the root module",
    ])
    env.expect.that_bool(level == None).equals(True)

def _test_disagreeing_dependencies_fail(env):
    level, errors = _plan([_module("root", is_root = True), _module("a", 28), _module("b", 24)])
    env.expect.that_collection(errors).contains_exactly([
        "Conflicting godot_android_toolchains.configure requests (ndk_api_level 24, 28). " +
        "Configure it in the root module.",
    ])
    env.expect.that_bool(level == None).equals(True)

def _ndk(*, tree = [_LINUX_CLANG + "/lib/clang/21/include/stddef.h"], revision = "29.0.14206865"):
    ctx = mocks.repository_ctx(
        attr = {"api_level": 26, "_pins": "pins.json"},
        name = "android_ndk_linux_x86_64",
        files = {
            "pins.json": _PINS,
            "source.properties": "Pkg.Desc = Android NDK\nPkg.Revision = %s\n" % revision,
        },
        tree = tree,
    )
    errors, fail_ = mocks.errors()
    metadata = linux_ndk_impl(ctx, _fail = fail_)
    return ctx, metadata, errors

def _test_ndk_api_level_reaches_both_ndks(env):
    declarations = android_toolchain_declarations("android_toolchains", 26)
    env.expect.that_collection([(declaration.rule, declaration.attrs) for declaration in declarations]).contains_exactly([
        ("android_ndk_repository", {"name": "android_ndk", "api_level": 26}),
        ("linux_sdk", {"name": "android_sdk_linux_x86_64"}),
        ("linux_ndk", {"name": "android_ndk_linux_x86_64", "api_level": 26}),
        ("hub", {"name": "android_toolchains"}),
    ]).in_order()

    ctx, metadata, errors = _ndk()
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_bool(metadata.reproducible).equals(True)
    download = mocks.calls(ctx, "download_and_extract")[0]
    env.expect.that_str(download.url).equals("https://dl.google.com/android/repository/android-ndk-r29-linux.zip")
    env.expect.that_str(download.stripPrefix).equals("android-ndk-r29")
    templates = {call.path: call for call in mocks.calls(ctx, "template")}
    clang = templates[_LINUX_CLANG + "/BUILD.bazel"]
    env.expect.that_str(clang.template).equals(str(Label("@rules_android_ndk//:BUILD.ndk_clang.tpl")))
    env.expect.that_dict(clang.substitutions).contains_exactly({
        "{repository_name}": Label("@rules_android_ndk//:BUILD").repo_name,
        "{api_level}": "26",
        "{clang_resource_directory}": "lib/clang/21",
        "{sysroot_directory}": _LINUX_CLANG + "/sysroot",
        "{executable_extension}": "",
    })
    env.expect.that_dict(templates[_LINUX_CLANG + "/sysroot/BUILD.bazel"].substitutions).contains_exactly(
        {"{api_level}": "26"},
    )
    env.expect.that_dict(templates["BUILD.bazel"].substitutions).contains_exactly(
        {"{clang_directory}": _LINUX_CLANG},
    )

def _test_linux_ndk_of_another_revision_fails(env):
    ctx, metadata, errors = _ndk(revision = "28.2.13676358")
    env.expect.that_collection(errors).contains_exactly([
        'android_ndk_linux_x86_64 holds revision ["28.2.13676358"], not the pinned 29.0.14206865',
    ])
    env.expect.that_bool(metadata == None).equals(True)
    env.expect.that_collection(mocks.calls(ctx, "template")).contains_exactly([])

def _test_linux_ndk_without_one_clang_resource_directory_fails(env):
    ctx, metadata, errors = _ndk(tree = [_LINUX_CLANG + "/lib/clang/20/include", _LINUX_CLANG + "/lib/clang/21/include"])
    env.expect.that_collection(errors).has_size(1)
    env.expect.that_str(errors[0]).contains(
        "expected one clang resource directory in toolchains/llvm/prebuilt/linux-x86_64, found",
    )
    env.expect.that_bool(metadata == None).equals(True)
    env.expect.that_collection(mocks.calls(ctx, "template")).contains_exactly([])

def _hub(os_name):
    ctx = mocks.repository_ctx(
        attr = {
            "_build_template": "hub.tpl",
            "_ndk_template": "ndk.tpl",
            "_api_level_template": "level.tpl",
            "_pins": "pins.json",
        },
        files = {
            "pins.json": _PINS,
            "hub.tpl": "{HOST_NDK_TOOLCHAINS}|{LINUX_NDK_TOOLCHAINS}|{SDK}|{LINUX_SDK}|{API_LEVEL_SETTINGS}\n",
            "ndk.tpl": "{NAME} {CLANG} {CONSTRAINTS}\n",
            "level.tpl": "level {LEVEL}\n",
        },
        os_name = os_name,
    )
    errors, fail_ = mocks.errors()
    hub_impl(ctx, _fail = fail_)
    return ctx, errors

def _build_file(ctx):
    return {call.path: call.content for call in mocks.calls(ctx, "file")}["BUILD.bazel"]

def _test_macos_host_registers_pinned_linux_tools(env):
    ctx, errors = _hub("mac os x")
    env.expect.that_collection(errors).contains_exactly([])
    linux_sdk = "select(\n        %s,\n        no_match_error = %r,\n    )" % (
        starlark_dict({
            ":api_level_35": "@android_sdk_linux_x86_64//:sdk-35",
            ":api_level_36": "@android_sdk_linux_x86_64//:sdk-36",
        }, indent = "        "),
        "Linux executors have the Android SDK platforms 35, 36 only. Set " +
        "--@androidsdk//:api_level to one of them or build on this host.",
    )
    env.expect.that_str(_build_file(ctx)).equals("|".join([
        "ndk @android_ndk//toolchains/llvm/prebuilt/darwin-x86_64 HOST_CONSTRAINTS",
        "ndk_linux_x86_64 @android_ndk_linux_x86_64//" + _LINUX_CLANG + " _LINUX_X86_64",
        "@android_sdk_linux_x86_64",
        linux_sdk,
        "level 35\n\nlevel 36",
    ]) + "\n")
    env.expect.that_collection([call.path for call in mocks.calls(ctx, "template")]).contains_exactly(
        ["target_systems.bzl"],
    )

def _test_linux_host_serves_linux_executors_itself(env):
    ctx, errors = _hub("linux")
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_str(_build_file(ctx)).equals("|".join([
        "ndk @android_ndk//" + _LINUX_CLANG + " HOST_CONSTRAINTS",
        "ndk_linux_x86_64 @android_ndk//" + _LINUX_CLANG + " _LINUX_X86_64",
        "@androidsdk",
        repr("@androidsdk//:sdk"),
        "level 35\n\nlevel 36",
    ]) + "\n")

def _test_unsupported_host_fails(env):
    ctx, errors = _hub("windows 11")
    env.expect.that_collection(errors).contains_exactly(["Unsupported operating system: windows 11"])
    env.expect.that_collection(ctx.calls).contains_exactly([])

def android_toolchains_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_root_tag_wins,
            _test_agreeing_dependencies_set_the_level,
            _test_no_tags_declare_nothing,
            _test_two_root_tags_fail,
            _test_disagreeing_dependencies_fail,
            _test_ndk_api_level_reaches_both_ndks,
            _test_linux_ndk_of_another_revision_fails,
            _test_linux_ndk_without_one_clang_resource_directory_fails,
            _test_macos_host_registers_pinned_linux_tools,
            _test_linux_host_serves_linux_executors_itself,
            _test_unsupported_host_fails,
        ],
    )
