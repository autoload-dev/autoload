"""
Repositories of `godot_android_toolchains`: Android toolchains per execution platform.

rules_android's `//toolchains/android_sdk:android_sdk_tools` and
`//toolchains/android:android_default_toolchain` and the NDK toolchains of rules_android_ndk
carry no execution constraints and resolve this host's tools, so the hub registers its own
with `--extra_toolchains` priority. The repositories reuse the BUILD templates of
rules_android and rules_android_ndk.

Sections: Linux SDK, Linux NDK, Toolchain hub, Planning.
"""

load("@rules_android_ndk//:rules.bzl", "android_ndk_repository")
load("//godot/private:repository_templates.bzl", "fill_template", "starlark_dict")

visibility(["//godot", "//godot/platforms/private/tests"])

# The Android versions tools/android/sdk.json pins as build_tools, api_levels and ndk,
# from Google's SDK repository (repository2-3.xml).
_REPOSITORY = "https://dl.google.com/android/repository/"

_PLATFORMS = {
    "35": struct(
        archive = "platform-35_r02.zip",
        integrity = "sha256-CYjKytAbOKGKR7rBSgaV8ka8dsGwbA7rjrDcglqwyOA=",
    ),
    "36": struct(
        archive = "platform-36_r02.zip",
        integrity = "sha256-N2BzaaKMW2QLOnmYho1FiY68t3dWWg6F+azzbyljHS4=",
    ),
}

_LINUX_CLANG = "toolchains/llvm/prebuilt/linux-x86_64"

_NDK_TEMPLATES = "@rules_android_ndk//:"

def _require_revision(ctx, directory, expected, _fail):
    """Fail unless an extracted package's source.properties names the pinned revision."""
    properties = ctx.read(directory + "source.properties").splitlines()
    revisions = [
        line.partition("=")[2].strip()
        for line in properties
        if line.partition("=")[0].strip() == "Pkg.Revision"
    ]
    if revisions != [expected]:
        _fail("%s holds revision %s, not the pinned %s" % (ctx.name, revisions, expected))
        return False
    return True

# ==== Linux SDK ===============================================================

_LINUX_BUILD_TOOLS = struct(
    version = "35.0.0",
    archive = "build-tools_r35_linux.zip",
    integrity = "sha256-vTpJZpEuuLMO0NALDNprZUO5SdX/4AvqVMBMgeFWHYg=",
    strip_prefix = "android-15",
)

_SDK_TEMPLATES = "@rules_android//rules/android_sdk_repository:"

def _linux_sdk_impl(ctx):
    build_tools = _LINUX_BUILD_TOOLS.version
    ctx.download_and_extract(
        url = _REPOSITORY + _LINUX_BUILD_TOOLS.archive,
        integrity = _LINUX_BUILD_TOOLS.integrity,
        stripPrefix = _LINUX_BUILD_TOOLS.strip_prefix,
        output = "build-tools/" + build_tools,
    )
    _require_revision(ctx, "build-tools/%s/" % build_tools, build_tools, fail)
    for level, platform in _PLATFORMS.items():
        ctx.download_and_extract(
            url = _REPOSITORY + platform.archive,
            integrity = platform.integrity,
            stripPrefix = "android-" + level,
            output = "platforms/android-" + level,
        )

    # rules_android's repository links a copy of its helper, whose loads would then resolve
    # in this extension's repository mapping; this one forwards to rules_android's helper.
    ctx.file("helper.bzl", """load(
    "{helper}",
    _create_android_sdk_rules = "create_android_sdk_rules",
    _create_system_images_filegroups = "create_system_images_filegroups",
)

create_android_sdk_rules = _create_android_sdk_rules
create_system_images_filegroups = _create_system_images_filegroups
""".format(helper = Label(_SDK_TEMPLATES + "helper.bzl")))

    # The template also declares sdk-<level>-toolchain targets for this host's execution
    # constraints; the hub registers this repository's SDKs for Linux instead.
    ctx.template(
        "BUILD.bazel",
        Label(_SDK_TEMPLATES + "template.bzl"),
        {
            "__repository_name__": ctx.name,
            "__build_tools_version__": build_tools,
            "__build_tools_directory__": build_tools,
            "__api_levels__": ", ".join(['"%s"' % level for level in _PLATFORMS]),
            "__default_api_level__": sorted(_PLATFORMS)[0],
            "__system_image_dirs__": "",
        },
    )
    return ctx.repo_metadata(reproducible = True)

