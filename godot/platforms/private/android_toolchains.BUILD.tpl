load("@platforms//host:constraints.bzl", "HOST_CONSTRAINTS")
load("@rules_android//toolchains/android:toolchain.bzl", "android_toolchain")
load("//:target_systems.bzl", "CPU_CONSTRAINT", "TARGET_SYSTEM_NAMES")

_LINUX_X86_64 = [
    "@platforms//os:linux",
    "@platforms//cpu:x86_64",
]

{HOST_NDK_TOOLCHAINS}

{LINUX_NDK_TOOLCHAINS}

android_toolchain(
    name = "android_linux_x86_64_aapt2",
    aapt2 = "{SDK}//:aapt2",
)

toolchain(
    name = "android_linux_x86_64",
    exec_compatible_with = _LINUX_X86_64,
    toolchain = ":android_linux_x86_64_aapt2",
    toolchain_type = "@rules_android//toolchains/android:toolchain_type",
    visibility = ["//visibility:public"],
)

alias(
    name = "sdk_linux_x86_64_api_level",
    actual = {LINUX_SDK},
)

toolchain(
    name = "sdk_linux_x86_64",
    exec_compatible_with = _LINUX_X86_64,
    toolchain = ":sdk_linux_x86_64_api_level",
    toolchain_type = "@rules_android//toolchains/android_sdk:toolchain_type",
    visibility = ["//visibility:public"],
)

config_setting(
    name = "linux_x86_64",
    constraint_values = _LINUX_X86_64,
    visibility = ["//visibility:private"],
)

# A test runs on an execution platform matching its target platform, so the SDK tools in its
# runfiles follow the configured platform: the Linux SDK's on Linux, this host's otherwise.
[
    alias(
        name = tool,
        actual = select({
            ":linux_x86_64": "{SDK}//:%s_binary" % tool,
            "//conditions:default": "@androidsdk//:%s_binary" % tool,
        }),
        visibility = ["//visibility:public"],
    )
    for tool in ["aapt", "aapt2"]
]

{API_LEVEL_SETTINGS}
