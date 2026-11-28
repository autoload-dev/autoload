"""
The web toolchain of an engine whose Godot minor has no pinned Emscripten release.

Toolchain resolution picks it for that engine's web builds, and its analysis fails with what
is missing, in place of Bazel's error that no toolchain matches.
"""

visibility("public")

def _unpinned_toolchain_impl(ctx):
    fail("%s has no web toolchain: rules_godot pins no Emscripten release for Godot %s (%s), so its web extensions cannot build. The ruleset pins one per Godot minor, in profiles.bzl." % (
        ("The engine " + ctx.attr.engine) if ctx.attr.engine else "The default engine",
        ctx.attr.series,
        ctx.attr.version,
    ))

emscripten_unpinned_toolchain = rule(
    doc = "A C/C++ toolchain for the web whose analysis fails: the engine's Godot minor has no pinned Emscripten release.",
    implementation = _unpinned_toolchain_impl,
    attrs = {
        "engine": attr.string(doc = "The engine's name; empty for an unnamed default engine."),
        "series": attr.string(doc = "The engine's Godot minor, such as 4.9."),
        "version": attr.string(doc = "The engine's version."),
    },
)
