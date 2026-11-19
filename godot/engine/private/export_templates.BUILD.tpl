load({PREBUILT_BZL}, "prebuilt_runtime")
{APPLE_LOAD}

package(default_visibility = ["//visibility:public"])

filegroup(
    name = "files",
    srcs = glob(
        [
            "templates/**",
            "macos/**",
        ],
        allow_empty = True,
    ),
)

filegroup(
    name = "macos_files",
    srcs = glob(
        ["macos/**"],
        allow_empty = True,
    ),
)
{RUNTIMES}{IOS}
exports_files(glob(["templates/*"]))
