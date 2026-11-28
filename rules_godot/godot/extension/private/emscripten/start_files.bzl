"""
The start file a threaded side module links, built in the build instead of Emscripten's cache.

emcc links a side module with threads with its crtbegin object, which it builds into its
cache on first use from system/lib/pthread/emscripten_tls_init.c. The SDK archives ship
without it, and the SDK repository's cache is frozen and read-only. This rule compiles that
source with the configuration's Emscripten toolchain, as emcc's system library build does,
and hands the object to the link with -nostartfiles, so emcc adds none of its own.
"""

load("@rules_cc//cc:find_cc_toolchain.bzl", "find_cc_toolchain", "use_cc_toolchain")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")

visibility(["//godot/extension/private/..."])

_SOURCE = "emscripten/system/lib/pthread/emscripten_tls_init.c"

# The include directories and flags of emcc's MuslInternalLibrary, relative to the SDK.
_INCLUDES = [
    # Emscripten 6 keeps musl's architecture headers apart.
    "emscripten/system/lib/libc/musl/arch/emscripten",
    "emscripten/system/lib/libc/musl/arch/generic",
    "emscripten/system/lib/libc/musl/src/internal",
    "emscripten/system/lib/libc/musl/src/include",
    "emscripten/system/lib/libc/musl/include",
    "emscripten/system/lib/libc",
    "emscripten/system/lib/pthread",
]

# Position independent as the side module, which the toolchain compiles every object as.
_FLAGS = ["-std=c99", "-D_XOPEN_SOURCE=700", "-Wno-unused-result", "-fPIC", "-O2"]

def _start_files_impl(ctx):
    toolchain = find_cc_toolchain(ctx)
    sources = [file for file in toolchain.all_files.to_list() if file.path.endswith("/" + _SOURCE)]
    if len(sources) != 1:
        fail("%s: the C/C++ toolchain %s has no Emscripten source %s" % (ctx.label, toolchain.toolchain_id, _SOURCE))
    source = sources[0]
    root = source.path[:-len(_SOURCE)]
    features = cc_common.configure_features(ctx = ctx, cc_toolchain = toolchain)
    compiled, outputs = cc_common.compile(
        name = ctx.label.name,
        actions = ctx.actions,
        feature_configuration = features,
        cc_toolchain = toolchain,
        srcs = [source],
        system_includes = [root + include for include in _INCLUDES],
        user_compile_flags = _FLAGS,
    )
    objects = outputs.pic_objects or outputs.objects
    linker_input = cc_common.create_linker_input(
        owner = ctx.label,
        user_link_flags = depset(["-nostartfiles"] + [obj.path for obj in objects]),
        additional_inputs = depset(objects),
    )
    _ = compiled  # @unused
    return [CcInfo(linking_context = cc_common.create_linking_context(linker_inputs = depset([linker_input])))]

emscripten_start_files = rule(
    doc = "The crtbegin object of a threaded side module, compiled with the configuration's Emscripten toolchain.",
    implementation = _start_files_impl,
    toolchains = use_cc_toolchain(),
    fragments = ["cpp"],
)
