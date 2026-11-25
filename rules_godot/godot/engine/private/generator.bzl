"""
Internal source-generation contract used by generated engine repositories.

Consumer BUILD files should use godot/engine:defs.bzl and repositories.bzl.
Generated repositories with consumer-chosen names load it, so its load visibility
is public.

Sections: Source generator, Revision and headers, Source library and binary.
"""

load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("//godot/private:actions.bzl", "PATH_MAPPING")
load("//godot/private:flags.bzl", "FlagInfo")
load("//godot/private:providers.bzl", "GodotRuntimeInfo")
load("//godot/private:symbols.bzl", "linked_dsym")
load("//godot/private:versions.bzl", "IOS_MINIMUM_OS", "MACOS_MINIMUM_OS", "version_below")
load("//godot/private/config:native.bzl", "COMPILATION_MODE", "IOS_MINIMUM_OS_OPTION", "MACOS_MINIMUM_OS_OPTION", "UNSTRIPPED")
load(":define_analysis.bzl", _godot_define_analysis = "godot_define_analysis", _godot_source_defines = "godot_source_defines")
load(
    ":optimization.bzl",
    "BUILD_PROFILE",
    "EDITOR_DEBUG_INPUTS",
    "EDITOR_DEBUG_OUTPUTS",
    "NO_BUILD_PROFILE",
    "OPTIMIZATION_CHECK_ATTRS",
    "OPTIMIZATION_INPUTS",
    "OPTIMIZATION_OUTPUTS",
    "PROFILE_SETTINGS",
    "check_optimization",
    "editor_debugging",
    "engine_optimization",
    "profile_settings",
)

visibility("public")

# The macro definition analysis, for generated engine BUILD files.
godot_define_analysis = _godot_define_analysis

godot_source_defines = _godot_source_defines

# ==== Source generator ========================================================

def _add_files(args, flag, files):
    """Name each logical path's file, as a File so path mapping rewrites its path."""
    for logical, file in files:
        args.add(flag)
        args.add(file, format = logical.replace("%", "%%") + "=%s")

def _single_file(target):
    files = target[DefaultInfo].files.to_list()
    if len(files) != 1:
        fail("generator input %s must contain exactly one file" % target.label)
    return files[0]

def _add_profile(args, flag, target):
    """Name the build profile a profile attribute names, if any: a label flag may name none."""
    profiles = target[DefaultInfo].files.to_list() if target else []
    if len(profiles) > 1:
        fail("%s names more than one build profile" % target.label)
    args.add_all(profiles, before_each = flag)

def _registration(label, engine):
    """The MODULE.bazel line that registers a build profile as a runtime profile."""
    profile = str(label).removeprefix("@@") if str(label).startswith("@@//") else str(label)
    named = "engine = %r, " % engine if engine else ""
    return 'godot_engines.runtime_profile(%sprofile = "%s")' % (named, profile)

def _add_registration(args, ctx):
    """
    Name the line that registers the application's build profile, unless it is registered.

    A registered runtime profile selects its runtime variant, whose graph has its build
    options; another profile may only disable classes.
    """
    if ctx.files.class_profile and not ctx.attr.registered_profile:
        engine = ctx.attr._engine[FlagInfo].value
        args.add("--registration", _registration(ctx.attr.class_profile.label, engine))

def _generator_impl(ctx):
    outputs = ctx.outputs.outs
    args = ctx.actions.args()
    args.add("--spec", ctx.file.spec)
    _add_files(args, "--input", [(logical, _single_file(target)) for target, logical in ctx.attr.inputs.items()])
    _add_files(args, "--output", zip(ctx.attr.logical_outputs, outputs))
    _add_profile(args, "--class-profile", ctx.attr.class_profile)
    _add_registration(args, ctx)
    _add_profile(args, "--recipe-profile", ctx.attr.recipe_profile)
    ctx.actions.run(
        executable = ctx.executable._generator,
        arguments = [args],
        inputs = depset([ctx.file.spec] + ctx.files.inputs + ctx.files.class_profile + ctx.files.recipe_profile),
        outputs = outputs,
        mnemonic = "GodotGenerate",
        # One cache key in every configuration with --experimental_output_paths=strip.
        execution_requirements = PATH_MAPPING,
        progress_message = "Generating %{label}",
    )
    return [DefaultInfo(files = depset(outputs))]

