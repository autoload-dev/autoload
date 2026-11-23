[toolchain(
    name = "{NAME}_%s" % target_system_name,
    exec_compatible_with = {CONSTRAINTS},
    target_compatible_with = [
        "@platforms//os:android",
        CPU_CONSTRAINT[target_system_name],
    ],
    toolchain = "{CLANG}:cc_toolchain_%s" % target_system_name,
    toolchain_type = "@bazel_tools//tools/cpp:toolchain_type",
    visibility = ["//visibility:public"],
) for target_system_name in TARGET_SYSTEM_NAMES]
