"""Checksum-pinned acquisition of prebuilt editor and export-template archives."""

load("//godot/engine/private:catalogue.bzl", "TEMPLATE_CPUS")
load("//godot/private:repository_templates.bzl", "fill_template", "starlark_list")
load("//godot/private:versions.bzl", "require_supported_godot_version")
load("//godot/private/config:settings.bzl", "CPU_TABLE")

visibility(["//godot/..."])

ARCHIVE_ATTRS = {
    "urls": attr.string_list(
        doc = "Ordered mirror URLs of the same ZIP or TPZ archive.",
        mandatory = True,
    ),
    "integrity": attr.string(
        doc = "Subresource Integrity digest of the archive, including the hash algorithm, such as sha512-...; required.",
        mandatory = True,
    ),
    "version": attr.string(
        doc = "Canonical Godot version of the archive's payloads; checked for ruleset support, not read from the archive.",
        mandatory = True,
    ),
}

EDITOR_ARCHIVE_ATTRS = ARCHIVE_ATTRS | {
    "binary": attr.string(
        doc = "Path of the editor executable inside the archive.",
        mandatory = True,
    ),
}

# Desktop runtime targets an export-template archive exposes, by operating system and
# CPU.
MACOS_CPUS = ["universal", "arm64", "x86_64"]

def _download(ctx, _fail):
    if not ctx.attr.integrity:
        _fail("integrity is required: every Godot download must be checksum-pinned")
        return False
    ctx.download_and_extract(url = ctx.attr.urls, integrity = ctx.attr.integrity, type = "zip")
    return True

def editor_archive_impl(ctx, *, _fail = fail):
    """
    Download one editor archive and generate its BUILD file.

    Args:
        ctx: Repository rule context.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        The repository's metadata: reproducible.
    """
    if not require_supported_godot_version(ctx.attr.version, _fail = _fail):
        return None
    if not _download(ctx, _fail):
        return None
    if not ctx.path(ctx.attr.binary).exists:
        _fail("Godot editor archive does not contain " + ctx.attr.binary)
        return None
    ctx.template("BUILD.bazel", ctx.attr._build_template, substitutions = {
        "{PREBUILT_BZL}": repr(str(ctx.attr._prebuilt_bzl)),
        "{BINARY}": repr(ctx.attr.binary),
        "{DIGEST}": repr(ctx.attr.integrity),
    })

    # The integrity-pinned archive determines the contents, so Bazel's repo contents
    # cache, local or remote, may reuse them.
    return ctx.repo_metadata(reproducible = True)

EDITOR_ARCHIVE_RULE_ATTRS = EDITOR_ARCHIVE_ATTRS | {
    "_prebuilt_bzl": attr.label(default = Label("//godot/engine/private:prebuilt.bzl")),
    "_build_template": attr.label(default = Label("//godot/engine/private:editor_archive.BUILD.tpl")),
}

def _runtimes(ctx, platform, name, binary, cpu):
    """Return the release and, when present, debug runtime declarations of one binary."""
    rules = []
    for variant in ["release", "debug"]:
        if variant == "debug" and not ctx.path(binary % variant).exists:
            continue
        rules.append(fill_template(ctx, ctx.attr._runtime_template, {
            "{NAME}": repr("%s_%s" % (name, variant)),
            "{CPU}": repr(cpu),
            "{BINARY}": repr(binary % variant),
            # The macOS runtime needs the template's application bundle.
            "{DATA}": '\n    data = [":macos_files"],' if platform == "macos" else "",
            "{PLATFORM}": repr(platform),
            "{VARIANT}": repr(variant),
            "{VERSION}": repr(ctx.attr.version),
            "{DIGEST}": repr(ctx.attr.integrity),
        }))
    return rules

def _ios(ctx, _fail):
    """Return the iOS XCFramework import declarations of an archive's ios.zip, "" or None after an error."""
    if not ctx.path("templates/ios.zip").exists:
        return ""
    ctx.extract("templates/ios.zip", output = "ios")
    for variant in ["debug", "release"]:
        path = "ios/libgodot.ios.%s.xcframework/Info.plist" % variant
        if not ctx.path(path).exists:
            _fail("Godot templates ios.zip is missing %s; expected Godot's ios.zip layout" % path)
            return None
    libraries = []
    dependencies = {"debug": [], "release": []}
    if ctx.path("ios/MoltenVK.xcframework/Info.plist").exists:
        libraries.append(fill_template(ctx, ctx.attr._ios_moltenvk_template, {}))
        for variant in dependencies:
            dependencies[variant].append(":ios_moltenvk")
    if ctx.path("ios/AccessKit.xcframework/Info.plist").exists:
        libraries.append(fill_template(ctx, ctx.attr._ios_accesskit_template, {}))
        for variant in dependencies:
            dependencies[variant].append(":ios_accesskit")
    for variant in ["debug", "release"]:
        camera = "libgodot_camera.ios.%s.xcframework" % variant
        if ctx.path("ios/" + camera + "/Info.plist").exists:
            libraries.append(fill_template(ctx, ctx.attr._ios_camera_template, {
                "{VARIANT}": variant,
                "{XCFRAMEWORK}": camera,
            }))
            dependencies[variant].append(":ios_camera_" + variant)
    return fill_template(ctx, ctx.attr._ios_template, {
        "{SIMULATOR}": repr(str(ctx.attr._simulator_constraint)),
        # Each library is set off by blank lines; without any, nothing.
        "{LIBRARIES}": "".join(["\n" + library + "\n" for library in libraries]),
        "{DEBUG_DEPS}": starlark_list(sorted(dependencies["debug"]), indent = "    "),
        "{RELEASE_DEPS}": starlark_list(sorted(dependencies["release"]), indent = "    "),
    })