_godot_source_generator = rule(
    implementation = _generator_impl,
    attrs = {
        "spec": attr.label(
            doc = "JSON generator specification emitted by source graph configuration.",
            allow_single_file = [".json"],
            mandatory = True,
        ),
        "inputs": attr.label_keyed_string_dict(
            doc = "Single-file input targets mapped to their upstream logical paths.",
            allow_files = True,
        ),
        "outs": attr.output_list(
            doc = "Declared output paths in the generated repository.",
            mandatory = True,
        ),
        "logical_outputs": attr.string_list(
            doc = "Upstream logical paths corresponding one-to-one to outs.",
            mandatory = True,
        ),
        "class_profile": attr.label(
            doc = "The application's build profile, //godot/private:build_profile, for the class generator; no file without one.",
            allow_files = True,
        ),
        "recipe_profile": attr.label(
            doc = "The recipe's own build profile, whose classes apply without an application's.",
            allow_single_file = [".gdbuild"],
        ),
        "registered_profile": attr.bool(
            doc = "Whether the application's build profile is a registered runtime profile, which may set build options; its runtime variant selects true.",
        ),
        "_engine": attr.label(default = Label("//godot:engine")),
        "_generator": attr.label(
            default = Label("//tools/engine:generator"),
            cfg = "exec",
            executable = True,
        ),
    },
)

def godot_source_generator(name, spec, inputs, outs, class_profile = False, recipe_profile = None, registered_profile = False, **kwargs):
    """
    Declare one upstream source generator as a hermetic Bazel action.

    This low-level macro is used by generated engine repositories. It creates
    the named target with DefaultInfo containing exactly outs; it does not run
    SCons. See [source-built engines](../../engine.md) for the repository-level API.

    Example:
        godot_source_generator(
            name = "generated_header",
            spec = ":header_spec.json",
            inputs = {":version.py": "version.py"},
            outs = ["gen/core/version_generated.gen.h"],
        )

    Args:
        name: Generator target name.
        spec: Label of the JSON specification emitted by source configuration.
        inputs: Single-file targets mapped to upstream logical input paths.
        outs: Declared output paths, also used as upstream logical output paths.
        class_profile: Whether the generator writes core/disabled_classes.gen.h, whose class
            list comes from the application's build profile when one is set.
        recipe_profile: The recipe's own build profile, whose classes apply otherwise.
        registered_profile: Whether the application's build profile is a registered runtime
            profile, which may set build options: a select() on the runtime variants.
        **kwargs: Common attributes, such as tags.
    """
    _godot_source_generator(
        name = name,
        spec = spec,
        inputs = inputs,
        outs = outs,
        logical_outputs = outs,
        class_profile = BUILD_PROFILE if class_profile else None,
        recipe_profile = recipe_profile,
        registered_profile = registered_profile,
        visibility = ["//visibility:private"],
        **kwargs
    )

def _without_build_profile_impl(settings, attr):
    profile = str(settings[BUILD_PROFILE])
    return profile_settings(profile if profile in attr.runtime_profiles else NO_BUILD_PROFILE)

# Resets an application's build profile for the objects that do not read it, unless it is a
# registered runtime profile, whose runtime variant they compile in.
_without_build_profile = transition(
    implementation = _without_build_profile_impl,
    inputs = [BUILD_PROFILE],
    outputs = PROFILE_SETTINGS,
)

def _profile_independent_impl(ctx):
    return [
        cc_common.merge_cc_infos(cc_infos = [dep[CcInfo] for dep in ctx.attr.deps]),
        DefaultInfo(files = depset(transitive = [dep[DefaultInfo].files for dep in ctx.attr.deps])),
    ]

godot_profile_independent = rule(
    doc = """
    Gather the objects of a source-built engine that read no build profile.

    Only the sources that register classes read the class list of a build profile. The
    others reach their objects through this rule, whose transition resets the profile that
    godot_app's build_profile sets, so applications with different profiles share them. A
    registered runtime profile stays: it selects the runtime variant the objects compile
    in. The attribute is named deps so that rules_apple's and rules_android's aspects reach
    the objects through it.
    """,
    implementation = _profile_independent_impl,
    attrs = {
        "deps": attr.label_list(
            doc = "The objects that read no build profile.",
            providers = [CcInfo],
            cfg = _without_build_profile,
        ),
        "runtime_profiles": attr.string_list(
            doc = "The engine's registered runtime profiles, which the transition keeps.",
        ),
    },
)

