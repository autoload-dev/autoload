"""Checksum-pinned acquisition of prebuilt editor and export-template archives."""

load("//godot/private:repository_templates.bzl", "fill_template", "starlark_list")
load("//godot/private:versions.bzl", "require_supported_godot_version")
load("//godot/private/config:settings.bzl", "CPU_TABLE")

visibility(["//godot/..."])

_VERSION_ATTR = attr.string(
    doc = "Canonical Godot version of the archive's payloads; checked for ruleset support, not read from the archive.",
    mandatory = True,
)

EDITOR_ARCHIVE_ATTRS = {
    "urls": attr.string_list(
        doc = "Ordered mirror URLs of the same ZIP archive.",
        mandatory = True,
    ),
    "integrity": attr.string(
        doc = "Subresource Integrity digest of the archive, including the hash algorithm, such as sha512-...; required.",
        mandatory = True,
    ),
    "version": _VERSION_ATTR,
    "binary": attr.string(
        doc = "Path of the editor executable inside the archive.",
        mandatory = True,
    ),
}

def _download(ctx, _fail):
    if not ctx.attr.integrity:
        _fail("integrity is required: every Godot download must be checksum-pinned")
        return False
    ctx.download_and_extract(url = ctx.attr.urls, integrity = ctx.attr.integrity, type = "zip")
    return True

# The directory that the archive members a repository keeps are renamed into, so that
# strip_prefix extracts them alone: Bazel skips the entries outside the prefix.
_KEPT = "kept"

def _extract_members(ctx, members):
    """Extract the archive entries named `members` that the archive has; at least one must be present."""
    ctx.extract(
        ctx.path(ctx.attr.archive),
        type = "zip",
        rename_files = {member: _KEPT + "/" + member for member in members},
        strip_prefix = _KEPT,
        # The archive's repository verifies it against the integrity this repository's
        # definition also carries, so watching the archive would only rehash it.
        watch_archive = "no",
    )

def _extract_nested(ctx, archive, output, _fail):
    """Extract a ZIP archive inside the repository to `output` and delete it; False if it is missing."""
    if not ctx.path(archive).exists:
        _fail("Godot template archive does not contain " + archive)
        return False
    ctx.extract(archive, output = output)
    ctx.delete(archive)
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

def _ios_libraries(ctx):
    """
    Return the imports of the dependent XCFrameworks an expanded ios.zip carries.

    Args:
        ctx: Repository rule context.

    Returns:
        A tuple of the filled import declarations and, per variant, the labels of the
        imports the engine of that variant depends on.
    """
    camera = "libgodot_camera.ios.%s.xcframework"
    candidates = [
        ("MoltenVK.xcframework", ctx.attr._ios_moltenvk_template, "ios_moltenvk", ["debug", "release"], {}),
        ("AccessKit.xcframework", ctx.attr._ios_accesskit_template, "ios_accesskit", ["debug", "release"], {}),
    ] + [
        (camera % variant, ctx.attr._ios_camera_template, "ios_camera_" + variant, [variant], {
            "{VARIANT}": variant,
            "{XCFRAMEWORK}": camera % variant,
        })
        for variant in ["debug", "release"]
    ]
    libraries = []
    dependencies = {"debug": [], "release": []}
    for xcframework, template, name, variants, substitutions in candidates:
        if not ctx.path("ios/%s/Info.plist" % xcframework).exists:
            continue
        libraries.append(fill_template(ctx, template, substitutions))
        for variant in variants:
            dependencies[variant].append(":" + name)
    return libraries, dependencies

def _ios(ctx, _fail):
    """Return the iOS XCFramework import declarations of an archive's ios.zip, or None after an error."""
    if not _extract_nested(ctx, "templates/ios.zip", "ios", _fail):
        return None
    for variant in ["debug", "release"]:
        path = "ios/libgodot.ios.%s.xcframework/Info.plist" % variant
        if not ctx.path(path).exists:
            _fail("Godot templates ios.zip is missing %s; expected Godot's ios.zip layout" % path)
            return None
    libraries, dependencies = _ios_libraries(ctx)
    return fill_template(ctx, ctx.attr._ios_template, {
        "{SIMULATOR}": repr(str(ctx.attr._simulator_constraint)),
        # Each library is set off by blank lines; without any, nothing.
        "{LIBRARIES}": "".join(["\n" + library + "\n" for library in libraries]),
        "{DEBUG_DEPS}": starlark_list(sorted(dependencies["debug"]), indent = "    "),
        "{RELEASE_DEPS}": starlark_list(sorted(dependencies["release"]), indent = "    "),
    })

def _linux_runtimes(ctx, _fail):
    """Return the runtime declarations of the Linux templates, or None after an error."""
    runtimes = []
    for cpu in ctx.attr.cpus:
        binary = "templates/linux_%s." + cpu
        if not ctx.path(binary % "release").exists:
            _fail(
                "Godot template archive does not contain %s; " % (binary % "release") +
                "its Linux CPUs differ from the catalogue's",
            )
            return None
        runtimes.extend(_runtimes(ctx, "linux", "linux_" + cpu, binary, cpu))
    return runtimes

def _macos_runtimes(ctx, _fail):
    """Return the runtime declarations of an archive's macos.zip, or None after an error."""
    if not _extract_nested(ctx, "templates/macos.zip", "macos", _fail):
        return None
    runtimes = []
    for cpu in ctx.attr.cpus:
        name = "macos" if cpu == "universal" else "macos_" + cpu
        binary = "macos/macos_template.app/Contents/MacOS/godot_macos_%s." + cpu
        if not ctx.path(binary % "release").exists:
            _fail(
                "Godot template archive does not contain %s; " % (binary % "release") +
                "set cpus to match the archive layout",
            )
            return None
        runtimes.extend(_runtimes(ctx, "macos", name, binary, cpu))
    return runtimes