def templates_archive_impl(ctx, *, _fail = fail):
    """
    Download one export-template archive and generate its runtime targets.

    Args:
        ctx: Repository rule context.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        The repository's metadata: reproducible.
    """
    if not require_supported_godot_version(ctx.attr.version, _fail = _fail):
        return None
    cpus = ctx.attr.macos_cpus
    if (
        len(depset(cpus).to_list()) != len(cpus) or
        any([cpu not in MACOS_CPUS for cpu in cpus]) or
        ("universal" in cpus and len(cpus) != 1)
    ):
        _fail('macos_cpus must be ["universal"] or a subset of ["arm64", "x86_64"]')
        return None
    if any([cpu not in CPU_TABLE for cpu in ctx.attr.linux_cpus]):
        _fail("linux_cpus must be Godot CPU tags: %s" % ", ".join(CPU_TABLE))
        return None
    if not _download(ctx, _fail):
        return None
    if ctx.path("templates/macos.zip").exists:
        ctx.extract("templates/macos.zip", output = "macos")
    else:
        cpus = []
    runtimes = []
    for cpu in ctx.attr.linux_cpus:
        binary = "templates/linux_%s." + cpu
        if not ctx.path(binary % "release").exists:
            _fail(
                "Godot template archive does not contain %s; " % (binary % "release") +
                "its Linux CPUs differ from the catalogue's",
            )
            return None
        runtimes.extend(_runtimes(ctx, "linux", "linux_" + cpu, binary, cpu))
    for cpu in cpus:
        name = "macos" if cpu == "universal" else "macos_" + cpu
        binary = "macos/macos_template.app/Contents/MacOS/godot_macos_%s." + cpu
        if not ctx.path(binary % "release").exists:
            _fail(
                "Godot template archive does not contain %s; " % (binary % "release") +
                "set macos_cpus to match the archive layout",
            )
            return None
        runtimes.extend(_runtimes(ctx, "macos", name, binary, cpu))
    ios = _ios(ctx, _fail)
    if ios == None:
        return None
    ctx.template("BUILD.bazel", ctx.attr._build_template, substitutions = {
        "{PREBUILT_BZL}": repr(str(ctx.attr._prebuilt_bzl)),
        "{APPLE_LOAD}": "load(%r, \"apple_static_xcframework_import\")" % str(ctx.attr._apple_bzl) if ios else "",
        # Each rule is set off by blank lines.
        "{RUNTIMES}": "".join(["\n" + rule + "\n" for rule in runtimes]),
        "{IOS}": ios,
    })

    # The integrity-pinned archive determines the contents, so Bazel's repo contents
    # cache, local or remote, may reuse them.
    return ctx.repo_metadata(reproducible = True)

TEMPLATES_ARCHIVE_ATTRS = ARCHIVE_ATTRS | {
    "macos_cpus": attr.string_list(
        doc = 'macOS template binary suffixes in the archive: ["universal"] or a subset of ["arm64", "x86_64"]. Empty disables macOS runtimes; archives without macos.zip omit them.',
        default = ["universal"],
    ),
    "linux_cpus": attr.string_list(
        doc = "Linux template binary suffixes in the archive, as Godot's CPU tags such as arm64 or x86_64. A missing binary fails.",
        default = TEMPLATE_CPUS["linux"],
    ),
}

TEMPLATES_ARCHIVE_RULE_ATTRS = TEMPLATES_ARCHIVE_ATTRS | {
    "_prebuilt_bzl": attr.label(default = Label("//godot/engine/private:prebuilt.bzl")),
    "_build_template": attr.label(default = Label("//godot/engine/private:export_templates.BUILD.tpl")),
    "_runtime_template": attr.label(default = Label("//godot/engine/private:prebuilt_runtime.BUILD.tpl")),
    "_apple_bzl": attr.label(default = Label("@rules_apple//apple:apple.bzl")),
    "_simulator_constraint": attr.label(default = Label("@apple_support//constraints:simulator")),
    "_ios_template": attr.label(default = Label("//godot/engine/private:ios_templates.BUILD.tpl")),
    "_ios_moltenvk_template": attr.label(default = Label("//godot/engine/private:ios_moltenvk.BUILD.tpl")),
    "_ios_accesskit_template": attr.label(default = Label("//godot/engine/private:ios_accesskit.BUILD.tpl")),
    "_ios_camera_template": attr.label(default = Label("//godot/engine/private:ios_camera.BUILD.tpl")),
}
