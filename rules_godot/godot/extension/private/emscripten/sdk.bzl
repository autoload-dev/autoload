"""
The Emscripten SDK of one release on one execution platform, as a repository with the C/C++
toolchains that link Godot's web extension libraries over it.

The repository holds the release's prebuilt archive and builds nothing at fetch time: the
SDK's system libraries without threads come with it, and emcc runs with a frozen cache.
Loaded by the godot_engines extension, so it needs public load visibility; it is not a
consumer API.
"""

load("//godot/private/engine:profiles.bzl", "emscripten_release")

visibility("public")

# The execution platforms the release archives exist for: the operating system and file
# suffix of each archive's URL, and the platform's constraints.
EXECUTION_PLATFORMS = {
    "linux_x86_64": struct(os = "linux", suffix = "", constraints = ["@platforms//os:linux", "@platforms//cpu:x86_64"]),
    "linux_arm64": struct(os = "linux", suffix = "-arm64", constraints = ["@platforms//os:linux", "@platforms//cpu:aarch64"]),
    "macos_x86_64": struct(os = "mac", suffix = "", constraints = ["@platforms//os:macos", "@platforms//cpu:x86_64"]),
    "macos_arm64": struct(os = "mac", suffix = "-arm64", constraints = ["@platforms//os:macos", "@platforms//cpu:aarch64"]),
}

_URL = "https://storage.googleapis.com/webassembly/emscripten-releases-builds/{os}/{revision}/wasm-binaries{suffix}.tar.xz"

def sdk_repository_name(version, execution):
    """The name of the SDK repository of an Emscripten version on an execution platform."""
    return "emscripten_%s_%s" % (version.replace(".", "_"), execution)

def sdk_url(revision, execution):
    """The URL of the release archive of an emscripten-releases revision for an execution platform."""
    platform = EXECUTION_PLATFORMS[execution]
    return _URL.format(os = platform.os, revision = revision, suffix = platform.suffix)

def sdk_repositories(version):
    """
    Return the SDK repositories of the Emscripten release that builds an engine's web extensions.

    One per execution platform; engines of one minor share them, and Bazel fetches one only
    when toolchain resolution selects its toolchain for a web extension.

    Args:
        version: The engine's canonical version.

    Returns:
        The emscripten_sdk attributes of each repository; none for a version whose
        profile names no Emscripten release.
    """
    emscripten = emscripten_release(version)
    if not emscripten:
        return []
    return [
        {
            "name": sdk_repository_name(emscripten["version"], execution),
            "url": sdk_url(emscripten["revision"], execution),
            "sha256": emscripten["sha256"][execution],
            "version": emscripten["version"],
        }
        for execution in EXECUTION_PLATFORMS
    ]

def _sdk_impl(ctx):
    ctx.download_and_extract(url = ctx.attr.url, sha256 = ctx.attr.sha256, stripPrefix = "install")
    clang = [path.basename for path in ctx.path("lib/clang").readdir()]
    if len(clang) != 1:
        fail("expected one clang resource directory in the Emscripten %s archive, found %s" % (ctx.attr.version, clang))
    root = "external/" + ctx.name
    for tool, script in [("emcc.sh", "emcc"), ("em++.sh", "em++"), ("emar.sh", "emar")]:
        ctx.template(tool, ctx.attr._wrapper, {"{SDK_ROOT}": root, "{TOOL}": script}, executable = True)
    ctx.template("emscripten_config", ctx.attr._config, {})
    ctx.template("BUILD.bazel", ctx.attr._build, {
        "{TOOLCHAIN_BZL}": repr(str(ctx.attr._toolchain_bzl)),
        "{PYTHON}": repr(str(ctx.attr._python)),
        "{VERSION}": repr(ctx.attr.version),
        "{SDK_ROOT}": repr(root),
        "{CLANG_MAJOR}": repr(clang[0]),
    })
    ctx.file("REPO.bazel", "")

    # The checksum-pinned archive determines the contents.
    return ctx.repo_metadata(reproducible = True)

emscripten_sdk = repository_rule(
    doc = "The Emscripten SDK of one release and execution platform, with its C/C++ toolchains.",
    implementation = _sdk_impl,
    attrs = {
        "url": attr.string(doc = "The release archive's URL.", mandatory = True),
        "sha256": attr.string(doc = "The archive's SHA-256.", mandatory = True),
        "version": attr.string(doc = "The Emscripten version.", mandatory = True),
        "_wrapper": attr.label(default = Label(":emcc.sh.tpl")),
        "_config": attr.label(default = Label(":emscripten_config.tpl")),
        "_build": attr.label(default = Label(":sdk.BUILD.tpl")),
        "_toolchain_bzl": attr.label(default = Label(":toolchain_config.bzl")),
        "_python": attr.label(default = Label(":python")),
    },
)
