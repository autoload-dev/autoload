"""
Internal source-generation contract used by generated engine repositories.

Consumer BUILD files should use godot/engine:defs.bzl and repositories.bzl.
Generated repositories with consumer-chosen names load it, so its load visibility
is public.
"""

load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("//godot:providers.bzl", "GodotRuntimeInfo")
load("//godot/private:flags.bzl", "FlagInfo")
load("//godot/private:symbols.bzl", "linked_dsym")

visibility("public")

def _generator_impl(ctx):
    outputs = ctx.outputs.outs
    args = ctx.actions.args()
    args.add("--spec", ctx.file.spec)
    for target, logical in ctx.attr.inputs.items():
        files = target[DefaultInfo].files.to_list()
        if len(files) != 1:
            fail("generator input %s must contain exactly one file" % target.label)
        args.add("--input", logical + "=" + files[0].path)
    for logical, output in zip(ctx.attr.logical_outputs, outputs):
        args.add("--output", logical + "=" + output.path)
    ctx.actions.run(
        executable = ctx.executable._generator,
        arguments = [args],
        inputs = depset([ctx.file.spec] + ctx.files.inputs),
        outputs = outputs,
        mnemonic = "GodotGenerate",
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
        "_generator": attr.label(
            default = Label("//tools/engine:generator"),
            cfg = "exec",
            executable = True,
        ),
    },
)

def godot_source_generator(name, spec, inputs, outs):
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
    """
    _godot_source_generator(
        name = name,
        spec = spec,
        inputs = inputs,
        outs = outs,
        logical_outputs = outs,
        visibility = ["//visibility:private"],
    )

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
    },
)

def _library_impl(ctx):
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
            minimum_os = ctx.attr.minimum_os,
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
    "minimum_os": attr.string(doc = "Deployment target Godot's SCons platform sets, such as 11.0 for macOS arm64; empty where it sets none."),
}

# The deployment-target option each Apple platform's engine compiles against.
_FLOOR_OPTIONS = {
    "macos": "//command_line_option:macos_minimum_os",
    "ios": "//command_line_option:ios_minimum_os",
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
        values[option] = attr.minimum_os
    return values

def _desktop_native_impl(settings, attr):
    # Desktop executables link without Bazel's --strip, as keep_debug_info in symbols.bzl
    # explains; a transition cannot compose two, so this one repeats that setting.
    return _floor(settings, attr) | {"//command_line_option:strip": "never"}

_desktop_native = transition(
    implementation = _desktop_native_impl,
    inputs = _FLOOR_OPTIONS.values(),
    outputs = _FLOOR_OPTIONS.values() + ["//command_line_option:strip"],
)

_engine_library = transition(
    implementation = _floor,
    inputs = _FLOOR_OPTIONS.values(),
    outputs = _FLOOR_OPTIONS.values(),
)

_BINARY_ATTRS = _SOURCE_ATTRS | {
    "deps": attr.label_list(
        doc = "The engine's native executable target, as the only item.",
        mandatory = True,
        allow_empty = False,
        cfg = _desktop_native,
    ),
}

_LIBRARY_ATTRS = _SOURCE_ATTRS | {
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