_linux_sdk = repository_rule(
    doc = "The pinned Linux build tools and platforms, as rules_android's SDK repository.",
    implementation = _linux_sdk_impl,
)

# ==== Linux NDK ===============================================================

_LINUX_NDK = struct(
    version = "29.0.14206865",
    archive = "android-ndk-r29-linux.zip",
    integrity = "sha256-Sru83IQvPUh5IG6WldUnCWA+Ut1o08H/8Es7Xnowjs8=",
    strip_prefix = "android-ndk-r29",
)

def linux_ndk_impl(ctx, *, _fail = fail):
    """
    Download the pinned Linux NDK and generate rules_android_ndk's BUILD files for it.

    Args:
        ctx: Repository rule context with the api_level attribute.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        The repository's metadata; None after an error.
    """
    ctx.download_and_extract(
        url = _REPOSITORY + _LINUX_NDK.archive,
        integrity = _LINUX_NDK.integrity,
        stripPrefix = _LINUX_NDK.strip_prefix,
    )
    if not _require_revision(ctx, "", _LINUX_NDK.version, _fail):
        return None

    # rules_android_ndk asks the host's clang for its resource directory; this clang
    # cannot run here, and the NDK holds exactly one.
    resources = ctx.path(_LINUX_CLANG + "/lib/clang").readdir()
    if len(resources) != 1:
        _fail("expected one clang resource directory in %s, found %s" % (
            _LINUX_CLANG,
            resources,
        ))
        return None
    sysroot = _LINUX_CLANG + "/sysroot"
    ctx.symlink("sources", "ndk/sources")
    ctx.template(
        "BUILD.bazel",
        Label(_NDK_TEMPLATES + "BUILD.ndk_root.tpl"),
        {"{clang_directory}": _LINUX_CLANG},
    )
    ctx.template("target_systems.bzl", Label(_NDK_TEMPLATES + "target_systems.bzl.tpl"), {})
    ctx.template(
        _LINUX_CLANG + "/BUILD.bazel",
        Label(_NDK_TEMPLATES + "BUILD.ndk_clang.tpl"),
        {
            "{repository_name}": Label(_NDK_TEMPLATES + "BUILD").repo_name,
            "{api_level}": str(ctx.attr.api_level),
            "{clang_resource_directory}": "lib/clang/" + resources[0].basename,
            "{sysroot_directory}": sysroot,
            "{executable_extension}": "",
        },
    )
    ctx.template(
        sysroot + "/BUILD.bazel",
        Label(_NDK_TEMPLATES + "BUILD.ndk_sysroot.tpl"),
        {"{api_level}": str(ctx.attr.api_level)},
    )
    return ctx.repo_metadata(reproducible = True)

_linux_ndk = repository_rule(
    doc = "The checksum-pinned Linux NDK, as rules_android_ndk's NDK repository.",
    implementation = linux_ndk_impl,
    attrs = {
        "api_level": attr.int(
            doc = "Native API level the NDK compiles for.",
            mandatory = True,
        ),
    },
)

# ==== Toolchain hub ===========================================================

def _ndk_toolchains(ctx, name, clang, constraints):
    return fill_template(ctx, ctx.attr._ndk_template, {
        "{NAME}": name,
        "{CLANG}": clang,
        "{CONSTRAINTS}": constraints,
    })

