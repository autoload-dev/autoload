load({CC_LIBRARY_BZL}, "cc_library")
load({BINDINGS_BZL}, "godot_cpp_bindings")

package(default_visibility = ["//visibility:public"])

exports_files([
    {API},
    "LICENSE.md",
])

godot_cpp_bindings(
    name = "bindings",
    visibility = ["//visibility:private"],
    outs = {OUTS},
    api = {API},
    # WebAssembly is 32-bit, whatever the bindings are for elsewhere.
    bits = select({
        {WEB}: "32",
        "//conditions:default": {BITS},
    }),
    generator = "binding_generator.py",
    interface = "gdextension/gdextension_interface.json",
    interface_generator = "make_interface_header.py",
    precision = {PRECISION},
    profile = {PROFILE},
    profile_generator = {PROFILE_GENERATOR},
)

filegroup(
    name = "bindings.headers",
    srcs = [":bindings"],
    output_group = "headers",
    visibility = ["//visibility:private"],
)

filegroup(
    name = "bindings.sources",
    srcs = [":bindings"],
    output_group = "sources",
    visibility = ["//visibility:private"],
)

cc_library(
    name = "godot_cpp",
    srcs = glob(["src/**/*.cpp"]) + [":bindings.sources"],
    hdrs = glob(
        [
            "include/**/*.hpp",
            "include/**/*.h",
            "include/**/*.inc",
        ],
        allow_empty = True,
    ) + [":bindings.headers"],
    # Hidden visibility matches upstream's symbols_visibility=hidden; the extension
    # library's export list is what keeps extensions apart.
    copts = select({
        {WINDOWS}: ["/std:c++17"],
        "//conditions:default": [
            "-std=c++17",
            "-fno-exceptions",
            "-fvisibility=hidden",
        ],
    }),
    # As upstream, threads where the platform has them: everywhere but the web without.
    defines = {DEFINES} + select({
        {WEB_NOTHREADS}: [],
        "//conditions:default": ["THREADS_ENABLED"],
    }),
    # Upstream's header search order; do not sort.
    includes = [
        "include",
        "gen/include",
    ],
    linkstatic = True,
)
