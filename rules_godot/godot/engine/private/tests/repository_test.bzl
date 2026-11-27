"""Analysis tests of the providers and default files of repository entrypoints."""

load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("//godot/private:providers.bzl", "GodotRuntimeInfo")

visibility("private")

_BINDING_HEADER = "gen/include/godot_cpp/classes/node.hpp"

def _repository_test_impl(env, target):
    expected = env.ctx.attr
    default = target[DefaultInfo]
    env.expect.that_bool(
        bool(default.files.to_list()),
        "the entrypoint has default files",
    ).equals(expected.files)
    env.expect.that_bool(
        default.files_to_run.executable != None,
        "the entrypoint is executable",
    ).equals(expected.executable)
    env.expect.that_bool(CcInfo in target, "the entrypoint returns CcInfo").equals(expected.cc)
    env.expect.that_bool(
        GodotRuntimeInfo in target,
        "the entrypoint returns GodotRuntimeInfo",
    ).equals(expected.runtime)
    if expected.generated_bindings and CcInfo in target:
        headers = target[CcInfo].compilation_context.headers.to_list()
        env.expect.that_bool(
            any([_BINDING_HEADER in header.path for header in headers]),
            "the entrypoint's headers include the generated " + _BINDING_HEADER,
        ).equals(True)

def repository_test(
        name,
        target,
        files = True,
        executable = False,
        cc = False,
        runtime = False,
        generated_bindings = False,
        **kwargs):
    """
    Check which providers and default files a repository's entrypoint returns.

    Args:
        name: The test's name.
        target: The entrypoint under test: a target or a file.
        files: Whether the entrypoint has default files.
        executable: Whether the entrypoint is executable. Bazel reports a file as its own
            executable.
        cc: Whether the entrypoint returns CcInfo.
        runtime: Whether the entrypoint returns GodotRuntimeInfo.
        generated_bindings: Whether the entrypoint's headers include generated godot-cpp
            class bindings.
        **kwargs: Common test attributes, such as size and tags.
    """
    analysis_test(
        name = name,
        target = target,
        impl = _repository_test_impl,
        attrs = {
            # An entrypoint may be a file, such as a source descriptor.
            "target": {"@attr": attr.label, "allow_files": True},
            "files": attr.bool(),
            "executable": attr.bool(),
            "cc": attr.bool(),
            "runtime": attr.bool(),
            "generated_bindings": attr.bool(),
        },
        attr_values = kwargs | {
            "files": files,
            "executable": executable,
            "cc": cc,
            "runtime": runtime,
            "generated_bindings": generated_bindings,
        },
    )
