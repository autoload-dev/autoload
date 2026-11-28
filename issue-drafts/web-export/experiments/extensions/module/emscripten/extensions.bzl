"""
Emscripten SDKs per version and execution platform, and a hub of toolchains selected by
//emscripten:version: the shape a ruleset-owned toolchain per Godot profile would take.
"""

# Reused from BCR emsdk: the pinned release table and the SDK's filegroups. Everything else
# (toolchain config, wrappers, Python, cache) is owned here.
load("@emsdk//:emscripten_build_file.bzl", "EMSCRIPTEN_BUILD_FILE_CONTENT_TEMPLATE")
load("@emsdk//:revisions.bzl", "EMSCRIPTEN_TAGS")

_URL = "https://storage.googleapis.com/webassembly/emscripten-releases-builds/{os}/{hash}/wasm-binaries{suffix}.tar.xz"

# Execution platforms: (emsdk's sha field, URL os, URL suffix, constraints).
_EXEC = {
    "linux_x86_64": ("sha_linux", "linux", "", ["@platforms//os:linux", "@platforms//cpu:x86_64"]),
    "linux_arm64": ("sha_linux_arm64", "linux", "-arm64", ["@platforms//os:linux", "@platforms//cpu:arm64"]),
    "macos_arm64": ("sha_mac_arm64", "mac", "-arm64", ["@platforms//os:macos", "@platforms//cpu:arm64"]),
    "macos_x86_64": ("sha_mac", "mac", "", ["@platforms//os:macos", "@platforms//cpu:x86_64"]),
}

def _sdk_impl(ctx):
    ctx.download_and_extract(url = ctx.attr.url, sha256 = ctx.attr.sha256, stripPrefix = "install")
    clang = [p.basename for p in ctx.path("lib/clang").readdir()]
    if len(clang) != 1:
        fail("expected one clang resource directory, found %s" % clang)
    sdk_root = "external/" + ctx.name
    for tool, py in [("emcc.sh", "emcc"), ("emar.sh", "emar")]:
        ctx.template(tool, ctx.attr._wrapper, {"{SDK_ROOT}": sdk_root, "{TOOL}": py}, executable = True)
    ctx.template("emscripten_config", ctx.attr._config, {})
    ctx.template("BUILD.bazel", ctx.attr._build, {
        "{CONFIG_BZL_REPO}": ctx.attr._build.workspace_name,
        "{EMSDK_FILEGROUPS}": EMSCRIPTEN_BUILD_FILE_CONTENT_TEMPLATE.format(bin_extension = "").replace(
            "package(default_visibility = ['//visibility:public'])",
            "",
        ),
        "{VERSION}": ctx.attr.version,
        "{EXEC}": ctx.attr.exec_name,
        "{SDK_ROOT}": sdk_root,
        "{CLANG_MAJOR}": clang[0],
    })
    return ctx.repo_metadata(reproducible = True)

emscripten_sdk = repository_rule(
    implementation = _sdk_impl,
    attrs = {
        "url": attr.string(mandatory = True),
        "sha256": attr.string(mandatory = True),
        "version": attr.string(mandatory = True),
        "exec_name": attr.string(mandatory = True),
        "_wrapper": attr.label(default = "//emscripten:emcc.sh.tpl"),
        "_config": attr.label(default = "//emscripten:emscripten_config.tpl"),
        "_build": attr.label(default = "//emscripten:sdk.BUILD.tpl"),
    },
)

def _hub_impl(ctx):
    lines = ['package(default_visibility = ["//visibility:public"])', ""]
    for version in ctx.attr.versions:
        v = version.replace(".", "_")
        lines.append("""config_setting(
    name = "is_{v}",
    flag_values = {{"{flag}": "{version}"}},
)
""".format(v = v, flag = ctx.attr.version_flag, version = version))
        for exec_name in ctx.attr.exec_names:
            lines.append("""toolchain(
    name = "emscripten_{v}_{e}",
    exec_compatible_with = {exec_constraints},
    target_compatible_with = ["@platforms//os:emscripten", "@platforms//cpu:wasm32"],
    target_settings = [":is_{v}"],
    toolchain = "@{repo}//:cc_toolchain",
    toolchain_type = "@bazel_tools//tools/cpp:toolchain_type",
)
""".format(
                v = v,
                e = exec_name,
                exec_constraints = repr(_EXEC[exec_name][3]),
                repo = ctx.attr.repos["%s|%s" % (version, exec_name)],
            ))
    ctx.file("BUILD.bazel", "\n".join(lines))

_hub = repository_rule(
    implementation = _hub_impl,
    attrs = {
        "versions": attr.string_list(),
        "exec_names": attr.string_list(),
        "repos": attr.string_dict(),
        "version_flag": attr.string(),
    },
)

def _extension_impl(mctx):
    versions = []
    for mod in mctx.modules:
        for tag in mod.tags.version:
            if tag.version not in versions:
                versions.append(tag.version)
    repos = {}
    for version in versions:
        revision = EMSCRIPTEN_TAGS[version]
        for exec_name, (sha_field, url_os, suffix, _) in _EXEC.items():
            name = "emscripten_%s_%s" % (version.replace(".", "_"), exec_name)
            emscripten_sdk(
                name = name,
                url = _URL.format(os = url_os, hash = revision.hash, suffix = suffix),
                sha256 = getattr(revision, sha_field),
                version = version,
                exec_name = exec_name,
            )
            repos["%s|%s" % (version, exec_name)] = "@" + name
    _hub(
        name = "emscripten_toolchains",
        versions = versions,
        exec_names = _EXEC.keys(),
        repos = {k: v.removeprefix("@") for k, v in repos.items()},
        version_flag = str(Label("//emscripten:version")),
    )
    return mctx.extension_metadata(reproducible = True)

emscripten = module_extension(
    implementation = _extension_impl,
    tag_classes = {"version": tag_class(attrs = {"version": attr.string(mandatory = True)})},
)
