"""Test that the license of every released module carries the repository's license text."""

load("@bazel_skylib//lib:shell.bzl", "shell")
load("@package_metadata//providers:package_attribute_info.bzl", "PackageAttributeInfo")

def _license_texts_test_impl(ctx):
    texts = []
    checks = []
    for target in ctx.attr.package_licenses:
        files = target[PackageAttributeInfo].files.to_list()
        texts += files
        checks.append("check %s %s" % (
            shell.quote(str(target.label)),
            shell.quote(files[0].short_path if files else ""),
        ))
    script = ctx.actions.declare_file(ctx.label.name + ".sh")
    ctx.actions.write(script, is_executable = True, content = """\
#!/usr/bin/env bash
set -euo pipefail
status=0
check() {{
    if [ -z "$2" ]; then
        echo "$1 declares no license text" >&2
        status=1
    elif ! cmp -s "$2" {expected}; then
        echo "$1: $2 differs from the repository's LICENSE" >&2
        status=1
    fi
}}
{checks}
exit "$status"
""".format(expected = shell.quote(ctx.file.expected.short_path), checks = "\n".join(checks)))
    return [DefaultInfo(
        executable = script,
        runfiles = ctx.runfiles(files = texts + [ctx.file.expected]),
    )]

license_texts_test = rule(
    doc = """
    Test that each license declares a text, the module's copy of the expected license.

    A license's text is what a license report embeds; each module's release archive holds it
    at the module's root.
    """,
    implementation = _license_texts_test_impl,
    attrs = {
        "package_licenses": attr.label_list(
            doc = "The `license` targets of the modules' package metadata.",
            providers = [PackageAttributeInfo],
        ),
        "expected": attr.label(
            doc = "The license text each of them declares a copy of.",
            allow_single_file = True,
            mandatory = True,
        ),
    },
    test = True,
)
