"""
The C/C++ toolchain configuration of an Emscripten SDK repository for Godot's web extensions.

Every object compiles as side-module code with WebAssembly longjmp, as godot-cpp's own web
build does, and shared libraries link as side modules: what Godot's web templates with
GDExtension support load. With threads every compile and link takes -pthread, the ABI of the
threaded templates. Python for emcc comes from rules_python's execution toolchain.
Loaded by generated SDK repositories, so it needs public load visibility; it is not a
consumer API.
"""

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

visibility("public")

_PYTHON = "@rules_python//python:exec_tools_toolchain_type"

_COMPILE = [
    ACTION_NAMES.c_compile,
    ACTION_NAMES.cpp_compile,
    ACTION_NAMES.cpp_header_parsing,
    ACTION_NAMES.assemble,
    ACTION_NAMES.preprocess_assemble,
]

_SHARED_LINK = [ACTION_NAMES.cpp_link_dynamic_library, ACTION_NAMES.cpp_link_nodeps_dynamic_library]

_LINK = _SHARED_LINK + [ACTION_NAMES.cpp_link_executable]

def _python(ctx):
    return ctx.toolchains[_PYTHON].exec_tools.exec_interpreter[platform_common.ToolchainInfo].py3_runtime

def _flags(actions, flags):
    return flag_set(actions = actions, flag_groups = [flag_group(flags = flags)]) if flags else None

def _abi_feature(version, threads):
    threads_flags = ["-pthread"] if threads else []

    # Emscripten 6 always uses BigInt and deprecates the setting.
    bigint = ["-sWASM_BIGINT"] if version.startswith("4.") else []
    return feature(
        name = "godot_web_abi",
        enabled = True,
        flag_sets = [
            _flags(_COMPILE, [
                "-sSIDE_MODULE=1",
                "-sSUPPORT_LONGJMP=wasm",
                "-fno-exceptions",
                # A side module exports only its entry symbol, which its link names.
                "-fvisibility=hidden",
                # clang's resource directory stays relative to the invoked path.
                "-no-canonical-prefixes",
            ] + threads_flags),
            _flags(_SHARED_LINK, ["-sSIDE_MODULE=1", "-sSUPPORT_LONGJMP=wasm"] + bigint + threads_flags),
        ],
    )

def _impl(ctx):
    root = ctx.attr.sdk_root
    python = _python(ctx)
    features = [
        feature(name = "supports_pic", enabled = True),
        feature(name = "supports_dynamic_linker", enabled = True),
        _abi_feature(ctx.attr.version, ctx.attr.threads),
        # Requested by an extension library's side module, which exports only its entry
        # symbol: its flag follows the ABI's, so it replaces SIDE_MODULE=1.
        feature(
            name = "godot_web_entry_only",
            flag_sets = [_flags(_SHARED_LINK, ["-sSIDE_MODULE=2"])],
        ),
        feature(
            name = "emscripten_environment",
            enabled = True,
            env_sets = [env_set(
                actions = _COMPILE + _LINK + [ACTION_NAMES.cpp_link_static_library],
                env_entries = [env_entry(key = "EMSDK_PYTHON", value = python.interpreter.path)],
            )],
        ),
        feature(name = "opt", flag_sets = [_flags(_COMPILE, ["-O2", "-DNDEBUG"])]),
        feature(name = "dbg", flag_sets = [_flags(_COMPILE, ["-O0", "-g"])]),
        feature(name = "fastbuild"),
    ]
    return cc_common.create_cc_toolchain_config_info(
        ctx = ctx,
        features = features,
        cxx_builtin_include_directories = [
            root + "/emscripten/cache/sysroot/include",
            "%s/lib/clang/%s/include" % (root, ctx.attr.clang_major),
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
    doc = "The configuration of an Emscripten SDK's toolchain for Godot's web extensions.",
    implementation = _impl,
    attrs = {
        "version": attr.string(doc = "The Emscripten version.", mandatory = True),
        "sdk_root": attr.string(doc = "The SDK repository's path in the execution root.", mandatory = True),
        "clang_major": attr.string(doc = "The SDK's clang resource directory.", mandatory = True),
        "threads": attr.bool(doc = "Whether the toolchain builds for the threaded templates."),
    },
    provides = [CcToolchainConfigInfo],
    toolchains = [_PYTHON],
)

def _python_files_impl(ctx):
    return [DefaultInfo(files = _python(ctx).files)]

python_files = rule(
    doc = "The files of the execution platform's Python, which emcc runs on.",
    implementation = _python_files_impl,
    toolchains = [_PYTHON],
)
