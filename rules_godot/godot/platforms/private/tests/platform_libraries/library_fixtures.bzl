"""
Stand-ins for the Android and Apple libraries of add-ons and extensions.

They provide JavaInfo or CcInfo without a Java or C++ toolchain, so the fixtures analyze for
any export platform on any host.
"""

load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("@rules_java//java/common:java_info.bzl", "JavaInfo")

visibility("//godot/platforms/private/tests/platform_libraries/...")

def _java_fixture_impl(ctx):
    jar = ctx.actions.declare_file(ctx.label.name + ".jar")
    ctx.actions.write(jar, "")
    return [JavaInfo(output_jar = jar, compile_jar = jar)]

java_fixture = rule(
    doc = "A JavaInfo stand-in for an Android library.",
    implementation = _java_fixture_impl,
)

def _cc_fixture_impl(ctx):
    libraries = []
    files = []
    if ctx.attr.static_archive:
        archive = ctx.actions.declare_file("lib%s.a" % ctx.label.name)
        ctx.actions.write(archive, "")
        files.append(archive)
        libraries.append(cc_common.create_library_to_link(
            actions = ctx.actions,
            static_library = archive,
        ))
    linker_input = cc_common.create_linker_input(
        owner = ctx.label,
        libraries = depset(libraries),
        user_link_flags = depset(ctx.attr.linkopts),
    )
    return [
        DefaultInfo(files = depset(files)),
        CcInfo(linking_context = cc_common.create_linking_context(
            linker_inputs = depset([linker_input]),
        )),
        OutputGroupInfo(archive = depset(files)),
    ]

cc_fixture = rule(
    doc = "A CcInfo stand-in for an Apple library, which links a static archive or only flags.",
    implementation = _cc_fixture_impl,
    attrs = {
        "linkopts": attr.string_list(doc = "Link flags of the library."),
        "static_archive": attr.bool(doc = "Link an empty static archive, as an iOS extension library."),
    },
)
