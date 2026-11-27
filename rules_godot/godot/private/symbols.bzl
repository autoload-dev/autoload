"""Stripped native code for applications and its unstripped original as debug symbols."""

load("@apple_support//lib:apple_support.bzl", "apple_support")
load("@bazel_skylib//rules:common_settings.bzl", "BuildSettingInfo")
load("@rules_cc//cc:find_cc_toolchain.bzl", "find_cc_toolchain")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("//godot/private/config:native.bzl", "LIBRARY_OPTIONS")

visibility("//godot/...")

def _keep_debug_info_impl(_settings, _attr):
    # Transitions read --strip as an opaque value, so they cannot leave the
    # configurations alone whose links would not strip.
    return LIBRARY_OPTIONS

# Native code that applications package; LIBRARY_OPTIONS in native.bzl says why it unstrips.
keep_debug_info = transition(
    implementation = _keep_debug_info_impl,
    inputs = [],
    outputs = LIBRARY_OPTIONS.keys(),
)

# Rules that strip native code add these private attributes, the C/C++
# toolchain (use_cc_toolchain(mandatory = False)) and the cpp fragment.
STRIP_ATTRS = {
    "_strip": attr.label(
        default = Label("//godot/private:strip"),
        providers = [BuildSettingInfo],
    ),
    "_native_symbols": attr.label(
        default = Label("//tools/platforms:native_symbols"),
        cfg = "exec",
        executable = True,
    ),
}

# Rules that write a ZIP of debug symbols add these private attributes.
SYMBOLS_ZIP_ATTRS = {
    "_symbols_packager": attr.label(
        default = Label("//tools/platforms:package_symbols"),
        cfg = "exec",
        executable = True,
    ),
}

def packaged(ctx, files, macho = False):
    """
    Return the native code to package: stripped when Bazel's --strip asks for it.

    --strip strips always, or with sometimes in fastbuild. One action strips
    every file with the target's C/C++ toolchain; symbols that dynamic linking
    needs stay, and so does the build ID or UUID that crash reporters match
    symbols by. Files that are neither ELF nor Mach-O, such as a runtime's
    launcher script, are copied.

    Args:
        ctx: Rule context with STRIP_ATTRS and the C/C++ toolchain.
        files: Dictionary of output paths, relative to the rule's package, to
            unstripped Files.
        macho: Whether the files are Mach-O rather than ELF.

    Returns:
        A dictionary of the same paths to the Files to package.
    """
    if not files or not ctx.attr._strip[BuildSettingInfo].value:
        return files
    cc_toolchain = find_cc_toolchain(ctx, mandatory = False)
    if not cc_toolchain:
        fail(
            "Stripping native code of %s requires a C/C++ toolchain for the " % ctx.label +
            "target platform; build with --strip=never to package it unstripped",
        )
    features = cc_common.configure_features(
        ctx = ctx,
        cc_toolchain = cc_toolchain,
        requested_features = ctx.features,
        unsupported_features = ctx.disabled_features,
    )
    if not cc_common.action_is_enabled(feature_configuration = features, action_name = "strip"):
        fail("The C/C++ toolchain of %s has no strip action" % ctx.label)
    outputs = {path: ctx.actions.declare_file(path) for path in files}
    args = ctx.actions.args()
    args.add("strip")
    args.add("--tool", cc_common.get_tool_for_action(
        feature_configuration = features,
        action_name = "strip",
    ))

    # As Xcode strips dynamic libraries and the Android Gradle plugin strips
    # JNI libraries: keep the global symbols dynamic linking needs.
    args.add_all(["-S", "-x"] if macho else ["--strip-unneeded"], format_each = "--option=%s")
    for path, file in files.items():
        args.add("--input", file)
        args.add("--output", outputs[path])
    ctx.actions.run(
        executable = ctx.executable._native_symbols,
        arguments = [args],
        env = cc_common.get_environment_variables(
            feature_configuration = features,
            action_name = "strip",
            variables = cc_common.create_compile_variables(
                cc_toolchain = cc_toolchain,
                feature_configuration = features,
            ),
        ),
        inputs = depset(files.values(), transitive = [cc_toolchain.all_files]),
        outputs = outputs.values(),
        use_default_shell_env = True,
        mnemonic = "GodotStrip",
        progress_message = "Stripping %{label}",
    )
    return outputs

def dsym(ctx, file, path):
    """
    Extract the DWARF of a Mach-O file into a .dSYM bundle with dsymutil.

    The DWARF of a linked file stays in the object files its debug map points
    to, which are not inputs here, so the .dSYM names functions without file
    and line information; prefer linked_dsym() where the linker wrote one.
    Other files leave the directory empty, and the symbol ZIP omits it.

    Args:
        ctx: Rule context with STRIP_ATTRS, apple_support.action_required_attrs()
            and the apple fragment.
        file: Unstripped Mach-O File.
        path: Output path of the .dSYM directory relative to the rule's package.

    Returns:
        The .dSYM directory.
    """
    output = ctx.actions.declare_directory(path)
    apple_support.run(
        actions = ctx.actions,
        xcode_config = ctx.attr._xcode_config[apple_common.XcodeVersionConfig],
        apple_fragment = ctx.fragments.apple,
        executable = ctx.executable._native_symbols,
        arguments = ["dsym", "--input", file.path, "--output", output.path],
        inputs = [file],
        outputs = [output],
        mnemonic = "GodotDsym",
        progress_message = "Generating %%{label} (%s)" % file.basename,
    )
    return output

def linked_dsym(target):
    """
    Return the .dSYM directory the linker wrote for a target's Mach-O file, or None.

    rules_cc's cc_binary writes it with --apple_generate_dsym in its dsyms
    output group. The link action has the object files, so the dSYM carries
    their DWARF, file and line information included, which dsym() cannot
    recover from the linked file alone.

    Args:
        target: Target that supplies a native executable or library.

    Returns:
        The .dSYM directory, or None.
    """
    if OutputGroupInfo not in target or not hasattr(target[OutputGroupInfo], "dsyms"):
        return None
    dsyms = target[OutputGroupInfo].dsyms.to_list()
    return dsyms[0] if len(dsyms) == 1 else None

def symbols_zip(ctx, entries, output):
    """
    Write a ZIP of debug symbols at the paths a crash reporter expects.

    Args:
        ctx: Rule context with SYMBOLS_ZIP_ATTRS.
        entries: Dictionary of ZIP paths to Files or directories; files that are
            neither ELF nor Mach-O are left out.
        output: Declared ZIP File.
    """
    manifest = ctx.actions.declare_file(output.basename + ".json", sibling = output)
    ctx.actions.write(manifest, json.encode([
        {"destination": destination, "source": file.path}
        for destination, file in sorted(entries.items())
    ]))
    ctx.actions.run(
        executable = ctx.executable._symbols_packager,
        arguments = ["--manifest", manifest.path, "--output", output.path],
        inputs = [manifest] + entries.values(),
        outputs = [output],
        mnemonic = "GodotDebugSymbols",
        progress_message = "Bundling %{label}",
    )
