"""
The implementations of the source repository rules in godot/engine/private:repositories.bzl.

A recipe and the Android shell link the files of their source's engine tree
(tree_repository.bzl) instead of extracting the sources, and patch copies of their own of
the files their patches touch: their repositories hold what they generate and change.

Errors go through `_fail`, so a Starlark unit test with a mocked repository_ctx collects
them; an implementation returns after an error.

Sections: Engine source, Tree links, Engine build, Android shell.
"""

load("//godot/private:supply_chain.bzl", "source_purl", "write_package_metadata")
load("//godot/private:versions.bzl", "require_supported_source_version")
load("//godot/private/config:settings.bzl", "OPERATING_SYSTEM_CONSTRAINTS")
load("//godot/private/engine:profiles.bzl", "engine_profile")
load(":engine_tools.bzl", "engine_tool")

visibility(["//godot/..."])

# ==== Engine source ===========================================================

_ARCHIVE_SUFFIXES = [".tar.gz", ".tgz", ".tar.xz", ".tar.bz2", ".tar.zst", ".zip"]

def _archive_name(urls, _fail):
    path = urls[0].partition("?")[0]
    for suffix in _ARCHIVE_SUFFIXES:
        if path.endswith(suffix):
            return "source" + suffix
    _fail("godot_engine_source cannot tell the archive type of %s; supported: %s" % (urls[0], ", ".join(_ARCHIVE_SUFFIXES)))
    return None

def engine_source_impl(ctx, *, _fail = fail):
    """
    Download one source archive and describe it in `source.json`.

    Args:
        ctx: Repository rule context of godot_engine_source.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        The repository's metadata: reproducible when the archive is digest-pinned.
    """
    if not ctx.attr.urls:
        _fail("%s: urls must list at least one mirror of the archive" % ctx.attr.name)
        return None
    if not require_supported_source_version(ctx.attr.version, _fail = _fail):
        return None
    archive = _archive_name(ctx.attr.urls, _fail)
    if not archive:
        return None
    ctx.download(url = ctx.attr.urls, output = archive, sha256 = ctx.attr.sha256)
    ctx.file("source.json", json.encode_indent({
        "archive": archive,
        "sha256": ctx.attr.sha256,
        "strip_prefix": ctx.attr.strip_prefix,
        "version": ctx.attr.version,
        # Mirror URLs are not identity.
        "origin": "sha256:%s %s" % (ctx.attr.sha256, ctx.attr.version),
    }) + "\n")
    ctx.file("BUILD.bazel", 'exports_files(["source.json", %r])\n' % archive)

    # The digest-pinned archive determines the contents, so Bazel's repo contents cache,
    # local or remote, may reuse them.
    return ctx.repo_metadata(reproducible = bool(ctx.attr.sha256))

# ==== Tree links ==============================================================

def _read_tree(ctx):
    """Read the `tree.json` descriptor of the repository's engine tree, whose digest keys it."""
    return json.decode(ctx.read(ctx.path(ctx.attr.tree)))

def _write_tree_metadata(ctx, tree, bundled = False):
    """
    Give the repository's targets the package metadata of the tree's source archive.

    With bundled, each library the tree's COPYRIGHT.txt lists is a package of its own, for
    the repository's targets that hold the engine.
    """
    directory = ctx.path(ctx.attr.tree).dirname
    write_package_metadata(
        ctx,
        source_purl("godot", tree["version"], sha256 = tree["sha256"]),
        "%s/LICENSE.txt" % directory,
        copyright = "%s/COPYRIGHT.txt" % directory if bundled else None,
    )