def _linux_cpus_error(cpus):
    if cpus and all([cpu in CPU_TABLE for cpu in cpus]):
        return None
    return "cpus of Linux templates must be Godot CPU tags: " + ", ".join(CPU_TABLE)

def _macos_cpus_error(cpus):
    if sorted(cpus) in [["universal"], ["arm64"], ["x86_64"], ["arm64", "x86_64"]]:
        return None
    return 'cpus of macOS templates must be ["universal"] or a subset of ["arm64", "x86_64"]'

def _ios_cpus_error(cpus):
    return "cpus must be empty for iOS templates" if cpus else None

def _ios_targets(ctx, _fail):
    ios = _ios(ctx, _fail)
    return None if ios == None else [ios]

# Per Godot platform: the error of cpus that do not describe its templates, or None; the
# archive entries its targets are made of; and its target declarations, or None after an
# error.
_PLATFORMS = {
    "linux": struct(
        cpus_error = _linux_cpus_error,
        members = lambda cpus: [
            "templates/linux_%s.%s" % (variant, cpu)
            for cpu in cpus
            for variant in ["release", "debug"]
        ],
        targets = _linux_runtimes,
    ),
    "macos": struct(
        cpus_error = _macos_cpus_error,
        members = lambda _cpus: ["templates/macos.zip"],
        targets = _macos_runtimes,
    ),
    "ios": struct(
        cpus_error = _ios_cpus_error,
        members = lambda _cpus: ["templates/ios.zip"],
        targets = _ios_targets,
    ),
}

# Godot's version file, which every export-template archive Godot installs carries.
# Extracting it with a platform's members keeps strip_prefix satisfied when the archive
# lacks them, so the repository can name the missing member.
_VERSION_FILE = "templates/version.txt"

def templates_archive_impl(ctx, *, _fail = fail):
    """
    Extract the templates of one platform from an export-template archive and generate their targets.

    Only the platform's members leave the archive.

    Args:
        ctx: Repository rule context.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        The repository's metadata: reproducible.
    """
    if not require_supported_godot_version(ctx.attr.version, _fail = _fail):
        return None
    platform = _PLATFORMS[ctx.attr.platform]
    error = platform.cpus_error(ctx.attr.cpus)
    if error:
        _fail(error)
        return None
    _extract_members(ctx, [_VERSION_FILE] + platform.members(ctx.attr.cpus))
    targets = platform.targets(ctx, _fail)
    if targets == None:
        return None
    apple_load = "load(%r, \"apple_static_xcframework_import\")" % str(ctx.attr._apple_bzl)
    ctx.template("BUILD.bazel", ctx.attr._build_template, substitutions = {
        "{PREBUILT_BZL}": repr(str(ctx.attr._prebuilt_bzl)),
        "{APPLE_LOAD}": apple_load if ctx.attr.platform == "ios" else "",
        # Each declaration is set off by blank lines.
        "{TARGETS}": "".join(["\n" + target + "\n" for target in targets]),
    })

    # The integrity-pinned archive determines the contents, so Bazel's repo contents
    # cache, local or remote, may reuse them.
    return ctx.repo_metadata(reproducible = True)

TEMPLATES_ARCHIVE_ATTRS = {
    "archive": attr.label(
        doc = "The export-template archive, a TPZ or ZIP file, such as another repository's download.",
        mandatory = True,
    ),
    "integrity": attr.string(
        doc = "Subresource Integrity digest of the archive, which the runtimes record as their provenance; whoever provides the archive verifies it.",
        mandatory = True,
    ),
    "version": _VERSION_ATTR,
    "platform": attr.string(
        doc = "Godot platform whose templates the repository extracts: linux, macos or ios.",
        mandatory = True,
        values = ["linux", "macos", "ios"],
    ),
    "cpus": attr.string_list(
        doc = """
        Template binary suffixes of the platform in the archive. Linux: Godot's CPU tags,
        such as arm64 or x86_64; a missing binary fails. macOS: ["universal"] or a subset of
        ["arm64", "x86_64"]. iOS: empty.
        """,
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

# The repository rules godot_engines.prebuilt declares for catalogued and declared releases.

godot_editor_archive = repository_rule(
    doc = """
    Acquire one checksum-pinned prebuilt editor archive.

    The repository exposes `:editor`, the executable with the complete distribution as
    runfiles, for a godot_editor_component; it registers nothing. The editor must match
    the operating system and CPU of the execution platform of the slot it fills. The
    declared version is checked for ruleset support; it is not read from the archive.
    """,
    implementation = editor_archive_impl,
    attrs = EDITOR_ARCHIVE_RULE_ATTRS,
)

godot_export_templates_archive = repository_rule(
    doc = """
    Extract the export templates of one Godot platform from an export-template archive.

    Only that platform's templates leave the archive, so a build extracts the templates
    of the platforms it uses, while the repositories of all platforms share one download
    of the archive. A Linux or macOS repository exposes one runtime target per
    CPU and template variant, such as `:linux_x86_64_release` or `:macos_debug`, each
    carrying GodotRuntimeInfo, for godot_runtime_component payloads; an archive without a
    debug template omits the debug target, and cpus describes the macOS layout. An iOS
    repository exposes `:ios_debug` and `:ios_release`, XCFramework imports with the
    dependent frameworks the archive carries; they serve device and simulator slots
    alike. A platform whose templates the archive lacks fails. Extracting, and
    downloading the archive, happen only when a payload is requested.
    """,
    implementation = templates_archive_impl,
    attrs = TEMPLATES_ARCHIVE_RULE_ATTRS,
)
