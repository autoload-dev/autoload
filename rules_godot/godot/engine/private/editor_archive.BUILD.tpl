load({PREBUILT_BZL}, "prebuilt_editor")

package(default_visibility = ["//visibility:public"])

filegroup(
    name = "distribution",
    srcs = glob(
        ["**"],
        exclude = ["BUILD.bazel"],
    ),
)

filegroup(
    name = "binary",
    srcs = [{BINARY}],
)

prebuilt_editor(
    name = "editor",
    binary = {BINARY},
    bundled_packages = [{BUNDLED_PACKAGES}],
    data = [":distribution"],
    digest = {DIGEST},
)