# ==== Revision and headers ====================================================

def _revision_impl(ctx):
    args = ctx.actions.args()
    args.add("--build-name", ctx.attr.build_name)
    args.add("--inputs-hash", ctx.attr.inputs_hash)
    args.add("--build-output", ctx.outputs.build)
    args.add("--hash-output", ctx.outputs.hash)
    args.add("--timestamp-output", ctx.outputs.timestamp)
    inputs = []
    if ctx.attr._stamp[FlagInfo].value:
        # Only this action reads the workspace status. A new commit changes
        # only the hash and time stamp files, so only the hash generator and
        # what links the engine run again.
        args.add("--status", ctx.info_file)
        inputs.append(ctx.info_file)
    ctx.actions.run(
        executable = ctx.executable._revision,
        arguments = [args],
        inputs = inputs,
        outputs = [ctx.outputs.build, ctx.outputs.hash, ctx.outputs.timestamp],
        mnemonic = "GodotEngineRevision",
        progress_message = "Generating %{label}",
    )

godot_source_revision = rule(
    doc = """
    Write the build name, hash and time stamp a source-built engine names in its version.

    A build with --stamp names the commit its workspace status reports as
    STABLE_GIT_COMMIT, with the build name's suffix -git, and the commit time
    STABLE_GIT_COMMIT_TIMESTAMP reports; otherwise, or without the commit, the
    hash of the engine's declared inputs, with the suffix -bazel, and no time
    stamp.
    """,
    implementation = _revision_impl,
    attrs = {
        "build_name": attr.string(
            doc = "Build name the suffix follows, such as custom.",
            mandatory = True,
        ),
        "inputs_hash": attr.string(
            doc = "Hash of the engine's declared inputs.",
            mandatory = True,
        ),
        "build": attr.output(
            doc = "File with the build name and its suffix, such as custom-git.",
            mandatory = True,
        ),
        "hash": attr.output(
            doc = "File with the hash.",
            mandatory = True,
        ),
        "timestamp": attr.output(
            doc = "File with the commit's Unix time, or 0.",
            mandatory = True,
        ),
        "_revision": attr.label(
            default = Label("//tools/engine:revision"),
            cfg = "exec",
            executable = True,
        ),
        "_stamp": attr.label(
            default = Label("//godot/private:stamp"),
            providers = [FlagInfo],
        ),
    },
)

def _headers_impl(ctx):
    headers = depset(
        ctx.files.hdrs,
        transitive = [dep[CcInfo].compilation_context.headers for dep in ctx.attr.deps],
    )
    return [CcInfo(compilation_context = cc_common.create_compilation_context(headers = headers))]

godot_source_headers = rule(
    doc = """
    Declare files that engine sources include, together with what those files include.

    Each compile action of a source-built engine depends on the headers its source can
    reach, not on every header of the engine, so a header change reruns only the actions
    of the sources that include it, also from a remote or disk cache. Files that include
    each other form one target, since dependencies cannot form cycles.
    """,
    implementation = _headers_impl,
    attrs = {
        "hdrs": attr.label_list(
            doc = "Files of the engine tree or generated files that sources include.",
            allow_files = True,
            mandatory = True,
        ),
        "deps": attr.label_list(
            doc = "The targets of the files these files include.",
            providers = [CcInfo],
        ),
    },
    provides = [CcInfo],
)

# ==== Source library and binary ===============================================

GodotEngineVersionInfo = provider(
    doc = "The version a source-built engine names, carried by the recipe outputs that declare it.",
    fields = {
        "version": "Version and status, such as 4.7.2.stable.",
        "build": "File with the build name, such as custom-git.",
        "hash": "File with the hash.",
        "canonical_version": "Source version.py's canonical Godot version.",
        "platform": "Configured Godot platform, that is the target operating system.",
        "cpu": "Configured target CPU.",
        "environment": "Configured iOS environment, or empty for other operating systems.",
        "role": "Configured role: editor or runtime.",
        "variant": "Configured variant: release or debug for runtimes; empty for editors.",
        "digest": "Source archive digest, such as sha256:<hex>.",
        "customizations": "Requested patches, modules, custom_modules and options, by name.",
        "renderers": "Rendering methods the engine runs, or None where its recipe declares no renderers.",
    },
)

