"""
godot_android_toolchains serves a Linux execution platform with Linux SDK and NDK tools.

The probe is an Android target analyzed for BuildBuddy's linux/x86_64 execution platform.
Its toolchains come from the pinned Linux SDK and NDK on hosts other than Linux and from this
host's SDK and NDK on a Linux host. The hub's aapt, configured as a test's runfiles are, is the
same Linux SDK's for a test on Linux, as --config=buildbuddy-linux runs it, and this host's for
a test on this host.
"""

load("@platforms//host:constraints.bzl", "HOST_CONSTRAINTS")
load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("//godot/private/tests:toolchains.bzl", "own_toolchains")

_SDK = "@rules_android//toolchains/android_sdk:toolchain_type"
_ANDROID = "@rules_android//toolchains/android:toolchain_type"
_CC = "@bazel_tools//tools/cpp:toolchain_type"

_Info = provider(
    doc = "Repository names of the tools the probe's toolchains resolve.",
    fields = ["android_jar", "aapt2", "compiler"],
)

def _repository(path):
    return path.partition("external/")[2].partition("/")[0]

def _probe_impl(ctx):
    aapt2 = ctx.toolchains[_ANDROID].aapt2[DefaultInfo].files_to_run.executable
    return [_Info(
        android_jar = _repository(ctx.toolchains[_SDK].android_sdk_info.android_jar.path),
        aapt2 = _repository(aapt2.path),
        compiler = _repository(ctx.toolchains[_CC].cc.compiler_executable),
    )]

resolution_probe = rule(
    doc = "Report the SDK, Android and C++ toolchains of a Linux execution platform.",
    implementation = _probe_impl,
    exec_compatible_with = ["@platforms//os:linux", "@platforms//cpu:x86_64"],
    toolchains = [_SDK, _ANDROID, _CC],
)

_LINUX_HOST = "@platforms//os:linux" in HOST_CONSTRAINTS
_LINUX_SDK = "androidsdk" if _LINUX_HOST else "android_sdk_linux_x86_64"

# The tests need an installed SDK; see resolution_test_suite.
_ATTRS = {
    "size": "small",
    "target_compatible_with": [Label(":requires_android_sdk")],
}

def _linux_executor_uses_linux_android_tools_impl(env, target):
    info = target[_Info]
    sdk = _LINUX_SDK
    ndk = "android_ndk" if _LINUX_HOST else "android_ndk_linux_x86_64"
    env.expect.that_bool(info.android_jar.endswith("+" + sdk), "SDK: " + info.android_jar).equals(True)
    env.expect.that_bool(info.aapt2.endswith("+" + sdk), "aapt2: " + info.aapt2).equals(True)
    env.expect.that_bool(info.compiler.endswith("+" + ndk), "NDK: " + info.compiler).equals(True)

def _test_linux_executor_uses_linux_android_tools(name, **kwargs):
    analysis_test(
        name = name,
        target = ":probe",
        impl = _linux_executor_uses_linux_android_tools_impl,
        # BuildBuddy's C++ toolchain builds the probe's Linux tools, as with --config=buildbuddy;
        # resolution for that executor is the subject, so the test registers both on the
        # command line.
        config_settings = {
            "//command_line_option:platforms": str(Label("//godot/platforms:android_arm64")),
            str(Label("@androidsdk//:api_level")): "35",
        } | own_toolchains(
            [
                "@android_toolchains//:all",
                "@toolchains_buildbuddy//toolchains/cc:ubuntu_gcc_x86_64",
            ],
            ["@toolchains_buildbuddy//platforms:linux_x86_64"],
        ),
        **kwargs
    )

def _tool_of(sdk):
    def impl(env, target):
        tool = _repository(target[DefaultInfo].files_to_run.executable.path)
        env.expect.that_bool(tool.endswith("+" + sdk), "tool: " + tool).equals(True)

    return impl

def _test_tool_test(name, tool, platform, sdk):
    analysis_test(
        name = name,
        target = "@android_toolchains//:" + tool,
        impl = _tool_of(sdk),
        config_settings = {"//command_line_option:platforms": str(Label(platform))},
        attr_values = _ATTRS,
    )

def resolution_test_suite(name):
    """
    Declare the resolution tests and a suite of them.

    The tests need an Android SDK and NDK: they are compatible only where rules_android found
    an installed SDK, and on hosts other than Linux they download the Linux SDK and NDK.

    Args:
        name: Name of the suite.
    """
    _test_linux_executor_uses_linux_android_tools(
        name = "test_linux_executor_uses_linux_android_tools",
        attr_values = _ATTRS,
    )
    for tool in ["aapt", "aapt2"]:
        _test_tool_test(
            name = "test_linux_test_runs_linux_" + tool,
            tool = tool,
            platform = "//godot/platforms:linux_x86_64",
            sdk = _LINUX_SDK,
        )
        _test_tool_test(
            name = "test_host_test_runs_host_" + tool,
            tool = tool,
            platform = "@platforms//host",
            sdk = "androidsdk",
        )
    native.test_suite(
        name = name,
        tests = [
            ":test_linux_executor_uses_linux_android_tools",
            ":test_linux_test_runs_linux_aapt",
            ":test_host_test_runs_host_aapt",
            ":test_linux_test_runs_linux_aapt2",
            ":test_host_test_runs_host_aapt2",
        ],
    )