def _link_tree(ctx, path = ""):
    """
    Link the engine tree's files below path, or all of them, into this repository; an error or None.

    The repository owns copies of the files its patches touch, which it patches, and of
    class_db.h, which it scopes: the tree stays the source archive's.
    """
    tool = engine_tool(ctx, ctx.attr._tree_link)
    command = tool.command + [
        "--tree",
        str(ctx.path(ctx.attr.tree).dirname),
        "--recipe",
        ".",
        "--path",
        path,
        "--patch-strip",
        str(ctx.attr.patch_strip),
    ]
    for patch in ctx.attr.patches:
        patch_file = ctx.path(patch)
        ctx.watch(patch_file)
        command.extend(["--patch", str(patch_file)])
    result = ctx.execute(command, environment = tool.environment)
    if result.return_code:
        return "%s: linking the engine tree failed:\n%s\n%s" % (ctx.attr.name, result.stdout, result.stderr)
    return None

def _watch_link_tools(ctx):
    """Link the tree again when the code that links, patches and scopes it changes."""
    ctx.watch(ctx.path(ctx.attr._tree))
    ctx.watch(ctx.path(ctx.attr._tree_link))
    ctx.watch(ctx.path(ctx.attr._class_db))
    ctx.watch(ctx.path(ctx.attr._patches))

# ==== Engine build ============================================================

_SCONS_PLATFORMS = {"linux": "linuxbsd", "macos": "macos", "android": "android", "ios": "ios"}

# The environment variables Godot's build scripts read during configuration that change
# the captured graph: cross toolchains, a compiler launcher, the version status and
# host package lookup. The SDK locations they also read only locate the toolchain that
# Godot's version pins, and the captured graph leaves those paths out.
_CONFIGURE_ENVIRONMENT = [
    "APPLE_LLVM_CROSS",
    "CCACHE",
    "GODOT_VERSION_STATUS",
    "MACPORTS_PREFIX",
    "OSXCROSS_IOS",
    "OSXCROSS_ROOT",
    "PKG_CONFIG_PATH",
]

# The operating system of the execution platform that pins a recipe: one Godot accepts for the
# recipe's platform. Android recipes configure on any, against a stand-in SDK.
_PIN_EXECUTION = {
    "ios": "macos",
    "linux": "linux",
    "macos": "macos",
}

def _unpinned_message(ctx):
    """The error of a recipe's engine targets while the lock file has no current pin for it."""
    return (
        "%s: the lock file %s {reason} recipe %s; pin it with `bazel run %s`, on a host that " +
        "can execute actions for %s recipes, such as one with remote execution"
    ) % (ctx.attr.name, ctx.attr.lock_file, ctx.attr.lock_key, ctx.attr.repin, ctx.attr.platform)

def _pin_sources(ctx):
    """The globs of the recipe repository's files a pin action copies into its source tree."""
    sources = ["_custom_modules/**", "_custom_modules.json", "_scons/**"]
    if ctx.attr.runtime_profiles:
        sources.append("_variant_*.gdbuild")
    return sources

def profile_options(options, version):
    """
    Return a build profile's options as the recipe's Godot version reads them.

    The editor writes switches that a version's SCons lacks, such as 4.7's renderer
    switches, which change nothing there; a version may also need an option another one
    implies.

    Args:
        options: A profile's disabled_build_options.
        version: The canonical Godot version of the recipe's sources.

    Returns:
        The options without the version's editor-only switches, with the options they imply.
    """
    table = engine_profile(version)["build_profile"]
    result = {key: value for key, value in options.items() if key not in table["editor_only_options"]}
    for implied in table["implied_options"]:
        if version in implied["versions"] and result.get(implied["option"]):
            result = implied["implies"] | result
    return result

def _write_profile(ctx, path, profile, version):
    """Write a build profile with the options the recipe's version reads."""
    options = profile_options(profile.get("disabled_build_options", {}), version)
    ctx.file(path, json.encode_indent(profile | {"disabled_build_options": options}) + "\n")

# The longest a configure-only SCons run of a recipe may take, in seconds: a cold run on a
# slow host takes minutes.
_CONFIGURE_TIMEOUT = 1800

# Where a recipe without a lock file configures its runtime variants, one pin each.
_VARIANT_PINS = "_variant_pins"