def hub_impl(ctx, *, _fail = fail):
    """
    Generate the hub that registers the host's and the Linux SDK and NDK toolchains.

    Args:
        ctx: Repository rule context with the hub's template attributes.
        _fail: Replaces fail in Starlark unit tests.
    """
    if ctx.os.name == "mac os x":
        host_ndk = "@android_ndk//toolchains/llvm/prebuilt/darwin-x86_64"
    elif ctx.os.name == "linux":
        host_ndk = "@android_ndk//" + _LINUX_CLANG
    else:
        _fail("Unsupported operating system: " + ctx.os.name)
        return

    # A Linux host serves Linux executors with its own SDK and NDK, under the same target
    # names; other hosts fetch the Linux SDK and NDK only when toolchain resolution selects
    # them, and fail analysis for an API level without a pinned Linux platform.
    if ctx.os.name == "linux":
        sdk = "@androidsdk"
        linux_ndk = host_ndk
        linux_sdk = repr("@androidsdk//:sdk")
    else:
        sdk = "@android_sdk_linux_x86_64"
        linux_ndk = "@android_ndk_linux_x86_64//" + _LINUX_CLANG
        linux_sdk = "select(\n        %s,\n        no_match_error = %r,\n    )" % (
            starlark_dict(
                {
                    ":api_level_" + level: "%s//:sdk-%s" % (sdk, level)
                    for level in _PLATFORMS
                },
                indent = "        ",
            ),
            "Linux executors have the Android SDK platforms %s only. Set " % (
                ", ".join(_PLATFORMS)
            ) + "--@androidsdk//:api_level to one of them or build on this host.",
        )
    ctx.template("target_systems.bzl", Label(_NDK_TEMPLATES + "target_systems.bzl.tpl"), {})
    ctx.file("BUILD.bazel", fill_template(ctx, ctx.attr._build_template, {
        "{HOST_NDK_TOOLCHAINS}": _ndk_toolchains(ctx, "ndk", host_ndk, "HOST_CONSTRAINTS"),
        "{LINUX_NDK_TOOLCHAINS}": _ndk_toolchains(
            ctx,
            "ndk_linux_x86_64",
            linux_ndk,
            "_LINUX_X86_64",
        ),
        "{SDK}": sdk,
        "{LINUX_SDK}": linux_sdk,
        "{API_LEVEL_SETTINGS}": "\n\n".join([
            fill_template(ctx, ctx.attr._api_level_template, {"{LEVEL}": level})
            for level in _PLATFORMS
        ]),
    }) + "\n")

_hub = repository_rule(
    doc = "The registration set of the Android toolchains, `@<name>//:all`.",
    implementation = hub_impl,
    attrs = {
        "_build_template": attr.label(default = Label(":android_toolchains.BUILD.tpl")),
        "_ndk_template": attr.label(default = Label(":android_toolchains_ndk.BUILD.tpl")),
        "_api_level_template": attr.label(
            default = Label(":android_toolchains_api_level.BUILD.tpl"),
        ),
    },
)

# ==== Planning ================================================================

def plan_android_toolchains(modules, *, _fail = fail):
    """
    Settle the godot_android_toolchains.configure tags of every module.

    The root module's tag applies; without one, the dependencies' tags must agree.

    Args:
        modules: module_ctx.modules.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        The NDK API level to configure, or None without tags or after an error.
    """
    requests = [(mod, tag) for mod in modules for tag in mod.tags.configure]
    root = [tag for mod, tag in requests if mod.is_root]
    if len(root) > 1:
        _fail("godot_android_toolchains takes at most one configure tag in the root module")
        return None
    levels = sorted({tag.ndk_api_level: None for _, tag in requests})
    if not root and len(levels) > 1:
        _fail((
            "Conflicting godot_android_toolchains.configure requests (ndk_api_level %s). " +
            "Configure it in the root module."
        ) % ", ".join([str(level) for level in levels]))
        return None
    if not requests:
        return None
    return root[0].ndk_api_level if root else levels[0]

def android_toolchain_declarations(name, ndk_api_level):
    """
    Return the hub and the SDK and NDK repositories it registers.

    Args:
        name: Name of the hub repository.
        ndk_api_level: Native API level of this host's NDK and the Linux NDK.

    Returns:
        A list of structs with `rule`, the name of a repository rule, and `attrs`, its
        keyword arguments.
    """
    return [
        struct(rule = "android_ndk_repository", attrs = {"name": "android_ndk", "api_level": ndk_api_level}),
        struct(rule = "linux_sdk", attrs = {"name": "android_sdk_linux_x86_64"}),
        struct(rule = "linux_ndk", attrs = {"name": "android_ndk_linux_x86_64", "api_level": ndk_api_level}),
        struct(rule = "hub", attrs = {"name": name}),
    ]

# The repository rules that android_toolchain_declarations names.
_RULES = {
    "android_ndk_repository": android_ndk_repository,
    "hub": _hub,
    "linux_ndk": _linux_ndk,
    "linux_sdk": _linux_sdk,
}

def android_toolchain_repositories(name, ndk_api_level):
    """
    Declare the hub and the SDK and NDK repositories it registers.

    Args:
        name: Name of the hub repository.
        ndk_api_level: Native API level of this host's NDK and the Linux NDK.
    """
    for declaration in android_toolchain_declarations(name, ndk_api_level):
        _RULES[declaration.rule](**declaration.attrs)
