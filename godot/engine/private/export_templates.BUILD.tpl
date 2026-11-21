load({PREBUILT_BZL}, "prebuilt_runtime")
{APPLE_LOAD}

package(default_visibility = ["//visibility:public"])

filegroup(
    name = "macos_files",
    srcs = glob(
        ["macos/**"],
        allow_empty = True,
    ),
)
{TARGETS}
