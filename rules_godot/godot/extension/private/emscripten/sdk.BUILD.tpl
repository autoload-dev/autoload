load("@rules_cc//cc/toolchains:cc_toolchain.bzl", "cc_toolchain")
load({TOOLCHAIN_BZL}, "emscripten_toolchain_config")

package(default_visibility = ["//visibility:public"])

# The SDK's files that compiling, linking and archiving read, as emsdk's own Bazel
# repository groups them.
filegroup(
    name = "emcc_common",
    srcs = [
        "emscripten/cache/sysroot_install.stamp",
        "emscripten/em++.py",
        "emscripten/emcc.py",
        "emscripten/emscripten-version.txt",
        "emscripten/src/settings.js",
        "emscripten/src/settings_internal.js",
    ] + glob(
        [
            "emscripten/third_party/**",
            "emscripten/tools/**",
        ],
        exclude = ["**/__pycache__/**"],
    ),
)

filegroup(
    name = "compiler_files",
    srcs = [
        "bin/clang",
        "bin/clang++",
        ":emcc_common",
    ] + glob([
        "emscripten/cache/sysroot/include/**",
        "lib/clang/**/include/**",
    ]),
)

filegroup(
    name = "linker_files",
    srcs = [
        "bin/clang",
        "bin/llvm-ar",
        "bin/llvm-dwarfdump",
        "bin/llvm-nm",
        "bin/llvm-objcopy",
        "bin/wasm-ctor-eval",
        "bin/wasm-emscripten-finalize",
        "bin/wasm-ld",
        "bin/wasm-metadce",
        "bin/wasm-opt",
        "bin/wasm-split",
        "bin/wasm2js",
        ":emcc_common",
    ] + glob([
        "emscripten/cache/sysroot/lib/**",
        "emscripten/node_modules/**",
        "emscripten/src/**",
    ]),
)

filegroup(
    name = "ar_files",
    srcs = [
        "bin/llvm-ar",
        "emscripten/emar.py",
        "emscripten/emscripten-version.txt",
        "emscripten/src/settings.js",
        "emscripten/src/settings_internal.js",
    ] + glob(
        ["emscripten/tools/**"],
        exclude = ["**/__pycache__/**"],
    ),
)

filegroup(
    name = "toolchain_files",
    srcs = [
        "em++.sh",
        "emar.sh",
        "emcc.sh",
        "emscripten_config",
        ":ar_files",
        ":compiler_files",
        ":linker_files",
        ":start_file_sources",
        {PYTHON},
    ],
)

# The source of a threaded side module's start file and the headers it includes, which
# @autoload_rules_godot//godot/extension/private/emscripten:start_files compiles.
filegroup(
    name = "start_file_sources",
    srcs = glob([
        "emscripten/system/lib/libc/*.h",
        "emscripten/system/lib/libc/musl/arch/**",
        "emscripten/system/lib/libc/musl/include/**",
        "emscripten/system/lib/libc/musl/src/include/**",
        "emscripten/system/lib/libc/musl/src/internal/**",
        "emscripten/system/lib/pthread/**",
    ]),
)

filegroup(name = "empty")

[
    [
        emscripten_toolchain_config(
            name = "config_" + kind,
            clang_major = {CLANG_MAJOR},
            sdk_root = {SDK_ROOT},
            threads = kind == "threads",
            version = {VERSION},
        ),
        cc_toolchain(
            name = "cc_toolchain_" + kind,
            all_files = ":toolchain_files",
            ar_files = ":toolchain_files",
            as_files = ":toolchain_files",
            compiler_files = ":toolchain_files",
            dwp_files = ":empty",
            linker_files = ":toolchain_files",
            objcopy_files = ":empty",
            strip_files = ":empty",
            toolchain_config = ":config_" + kind,
        ),
    ]
    for kind in [
        "nothreads",
        "threads",
    ]
]
