"""Library fixtures of the extension tests: metadata-only files and XCFramework imports."""

load("@rules_apple//apple:apple.bzl", "apple_dynamic_xcframework_import")
load("@rules_cc//cc:find_cc_toolchain.bzl", "find_cc_toolchain", "use_cc_toolchain")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")

# The slices of the XCFramework fixtures, as vendors ship iOS ones.
_SLICES = ["ios-arm64", "ios-arm64_x86_64-simulator"]

visibility([
    "//godot/extension/tests/...",
    "//godot/platforms/private/tests/...",
    "//godot/private/config/tests/...",
])

def _fixture_impl(ctx):
    output = ctx.actions.declare_file(
        ctx.label.name + "/" + ctx.attr.filename if ctx.attr.filename else "libandroid_contract_fixture.so",
    )
    ctx.actions.write(output, "Metadata-only Android library fixture; never loaded.\n")
    return [DefaultInfo(files = depset([output]))]

extension_library_fixture = rule(
    implementation = _fixture_impl,
    attrs = {"filename": attr.string()},
)

def _xcframework_fixture_impl(ctx):
    # Like apple_static_xcframework_import: every slice is a file, but CcInfo
    # links only the slice the target platform selects.
    slices = []
    for identifier in _SLICES:
        archive = ctx.actions.declare_file(
            "Fixture.xcframework/%s/libfixture.a" % identifier,
        )
        ctx.actions.write(archive, "Metadata-only static library slice; never linked.\n")
        slices.append(archive)
    cc_toolchain = find_cc_toolchain(ctx)
    library = cc_common.create_library_to_link(
        actions = ctx.actions,
        feature_configuration = cc_common.configure_features(
            ctx = ctx,
            cc_toolchain = cc_toolchain,
        ),
        cc_toolchain = cc_toolchain,
        static_library = slices[0],
    )
    linker_input = cc_common.create_linker_input(
        owner = ctx.label,
        libraries = depset([library]),
    )
    return [
        DefaultInfo(files = depset(slices)),
        CcInfo(linking_context = cc_common.create_linking_context(
            linker_inputs = depset([linker_input]),
        )),
    ]

xcframework_fixture = rule(
    implementation = _xcframework_fixture_impl,
    fragments = ["cpp"],
    toolchains = use_cc_toolchain(),
)

def _dynamic_xcframework_files_impl(ctx):
    # A dynamic XCFramework's files as a vendor ships them, one framework per slice whose
    # binary is named after it, for rules_apple's import to select from.
    name = ctx.attr.binary
    files = []
    for path in ["Info.plist"] + [
        "%s/%s.framework/%s" % (identifier, name, file)
        for identifier in _SLICES
        for file in [name, "Info.plist"]
    ]:
        output = ctx.actions.declare_file("%s/%s.xcframework/%s" % (ctx.label.name, name, path))
        ctx.actions.write(output, "Metadata-only framework file; never loaded.\n")
        files.append(output)
    return [DefaultInfo(files = depset(files))]

_dynamic_xcframework_files = rule(
    implementation = _dynamic_xcframework_files_impl,
    attrs = {"binary": attr.string(mandatory = True)},
)

def dynamic_xcframework_fixture(name, binary, deps = []):
    """
    Declare an import of a dynamic XCFramework of binary that links nothing, as Godot loads it.

    Args:
        name: Name of the apple_dynamic_xcframework_import.
        binary: The framework binary's name; the framework is <binary>.framework.
        deps: The import's deps, such as the frameworks it loads.
    """
    _dynamic_xcframework_files(name = name + "_files", binary = binary, tags = ["manual"])
    apple_dynamic_xcframework_import(
        name = name,
        bundle_only = True,
        tags = ["manual"],
        xcframework_imports = [":" + name + "_files"],
        deps = deps,
    )
