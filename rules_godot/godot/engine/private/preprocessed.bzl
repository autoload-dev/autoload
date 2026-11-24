"""
Prototype: compile an engine source in two actions, preprocessing and compiling.

The preprocess action sees the source, its headers and every macro definition. The
compile action sees only the preprocessed text and the flags that are not macro
definitions, so its cache key changes only when the preprocessed text does.
"""

load("@rules_cc//cc:action_names.bzl", "ACTION_NAMES")
load("@rules_cc//cc:find_cc_toolchain.bzl", "find_cc_toolchain", "use_cc_toolchain")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_helper.bzl", "cc_helper")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")

visibility("public")

_PREPROCESSOR_PREFIXES = ("-D", "-U")

def _package_paths(ctx, directories):
    root = ctx.label.workspace_root
    paths = []
    for directory in directories:
        source = root if directory == "." else root + "/" + directory
        paths += [source, ctx.bin_dir.path + "/" + source]
    return paths

def _command(ctx, toolchain, features, action, source, output, flags, context = None, defines = []):
    variables = cc_common.create_compile_variables(
        cc_toolchain = toolchain,
        feature_configuration = features,
        source_file = source.path,
        output_file = output.path,
        user_compile_flags = flags,
        include_directories = depset(
            _package_paths(ctx, ctx.attr.includes),
            transitive = [context.includes],
            order = "preorder",
        ) if context else None,
        quote_include_directories = depset(
            _package_paths(ctx, ["."]),
            transitive = [context.quote_includes],
            order = "preorder",
        ) if context else None,
        system_include_directories = context.system_includes if context else None,
        framework_include_directories = context.framework_includes if context else None,
        preprocessor_defines = depset(defines, transitive = [context.defines]) if context else None,
    )
    return (
        cc_common.get_tool_for_action(feature_configuration = features, action_name = action),
        cc_common.get_memory_inefficient_command_line(
            feature_configuration = features,
            action_name = action,
            variables = variables,
        ),
        cc_common.get_environment_variables(
            feature_configuration = features,
            action_name = action,
            variables = variables,
        ),
    )

def _preprocessed_object_impl(ctx):
    toolchain = find_cc_toolchain(ctx)
    features = cc_common.configure_features(
        ctx = ctx,
        cc_toolchain = toolchain,
        requested_features = ctx.features,
        unsupported_features = ctx.disabled_features,
    )
    source = ctx.file.src
    is_c = source.extension == "c"
    action = ACTION_NAMES.c_compile if is_c else ACTION_NAMES.cpp_compile
    stem = ctx.label.name + "/" + source.basename.rsplit(".", 1)[0]
    preprocessed = ctx.actions.declare_file(stem + (".i" if is_c else ".ii"))
    obj = ctx.actions.declare_file(stem + ".o")
    context = cc_common.merge_compilation_contexts(
        compilation_contexts = [dep[CcInfo].compilation_context for dep in ctx.attr.deps],
    )
    compiler_files = toolchain.all_files

    # cc_library applies Bourne shell tokenization to copts; do the same.
    copts = []
    for copt in ctx.attr.copts:
        cc_helper.tokenize(copts, copt)

    tool, arguments, env = _command(
        ctx,
        toolchain,
        features,
        action,
        source,
        preprocessed,
        copts + ["-E"],
        context,
        ctx.attr.local_defines,
    )
    ctx.actions.run(
        executable = tool,
        arguments = arguments,
        env = env,
        inputs = depset([source], transitive = [context.headers, compiler_files]),
        outputs = [preprocessed],
        mnemonic = "CppPreprocess",
        progress_message = "Preprocessing " + source.short_path,
    )

    flags = [flag for flag in copts if not flag.startswith(_PREPROCESSOR_PREFIXES)]
    tool, arguments, env = _command(ctx, toolchain, features, action, preprocessed, obj, flags)
    ctx.actions.run(
        executable = tool,
        arguments = arguments,
        env = env,
        inputs = depset([preprocessed], transitive = [compiler_files]),
        outputs = [obj],
        mnemonic = "CppCompile",
        progress_message = "Compiling preprocessed " + source.short_path,
    )

    outputs = cc_common.create_compilation_outputs(objects = depset([obj]), pic_objects = depset([obj]))
    linking_context, _ = cc_common.create_linking_context_from_compilation_outputs(
        actions = ctx.actions,
        name = ctx.label.name,
        feature_configuration = features,
        cc_toolchain = toolchain,
        compilation_outputs = outputs,
        alwayslink = True,
        disallow_dynamic_library = True,
    )
    return [
        DefaultInfo(files = depset([obj])),
        CcInfo(linking_context = linking_context),
        OutputGroupInfo(compilation_outputs = depset([obj]), preprocessed = depset([preprocessed])),
    ]

godot_preprocessed_object = rule(
    doc = "Prototype: preprocess an engine source, then compile only the preprocessed text.",
    implementation = _preprocessed_object_impl,
    attrs = {
        "src": attr.label(allow_single_file = [".c", ".cc", ".cpp", ".cxx"], mandatory = True),
        "copts": attr.string_list(),
        "includes": attr.string_list(),
        "local_defines": attr.string_list(),
        "deps": attr.label_list(providers = [CcInfo]),
    },
    toolchains = use_cc_toolchain(),
    fragments = ["cpp"],
    provides = [CcInfo],
)