# Below these floors every translation unit warns that libc++ no longer supports the
# platform; Godot's own build targets iOS 14.0 and, on Intel Macs, macOS 10.13.
_LIBCXX_MINIMUM_OS = {
    "macos": MACOS_MINIMUM_OS,
    "ios": IOS_MINIMUM_OS,
}

def _minimum_os(attr):
    """
    The deployment target an Apple engine compiles for: Godot's own, raised to libc++'s floor.

    Applications cannot go below it either, since the runtime reports it.
    """
    floor = _LIBCXX_MINIMUM_OS.get(attr.platform, "")
    if attr.minimum_os and floor and version_below(attr.minimum_os, floor):
        return floor
    return attr.minimum_os

def _library_impl(ctx):
    check_optimization(ctx)
    if len(ctx.attr.deps) != 1:
        fail("%s: deps must name exactly the engine's native library" % ctx.label)
    if (ctx.attr.role == "runtime") != bool(ctx.attr.variant):
        fail("%s: a runtime needs variant release or debug, an editor none" % ctx.label)
    target = ctx.attr.deps[0]
    metadata = {name: getattr(ctx.attr, name) for name in ["canonical_version", "platform", "cpu", "environment", "role", "variant", "digest", "customizations"]}
    result = [
        DefaultInfo(files = target[DefaultInfo].files, runfiles = target[DefaultInfo].default_runfiles),
        GodotEngineVersionInfo(
            version = ctx.attr.version,
            build = ctx.file.build,
            hash = ctx.file.hash,
            renderers = ctx.attr.renderers if ctx.attr.declares_renderers else None,
            **metadata
        ),
    ]
    if ctx.attr.role == "runtime":
        result.append(GodotRuntimeInfo(
            executable = target[DefaultInfo].files_to_run.executable,
            files = target[DefaultInfo].files,
            version = ctx.attr.canonical_version,
            platform = ctx.attr.platform,
            cpu = ctx.attr.cpu,
            environment = ctx.attr.environment,
            variant = ctx.attr.variant,
            facts_source = "source",
            origin = str(ctx.label),
            bundle_files = {},
            debug_symbols = linked_dsym(target),
            minimum_os = _minimum_os(ctx.attr),
        ))
    if CcInfo in target:
        result.append(target[CcInfo])
    if OutputGroupInfo in target:
        result.append(target[OutputGroupInfo])
    return result

def _binary_impl(ctx):
    target = ctx.attr.deps[0]
    native = target[DefaultInfo]
    if not native.files_to_run.executable:
        fail("A source-built engine binary must provide its executable")
    executable = ctx.actions.declare_file(ctx.label.name)
    ctx.actions.symlink(output = executable, target_file = native.files_to_run.executable, is_executable = True)
    return [DefaultInfo(
        executable = executable,
        files = depset([executable], transitive = [native.files]),
        runfiles = native.default_runfiles,
    )] + _library_impl(ctx)[1:]

