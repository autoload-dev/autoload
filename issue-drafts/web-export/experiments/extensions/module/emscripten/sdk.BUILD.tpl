load("@@{CONFIG_BZL_REPO}//emscripten:toolchain_config.bzl", "emscripten_toolchain_config")
load("@rules_cc//cc:defs.bzl", "cc_toolchain")

package(default_visibility = ["//visibility:public"])

# Emscripten {VERSION} for {EXEC}: the filegroups of emsdk's build file template.
{EMSDK_FILEGROUPS}

filegroup(
    name = "toolchain_files",
    srcs = [
        "emar.sh",
        "emcc.sh",
        "emscripten_config",
        ":all_sdk_files",
        "@@{CONFIG_BZL_REPO}//emscripten:python",
    ],
)

filegroup(
    name = "all_sdk_files",
    srcs = [
        ":ar_files",
        ":compiler_files",
        ":linker_files",
    ],
)

filegroup(name = "empty")

emscripten_toolchain_config(
    name = "config",
    clang_major = "{CLANG_MAJOR}",
    sdk_root = "{SDK_ROOT}",
    version = "{VERSION}",
)

cc_toolchain(
    name = "cc_toolchain",
    all_files = ":toolchain_files",
    ar_files = ":toolchain_files",
    as_files = ":toolchain_files",
    compiler_files = ":toolchain_files",
    dwp_files = ":empty",
    linker_files = ":toolchain_files",
    objcopy_files = ":empty",
    strip_files = ":empty",
    toolchain_config = ":config",
)