def _variant_profiles(ctx, version):
    """
    Write each runtime variant's build profile and return its runtime profile and path.

    A variant's profile has its runtime profile's build options, which configure beside the
    recipe's build_options; its classes stay with the application, whose profile the class
    generator reads.
    """
    variants = []
    for index, label in enumerate(sorted(ctx.attr.runtime_profiles)):
        path = "_variant_%d.gdbuild" % index
        options = json.decode(ctx.attr.runtime_profiles[label])
        _write_profile(ctx, path, {"type": "build_profile", "disabled_build_options": options}, version)
        variants.append((label, path))
    return variants

def _profile_arguments(path):
    """The configure arguments of a build profile, none without one."""
    return ["--build-profile", path] if path else []

def _variant_arguments(ctx, command, variants):
    """
    The configure arguments that render a recipe's runtime variants beside its graph.

    A recipe without a lock file configures each variant first.
    """
    arguments = ["--build-profile-label", str(ctx.attr._build_profile_label)]
    if variants and not ctx.attr.lock_file:
        arguments.extend(_configure_variants(ctx, command, variants))
    for label, path in variants:
        arguments.extend(["--runtime-profile", label, path])
    return arguments

def _quoted(argument):
    """A shell word for an argument."""
    return "'" + argument.replace("'", "'\\''") + "'"

def _configure_variants(ctx, command, variants):
    """
    Configure the runtime variants of a recipe without a lock file, together, one pin each.

    A variant that cannot configure, such as one whose profile contradicts the recipe's
    build options, records its output instead; only the applications that select it fail.
    """
    lines = []
    for index, (_, path) in enumerate(variants):
        pin = "%s/%d" % (_VARIANT_PINS, index)
        configure = command + _profile_arguments(path) + ["--pin-output", pin + ".json"]
        lines.append("(%s > %s.log 2>&1 || mv %s.log %s.error) &" % (
            " ".join([_quoted(argument) for argument in configure]),
            pin,
            pin,
            pin,
        ))
    ctx.file(_VARIANT_PINS + "/configure.sh", "\n".join(lines + ["wait", ""]))
    ctx.execute(
        ["/bin/sh", _VARIANT_PINS + "/configure.sh"],
        environment = engine_tool(ctx, ctx.attr._configure).environment,
        timeout = _CONFIGURE_TIMEOUT,
        quiet = True,
    )
    return ["--variant-pins", str(ctx.path(_VARIANT_PINS))]

def _selection_arguments(ctx):
    """Return the configure arguments of Godot's default modules and renderers."""
    arguments = ["--default-modules"] if ctx.attr.default_modules else []
    if ctx.attr.renderers:
        arguments.extend(["--renderers", ",".join(ctx.attr.renderers)])
    return arguments

def _repository(label):
    """The canonical repository of a label, such as @@platforms, for generated BUILD files."""
    return str(label).split("//")[0]

def _pin_target(ctx, tree, arguments, name = "pin"):
    """The :pin target that configures this recipe, or one of its variants, on its execution platform."""
    execution = _PIN_EXECUTION.get(ctx.attr.platform)
    constraints = [str(OPERATING_SYSTEM_CONSTRAINTS[execution])] if execution else []
    return """
load(%r, "godot_recipe_pin")

godot_recipe_pin(
    name = %r,
    archive = %r,
    strip_prefix = %r,
    patches = %r,
    srcs = glob(%r),
    arguments = %r,
    exec_compatible_with = %r,
    tags = ["manual"],
    visibility = ["//visibility:public"],
)
""" % (
        str(ctx.attr._pin_bzl),
        name,
        tree["archive"],
        tree["strip_prefix"],
        [str(patch) for patch in ctx.attr.patches],
        _pin_sources(ctx),
        arguments,
        constraints,
    )

