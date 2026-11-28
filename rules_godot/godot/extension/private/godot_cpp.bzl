"""
The implementation of godot_cpp_bindings in godot/extension:repositories.bzl.

Errors go through `_fail`, so a Starlark unit test with a mocked repository_ctx collects
them; the implementation returns after an error.
"""

load("//godot/private:patches.bzl", "apply_repository_patches")
load("//godot/private:repository_templates.bzl", "starlark_list")
load("//godot/private:supply_chain.bzl", "source_purl", "write_package_metadata")
load(":godot_cpp_api.bzl", "binding_outputs", "included_classes")

visibility(["//godot/extension/..."])

# godot-cpp 10.0.0-stable, with the Godot 4.7 API and generated ABI loader.
GODOT_CPP_COMMIT = "507ed9d840c01a3c5b2a39af8bb4000bfac30bf5"
GODOT_CPP_SHA256 = "30da4ac295997061a6af81ae531510efd4e6a86e506eb4466edc0898ef3fe048"

def _download(ctx, _fail):
    """
    Download the archive of `version`, which replaces `{version}` in urls and strip_prefix.

    A URL without `{version}` is an error: the package URL would name another version than
    the one downloaded. Returns False after an error.
    """
    version = ctx.attr.version
    unversioned = [url for url in ctx.attr.urls if "{version}" not in url]
    if unversioned:
        _fail("godot_cpp_bindings: the URL %s does not name {version}" % unversioned[0])
        return False
    ctx.download_and_extract(
        url = [url.replace("{version}", version) for url in ctx.attr.urls],
        sha256 = ctx.attr.sha256,
        stripPrefix = ctx.attr.strip_prefix.replace("{version}", version),
        type = "tar.gz",
    )
    return True

def godot_cpp_bindings_impl(ctx, *, _fail = fail):
    """
    Fetch godot-cpp and generate the BUILD file of its bindings for one API selection.

    Args:
        ctx: Repository rule context of godot_cpp_bindings.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        The repository's metadata: reproducible when the archive is checksum-pinned.
    """
    if not _download(ctx, _fail):
        return None
    if not apply_repository_patches(ctx, _fail = _fail):
        return None
    api = json.decode(ctx.read(ctx.attr.api_path))
    if api["header"]["version_major"] != 4 or api["header"]["version_minor"] < 7:
        _fail("godot_cpp_bindings requires a Godot 4.7 or newer API within Godot 4")
        return None
    enabled = included_classes(api, ctx.attr.enabled_classes, _fail)
    if enabled == None:
        return None
    profile = None
    profile_generator = None
    if enabled:
        # Retain classes referenced by handwritten C++ sources in both the
        # output manifest and the upstream profile generator's input.
        ctx.file(
            "rules_godot_profile.json",
            json.encode({"enabled_classes": ctx.attr.enabled_classes + ["OS"]}),
        )
        profile = "rules_godot_profile.json"
        profile_generator = "build_profile.py"
    source_def = str(ctx.attr._defs)
    defines = ["GDEXTENSION", "THREADS_ENABLED"] + (
        ["REAL_T_IS_DOUBLE"] if ctx.attr.precision == "double" else []
    ) + (
        ["DEBUG_ENABLED", "HOT_RELOAD_ENABLED"] if ctx.attr.debug_features else []
    )
    ctx.template("BUILD.bazel", ctx.attr._build_template, substitutions = {
        "{BINDINGS_BZL}": repr(source_def),
        "{CC_LIBRARY_BZL}": repr(str(ctx.attr._cc_library)),
        "{API}": repr(ctx.attr.api_path),
        "{BITS}": repr(ctx.attr.bits),
        "{PRECISION}": repr(ctx.attr.precision),
        "{OUTS}": starlark_list(sorted(binding_outputs(api, enabled)), indent = "    "),
        "{PROFILE}": repr(profile),
        "{PROFILE_GENERATOR}": repr(profile_generator),
        "{DEFINES}": starlark_list(defines, indent = "    "),
        "{WINDOWS}": repr(str(ctx.attr._windows_constraint)),
    })
    write_package_metadata(
        ctx,
        source_purl("godot-cpp", ctx.attr.version, sha256 = ctx.attr.sha256),
        "LICENSE.md",
    )

    # A checksum-pinned archive and its patches determine the contents, so Bazel's repo
    # contents cache, local or remote, may reuse them.
    return ctx.repo_metadata(reproducible = bool(ctx.attr.sha256))
