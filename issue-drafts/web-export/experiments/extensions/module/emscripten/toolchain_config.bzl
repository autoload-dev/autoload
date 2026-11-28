"""A minimal Emscripten cc_toolchain config that links side modules."""

load("@bazel_tools//tools/build_defs/cc:action_names.bzl", "ACTION_NAMES")
load(
    "@rules_cc//cc:cc_toolchain_config_lib.bzl",
    "env_entry",
    "env_set",
    "feature",
    "flag_group",
    "flag_set",
    "tool_path",
)
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/toolchains:cc_toolchain_config_info.bzl", "CcToolchainConfigInfo")

_PY = "@rules_python//python:exec_tools_toolchain_type"

_COMPILE = [
    ACTION_NAMES.c_compile,
    ACTION_NAMES.cpp_compile,
    ACTION_NAMES.cpp_header_parsing,
    ACTION_NAMES.assemble,
    ACTION_NAMES.preprocess_assemble,
]
_LINK = [
    ACTION_NAMES.cpp_link_executable,
    ACTION_NAMES.cpp_link_dynamic_library,
    ACTION_NAMES.cpp_link_nodeps_dynamic_library,
]
_ALL = _COMPILE + _LINK + [ACTION_NAMES.cpp_link_static_library]

def _python(ctx):
    return ctx.toolchains[_PY].exec_tools.exec_interpreter[platform_common.ToolchainInfo].py3_runtime

def _impl(ctx):
    sdk = ctx.attr.sdk_root
    python = _python(ctx)
    features = [
        feature(name = "supports_pic", enabled = True),
        feature(name = "supports_dynamic_linker", enabled = True),
        feature(name = "no_legacy_features_marker"),
        # The engine's ABI, on every compile and link of the configuration: godot-cpp's
        # tools/web.py builds every object as side-module code with wasm longjmp.
        feature(
            name = "godot_web_abi",
            enabled = True,
            flag_sets = [
                flag_set(
                    actions = _COMPILE,
                    flag_groups = [flag_group(flags = [
                        "-sSIDE_MODULE=1",
                        "-sSUPPORT_LONGJMP=wasm",
                        "-fno-exceptions",
                        # Keep clang's resource directory relative to the invoked path.
                        "-no-canonical-prefixes",
                    ])],
                ),
                flag_set(
                    actions = [ACTION_NAMES.cpp_link_dynamic_library, ACTION_NAMES.cpp_link_nodeps_dynamic_library],
                    flag_groups = [flag_group(flags = [
                        "-sSIDE_MODULE=1",
                        "-sWASM_BIGINT",
                        "-sSUPPORT_LONGJMP=wasm",
                    ])],
                ),
            ],
        ),
        # Threads change the ABI: in the ruleset a constraint of the export platform.
        feature(
            name = "use_pthreads",
            flag_sets = [flag_set(actions = _COMPILE + _LINK, flag_groups = [flag_group(flags = ["-pthread"])])],
        ),
        feature(
            name = "emscripten_env",
            enabled = True,
            env_sets = [env_set(
                actions = _ALL,
                env_entries = [env_entry(key = "EMSDK_PYTHON", value = python.interpreter.path)],
            )],
        ),
        feature(name = "opt"),
        feature(name = "dbg"),
        feature(name = "fastbuild"),
    ]
    return cc_common.create_cc_toolchain_config_info(
        ctx = ctx,
        features = features,
        cxx_builtin_include_directories = [
            sdk + "/emscripten/cache/sysroot/include",
            sdk + "/lib/clang/%s/include" % ctx.attr.clang_major,
        ],
        toolchain_identifier = "emscripten-" + ctx.attr.version,
        host_system_name = "local",
        target_system_name = "wasm32-unknown-emscripten",
        target_cpu = "wasm32",
        target_libc = "musl",
        compiler = "emscripten",
        abi_version = "emscripten-" + ctx.attr.version,
        abi_libc_version = "musl",
        tool_paths = [
            tool_path(name = "gcc", path = "emcc.sh"),
            tool_path(name = "ld", path = "emcc.sh"),
            tool_path(name = "ar", path = "emar.sh"),
            tool_path(name = "cpp", path = "/bin/false"),
            tool_path(name = "gcov", path = "/bin/false"),
            tool_path(name = "nm", path = "/bin/false"),
            tool_path(name = "objdump", path = "/bin/false"),
            tool_path(name = "strip", path = "/bin/false"),
        ],
    )

emscripten_toolchain_config = rule(
    implementation = _impl,
    attrs = {
        "version": attr.string(mandatory = True),
        "sdk_root": attr.string(mandatory = True),
        "clang_major": attr.string(mandatory = True),
    },
    provides = [CcToolchainConfigInfo],
    toolchains = [_PY],
)

python_interpreter_files = rule(
    implementation = lambda ctx: DefaultInfo(files = _python(ctx).files),
    toolchains = [_PY],
)