def _pin_targets(ctx, tree, arguments, variants):
    """The :pin target of the recipe and the :pin_variant_<n> target of each runtime variant."""
    return _pin_target(ctx, tree, arguments) + "".join([
        _pin_target(ctx, tree, arguments + _profile_arguments(path), name = "pin_variant_%d" % index)
        for index, (_, path) in enumerate(variants)
    ])

def _watch_tools(ctx):
    """Configure again when the code that captures or renders a recipe's graph changes."""
    ctx.watch(ctx.path(ctx.attr._configure))
    ctx.watch(ctx.path(ctx.attr._compile_options))
    ctx.watch(ctx.path(ctx.attr._generator_inputs))
    ctx.watch(ctx.path(ctx.attr._lock))
    ctx.watch(ctx.path(ctx.attr._recipe_options))
    ctx.watch(ctx.path(ctx.attr._module_graph))
    ctx.watch(ctx.path(ctx.attr._source_tree))
    ctx.watch(ctx.path(ctx.attr._render))
    ctx.watch(ctx.path(ctx.attr._build_profile))
    ctx.watch(ctx.path(ctx.attr._define_analysis))
    ctx.watch(ctx.path(ctx.attr._include_graph))
    ctx.watch(ctx.path(ctx.attr._variants))
    ctx.watch(ctx.path(ctx.attr._generators))
    ctx.watch(ctx.path(ctx.attr._build_file))
    ctx.watch(ctx.path(ctx.attr._custom_modules))
    _watch_link_tools(ctx)

def _recipe_error(ctx):
    """Why a recipe's attributes cannot configure it, or None."""
    is_ios = ctx.attr.platform == "ios"
    if is_ios and not ctx.attr.environment:
        return "%s: iOS recipes need environment = \"device\" or \"simulator\"" % ctx.attr.name
    if ctx.attr.environment and not is_ios:
        return "%s: environment is only valid for iOS recipes" % ctx.attr.name
    if not ctx.attr.lock_file:
        return None
    if not ctx.attr.lock_key or not ctx.attr.repin:
        return "%s: lock_file needs lock_key and repin, as the godot_engines extension sets them" % ctx.attr.name
    return None

def _read_environment(ctx):
    """Read the host environment a configuration here reads; a pinned recipe reads none."""
    if ctx.attr.lock_file:
        return
    imported = ctx.attr.build_options.get("import_env_vars", "").split(",")
    for name in _CONFIGURE_ENVIRONMENT + [name for name in imported if name]:
        ctx.getenv(name)

def _recipe_arguments(ctx, tree):
    """The recipe's own configure arguments, which its pin action repeats on another host."""
    arguments = [
        "--platform",
        _SCONS_PLATFORMS[ctx.attr.platform],
        "--cpu",
        ctx.attr.cpu,
        "--build-target",
        ctx.attr.build_target,
        "--environment",
        ctx.attr.environment,
        "--expected-version",
        tree["version"],
        "--modules",
        ",".join(ctx.attr.enabled_modules),
        "--build-name",
        ctx.attr.build_name,
        "--source-sha256",
        tree["sha256"],
        "--patch-strip",
        str(ctx.attr.patch_strip),
    ]
    arguments.extend(_selection_arguments(ctx))
    for option in sorted(ctx.attr.build_options):
        arguments.extend(["--option", option + "=" + ctx.attr.build_options[option]])
    return arguments

def _host_command(ctx, arguments):
    """The configure command on this host: the tool's module, its paths, then the recipe's arguments."""
    return engine_tool(ctx, ctx.attr._configure).command + [
        "--source",
        str(ctx.path(".")),
        "--scons",
        str(ctx.path("_scons")),
        "--generator-bzl",
        str(ctx.attr._generator),
        "--cc-repository",
        _repository(ctx.attr._cc_rules),
        "--platforms-repository",
        _repository(ctx.attr._platforms_constraint),
        "--apple-repository",
        _repository(ctx.attr._apple_constraint),
        "--swift-repository",
        _repository(ctx.attr._swift_library),
    ] + arguments

