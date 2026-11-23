"""Source contracts with deliberate mismatches against their Bazel-evaluated interface."""

load(":visibility_fixture.bzl", _same_package_leak = "same_package_leak")

FixtureInfo = provider(doc = "Expected provider identity of the Bazel-evaluated contract fixture.", fields = [])

_FILES_DOC = """
Produce one controlled artifact.

### Default outputs
- files (one): build
"""

_GROUP_DOC = _FILES_DOC + """
### Output groups
- `report`: fixture artifact
"""

def _file(ctx):
    output = ctx.actions.declare_file(ctx.label.name + ".txt")
    ctx.actions.write(output, "Bazel-evaluated contract fixture\n")
    return output

def _good_impl(ctx):
    output = _file(ctx)
    return [DefaultInfo(files = depset([output])), OutputGroupInfo(report = depset([output])), FixtureInfo()]

def _plain_impl(ctx):
    return [DefaultInfo(files = depset([_file(ctx)]))]

def _executable_impl(ctx):
    output = ctx.actions.declare_file(ctx.label.name + ".sh")
    ctx.actions.write(output, "#!/bin/sh\nexit 0\n", is_executable = True)
    return [DefaultInfo(executable = output, runfiles = ctx.runfiles(files = [output]))]

good = rule(doc = _GROUP_DOC, implementation = _good_impl)
missing_group = rule(doc = _GROUP_DOC.replace("`report`", "`missing`"), implementation = _good_impl)
executable_claim = rule(
    doc = _FILES_DOC.replace("- files (one): build", "- test (one): test"),
    implementation = _executable_impl,
    executable = True,
)

_plain = rule(implementation = _plain_impl)

def _restricted_leak_impl(name, visibility, **kwargs):
    _plain(name = name, visibility = visibility, **kwargs)
    native.filegroup(
        name = name + ".unexpected",
        srcs = [":" + name],
        visibility = ["//godot/private:__pkg__"],
    )

restricted_companion = macro(
    doc = _FILES_DOC,
    inherit_attrs = "common",
    implementation = _restricted_leak_impl,
)

def _companion_doc(kind, purpose):
    return _FILES_DOC + """
### Generated targets
- `{name}.boundary` (%s): Check a separately analyzed operation
  - purpose: %s
  - testonly: inherit
""" % (kind, purpose)

def _executable_companion_impl(name, visibility, **kwargs):
    _plain(name = name, visibility = visibility, **kwargs)
    executable_claim(name = name + ".boundary", visibility = ["//visibility:public"])

pretend_test_companion = macro(
    doc = _companion_doc("test", "test"),
    inherit_attrs = "common",
    implementation = _executable_companion_impl,
)

def _alias_files_impl(name, visibility, **kwargs):
    _plain(name = name, visibility = visibility, **kwargs)
    native.filegroup(name = name + ".data", srcs = [":" + name], visibility = ["//visibility:private"])
    native.alias(name = name + ".boundary", actual = ":" + name + ".data", visibility = ["//visibility:public"])

alias_files_companion = macro(
    doc = _companion_doc("alias", "analysis_boundary"),
    inherit_attrs = "common",
    implementation = _alias_files_impl,
)

def _alias_executable_impl(name, visibility, **kwargs):
    _plain(name = name, visibility = visibility, **kwargs)
    executable_claim(name = name + ".operation", visibility = ["//visibility:private"])
    native.alias(name = name + ".boundary", actual = ":" + name + ".operation", visibility = ["//visibility:public"])

alias_executable_companion = macro(
    doc = _companion_doc("alias", "analysis_boundary"),
    inherit_attrs = "common",
    implementation = _alias_executable_impl,
)

same_package_leak = _same_package_leak