_SOURCE_ATTRS = {
    # A single-item deps list, not a named label: the Apple and Android aspects replayed on
    # runtime payloads traverse deps into the native graph.
    "deps": attr.label_list(
        doc = "The engine's native library target, as the only item.",
        mandatory = True,
        allow_empty = False,
    ),
    "canonical_version": attr.string(doc = "Canonical version derived from source version.py.", mandatory = True),
    "platform": attr.string(doc = "Godot platform the source graph is configured for: the target operating system.", mandatory = True),
    "cpu": attr.string(doc = "Target CPU the source graph is configured for.", mandatory = True),
    "environment": attr.string(doc = "iOS environment the source graph is configured for, or empty for other operating systems."),
    "role": attr.string(doc = "Whether the source graph builds the editor or a runtime.", mandatory = True, values = ["editor", "runtime"]),
    "variant": attr.string(doc = "Variant of a runtime: release or debug; empty for the editor.", values = ["", "release", "debug"]),
    "version": attr.string(
        doc = "Version and status the library names, such as 4.7.2.stable.",
        mandatory = True,
    ),
    "build": attr.label(
        doc = "The build file of the engine's godot_source_revision.",
        mandatory = True,
        allow_single_file = True,
    ),
    "hash": attr.label(
        doc = "The hash file of the engine's godot_source_revision.",
        mandatory = True,
        allow_single_file = True,
    ),
    "digest": attr.string(doc = "Source archive digest, such as sha256:<hex>."),
    "customizations": attr.string_list_dict(doc = "Requested patches, modules, custom_modules and options."),
    "renderers": attr.string_list(doc = "Rendering methods the engine runs, where declares_renderers is set."),
    "declares_renderers": attr.bool(doc = "Whether the recipe declares its renderers, so applications check their projects against them."),
    "minimum_os": attr.string(doc = "Deployment target Godot's SCons platform sets, such as 11.0 for macOS arm64; empty where it sets none. Apple engines compile for at least libc++'s floor, iOS 15.0 and macOS 11.0."),
}

# The deployment-target option each Apple platform's engine compiles against.
_FLOOR_OPTIONS = {
    "macos": MACOS_MINIMUM_OS_OPTION,
    "ios": IOS_MINIMUM_OS_OPTION,
}

def _floor(settings, attr):
    """
    The deployment targets a recipe's native graph compiles for.

    A macOS or iOS recipe compiles for Godot's own floor, whatever the build's or the
    linking application's minimum says: one engine build serves every application, and an
    application's minimum stays its bundle's and its extension libraries'.
    """
    values = {option: settings[option] for option in _FLOOR_OPTIONS.values()}
    option = _FLOOR_OPTIONS.get(attr.platform)
    if option and attr.minimum_os:
        values[option] = _minimum_os(attr)
    return values

_ENGINE_INPUTS = _FLOOR_OPTIONS.values() + OPTIMIZATION_INPUTS

_ENGINE_OUTPUTS = _FLOOR_OPTIONS.values() + OPTIMIZATION_OUTPUTS

def _engine_library_impl(settings, attr):
    return _floor(settings, attr) | engine_optimization(settings, attr)

_engine_library = transition(
    implementation = _engine_library_impl,
    inputs = _ENGINE_INPUTS,
    outputs = _ENGINE_OUTPUTS,
)

def _desktop_native_impl(settings, attr):
    # Desktop executables link without Bazel's --strip, as keep_debug_info in symbols.bzl
    # explains; a transition cannot compose two, so this one repeats that setting.
    debugging = editor_debugging(settings, attr)
    debugged = dict(settings) | {COMPILATION_MODE: debugging[COMPILATION_MODE]}
    return _engine_library_impl(debugged, attr) | UNSTRIPPED | debugging

# Editors are desktop executables, so this transition also applies editor_debug.
_desktop_native = transition(
    implementation = _desktop_native_impl,
    inputs = _ENGINE_INPUTS + EDITOR_DEBUG_INPUTS,
    outputs = _ENGINE_OUTPUTS + UNSTRIPPED.keys() + EDITOR_DEBUG_OUTPUTS,
)

_BINARY_ATTRS = _SOURCE_ATTRS | OPTIMIZATION_CHECK_ATTRS | {
    "deps": attr.label_list(
        doc = "The engine's native executable target, as the only item.",
        mandatory = True,
        allow_empty = False,
        cfg = _desktop_native,
    ),
}

_LIBRARY_ATTRS = _SOURCE_ATTRS | OPTIMIZATION_CHECK_ATTRS | {
    "deps": attr.label_list(
        doc = "The engine's native library target, as the only item.",
        mandatory = True,
        allow_empty = False,
        cfg = _engine_library,
    ),
}

godot_source_library = rule(
    doc = "Forward a source-built engine library with its configured provenance, CcInfo and output groups.",
    implementation = _library_impl,
    attrs = _LIBRARY_ATTRS,
)

godot_source_binary = rule(
    doc = "Expose an executable source-built engine with its configured provenance, CcInfo and output groups.",
    implementation = _binary_impl,
    attrs = _BINARY_ATTRS,
    executable = True,
)