def _watch_custom_module(ctx, target, directory, watched):
    """Prepare the recipe again when a module's directory listings or graph files change."""
    for path in watched["directories"]:
        listed = directory if path == "." else ctx.path(target.same_package_label(path))
        listed.readdir(watch = "yes")
    for path in watched["files"]:
        ctx.watch(target.same_package_label(path))

def _add_custom_modules(ctx, command, arguments):
    """
    Give the recipe its custom modules' structure and name them in both argument lists.

    The repository holds the files that shape the graph, watched, and placeholders of the
    code, which a build takes from each module's target (custom_modules.py). Returns an
    error or None, and the placeholders, which the repository deletes after configuring.
    """
    if not ctx.attr.custom_modules:
        return None, []
    declarations = []
    modules = []
    for target, name in ctx.attr.custom_modules.items():
        config = ctx.path(target.same_package_label("config.py"))
        if not config.exists:
            return "custom module %s: the package of its target must hold the module's config.py" % target, []
        modules.append((target, name, config.dirname))
        declarations.extend(["--module", name, str(config.dirname), str(target)])
        for names in [command, arguments]:
            names.extend(["--custom-module-name", name])
    tool = engine_tool(ctx, ctx.attr._custom_modules)
    result = ctx.execute(
        tool.command + ["--recipe", "."] + declarations,
        environment = tool.environment,
    )
    if result.return_code:
        return "%s: preparing the custom modules failed:\n%s\n%s" % (ctx.attr.name, result.stdout, result.stderr), []
    prepared = json.decode(result.stdout)
    for target, name, directory in modules:
        _watch_custom_module(ctx, target, directory, prepared["modules"][name])
    return None, prepared["placeholders"]

def _lock_arguments(ctx):
    """The configure arguments that render a pinned recipe from its lock file; none without."""
    if not ctx.attr.lock_file:
        return []
    lock = ctx.path(ctx.attr.lock_file)
    ctx.watch(lock)
    return [
        "--lock",
        str(lock),
        "--recipe",
        ctx.attr.lock_key,
        "--unpinned-message",
        _unpinned_message(ctx),
        "--pin-bzl",
        str(ctx.attr._pin_bzl),
    ]

def _patch_arguments(ctx):
    """The recipe's patches, whose contents its pin digest covers."""
    arguments = []
    for patch in ctx.attr.patches:
        arguments.extend(["--patch", str(ctx.path(patch))])
    return arguments

def _finish(ctx, tree, arguments, variants):
    """Add a pinned recipe's pin targets, or drop what a configuration here leaves behind."""
    if ctx.attr.lock_file:
        ctx.file("BUILD.bazel", ctx.read("BUILD.bazel") + _pin_targets(ctx, tree, arguments, variants))
    else:
        # Upstream dumps its configured environment, with this host's SDK paths, for editor
        # integrations; no target reads it.
        ctx.delete(".scons_env.json")
    ctx.file("WORKSPACE.bazel", "")

