"""
The configuration in which builds analyze a part of an application, for analysis tests.

An analysis test that sets only --platforms analyzes its target in the build's top-level
configuration for that export platform. A pack or an application has its native code there
only on the edges that keep the incoming configuration, and a part of an application, such
as an iOS application's extension libraries, is never there: rules_apple's and
rules_android's splits configure it for one platform slice, with the operating system's
CPU and the ruleset's native options. in_platform_slice analyzes the target as a build
does, with the ruleset's own platform slice transition, and forwards the providers tests
read.
"""

load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("//godot:providers.bzl", "GodotPackInfo")
load("//godot/private/config:transitions.bzl", "platform_slice_transition")

visibility([
    "//godot/platforms/private/tests/...",
    "//godot/private/tests/...",
])

# The providers tests read: what a pack, an application pack or an application part returns.
_FORWARDED = [CcInfo, GodotPackInfo, OutputGroupInfo]

def _forward(target):
    return [DefaultInfo(files = target[DefaultInfo].files)] + [
        target[provider]
        for provider in _FORWARDED
        if provider in target
    ]

def _in_platform_slice_impl(ctx):
    if len(ctx.attr.target) != 1:
        fail("in_platform_slice needs an export platform with one platform slice; it has %d" % len(ctx.attr.target))
    return _forward(ctx.attr.target[0])

in_platform_slice = rule(
    doc = """
    Analyze a part of an application in the configuration of the build's export platform's
    one platform slice, as rules_apple's and rules_android's splits configure it.
    """,
    implementation = _in_platform_slice_impl,
    attrs = {
        "target": attr.label(mandatory = True, cfg = platform_slice_transition),
    },
)