def engine_build_impl(ctx, *, _fail = fail):
    """
    Link one source recipe to its engine tree, patch it and render its build graph.

    Without a lock file the recipe is configured here, with SCons; with one, the graph comes
    from the recipe's pin, and nothing is configured on this host.

    Args:
        ctx: Repository rule context of godot_engine_build.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        The repository's metadata: reproducible except for unpinned Linux recipes.
    """
    _watch_tools(ctx)
    error = _recipe_error(ctx)
    if error:
        _fail(error)
        return None
    _read_environment(ctx)
    tree = _read_tree(ctx)
    error = _link_tree(ctx)
    if error:
        _fail(error)
        return None
    arguments = _recipe_arguments(ctx, tree)
    command = _host_command(ctx, arguments)
    error, placeholders = _add_custom_modules(ctx, command, arguments)
    if error:
        _fail(error)
        return None
    command.extend(_patch_arguments(ctx))
    variants = _variant_profiles(ctx, tree["version"])
    command = command + _variant_arguments(ctx, command, variants) + _lock_arguments(ctx)
    result = ctx.execute(
        command,
        environment = engine_tool(ctx, ctx.attr._configure).environment,
        timeout = _CONFIGURE_TIMEOUT,
        quiet = True,
    )
    if result.return_code:
        _fail("Godot graph configuration failed:\n%s\n%s" % (result.stdout, result.stderr))
        return None
    for placeholder in placeholders:
        ctx.delete(placeholder)
    _finish(ctx, tree, arguments, variants)
    _write_tree_metadata(ctx, tree, bundled = True)

    # A pinned recipe depends only on the recipe, the sources and the lock file, and Android
    # and Apple configurations only on those and the environment recorded above, so Bazel's
    # repo contents cache, local or remote, may reuse them. Godot's Linux configuration
    # chooses warning flags by the host compiler's version, so unpinned Linux recipes
    # configure on each host.
    return ctx.repo_metadata(reproducible = bool(ctx.attr.lock_file) or ctx.attr.platform != "linux")

# ==== Android shell ===========================================================

def _library_version(version):
    """The version name Godot's Gradle build gives the Android shell library, such as 4.7.2.stable."""
    number, _, status = version.partition("-")
    return number + "." + (status or "stable")

_BUILD_CONFIG = """package {package};

public final class BuildConfig {{
  public static final boolean DEBUG = {debug};
  public static final String LIBRARY_PACKAGE_NAME = "{package}";
  public static final String BUILD_TYPE = "{variant}";
  public static final String FLAVOR = "template";
}}
"""

def android_shell_impl(ctx, *, _fail = fail):
    """
    Link the Android shell library of the engine tree, patch it and prepare it.

    Args:
        ctx: Repository rule context of godot_android_shell.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        The repository's metadata: reproducible.
    """
    tree = _read_tree(ctx)
    _watch_link_tools(ctx)
    shell = engine_profile(tree["version"].partition("-")[0])["android_shell"]
    library = shell["library"]
    error = _link_tree(ctx, library)
    if error:
        _fail(error)
        return None
    manifest = ctx.read(library + "/src/main/AndroidManifest.xml")
    if shell["version_placeholder"] not in manifest or "<application>" not in manifest:
        _fail("%s: the Android shell manifest of Godot %s lacks the expected placeholder" % (ctx.attr.name, tree["version"]))
        return None
    manifest = manifest.replace(shell["version_placeholder"], _library_version(tree["version"]))
    manifest = manifest.replace(
        "<application>",
        '<uses-sdk android:minSdkVersion="%d" />\n\n    <application>' % shell["min_sdk"],
        1,
    )
    ctx.file("AndroidManifest.xml", manifest)
    path = shell["package"].replace(".", "/")
    for variant in ["debug", "release"]:
        ctx.file("_build_config/%s/%s/BuildConfig.java" % (variant, path), _BUILD_CONFIG.format(
            package = shell["package"],
            debug = "true" if variant == "debug" else "false",
            variant = variant,
        ))
    ctx.template("BUILD.bazel", ctx.attr._build_template, substitutions = {
        "{KOTLIN_ANDROID}": repr(str(ctx.attr._kotlin_android)),
        "{KOTLIN_CORE}": repr(str(ctx.attr._kotlin_core)),
        "{LIBRARY}": repr(library),
        "{PACKAGE}": repr(shell["package"]),
        "{PACKAGE_PATH}": repr(path),
        "{JAVA_LEVEL}": repr(shell["java_level"]),
        "{DEPS}": repr([str(Label(dep)) for dep in shell["deps"]]),
    })
    _write_tree_metadata(ctx, tree)

    # The engine tree determines the contents, so Bazel's repo contents cache, local or
    # remote, may reuse them.
    return ctx.repo_metadata(reproducible = True)
