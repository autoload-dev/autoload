"""
Which of its macro definitions each source of a source-built engine reads.

Every -D option is part of a compile action's cache key, so a build option such as
`disable_3d` would miss the cache for every object, also where the source's preprocessing
never reads the macro. The analysis lets the compiler decide instead:

- `godot_source_defines` writes a wrapper per source: its definitions as `#define` and
  `#undef` lines, then an `#include` of the source. It also prepares the source's compile
  command line, with `-E` and `-Wunused-macros` added and the options that would silence or
  fail on that warning removed.
- `godot_define_analysis` preprocesses the wrappers of several sources in one action and
  writes each source's header, `_macros/<library>.h`: the wrapper's definitions except
  those the compiler reports unused. A definition that the preprocessing never reads
  cannot change it, so dropping it keeps the preprocessed source, and the object, as is.

The source's library compiles with `-include` of its header instead of the definitions.
Its command line no longer changes with the build options, so the cache decides by the
header's content.

The source is preprocessed as an included file, not as the main file, so a source whose
preprocessing depends on that, through __INCLUDE_LEVEL__, __BASE_FILE__ or a #pragma once
of its own, can read a definition in its compile that the analysis reported unused;
Godot's sources have none of them.

A build with --per_file_copt keeps every definition: those options reach the compiles but
not Starlark, so the analysis could not preprocess with them.

Objective-C compiles keep their -D options: they use implicit Clang modules, which see the
command line's macros but neither a wrapper's nor a forced include's, so a definition
reported unused can still change a module the source imports.

Sections: godot_source_defines, godot_define_analysis.
"""

load("@bazel_skylib//rules:common_settings.bzl", "BuildSettingInfo")
load("@rules_cc//cc:action_names.bzl", "ACTION_NAMES")
load("@rules_cc//cc:find_cc_toolchain.bzl", "find_cc_toolchain", "use_cc_toolchain")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_helper.bzl", "cc_helper")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("//godot/private:actions.bzl", "PATH_MAPPING")

visibility(["//godot/..."])

# ==== godot_source_defines ====================================================

GodotSourceDefinesInfo = provider(
    doc = "A source's wrapper and the command line that preprocesses it.",
    fields = {
        "definitions": "str: the source's #define and #undef lines.",
        "wrapper": "File: a canary definition, the definitions, then an #include of the source.",
        "command": "list[str] | None: the preprocessing command line; None keeps every definition.",
        "env": "dict[str, str]: the command's environment.",
        "execution_requirements": "dict[str, str]: the toolchain's requirements of a compile, such as Xcode's.",
        "inputs": "depset[File]: the source, its wrapper and the headers it may include.",
    },
)

# Options that would silence the analysis' warning or turn it into an error.
_SILENCING = ("-w", "-Wno-everything", "-Wno-unused-macros", "-Wfatal-errors")

# Compilers with cl.exe's options, which have neither -E's form here nor -Wunused-macros;
# their sources keep every definition. Clang and GCC, whatever a toolchain calls them
# (the NDK's says llvm-c++), name the main file's unused definitions. A compiler that
# reported none would keep every definition too.
_CL_COMPILERS = ("msvc-cl", "clang-cl")

# The wrapper's first line, which no source reads: a compiler that does not name it
# unused reports no unused definition at all, and the analysis fails.
_CANARY = "#define GODOT_DEFINE_ANALYSIS_CANARY 1\n"

_PER_FILE_COPT = "//command_line_option:per_file_copt"

_PER_FILE_COPT_SET = str(Label("//godot/engine/private:per_file_copt_set"))

def _per_file_copt_impl(settings, _attr):
    return {_PER_FILE_COPT_SET: bool(settings[_PER_FILE_COPT])}

# Changes the configuration only where --per_file_copt is set.
_per_file_copt = transition(
    implementation = _per_file_copt_impl,
    inputs = [_PER_FILE_COPT],
    outputs = [_PER_FILE_COPT_SET],
)

def _tokens(options):
    """The options as cc_library sees them: Bourne shell tokenization applies."""
    tokens = []
    for option in options:
        cc_helper.tokenize(tokens, option)
    return tokens

def _definition(option):
    """The #define or #undef line of a -D or -U option."""
    if option.startswith("-U"):
        return "#undef " + option[2:]
    name, equals, value = option[2:].partition("=")
    return "#define {} {}".format(name, value if equals else "1")

def _package_paths(ctx, directories):
    """The source and output paths of package directories, as cc_library's includes."""
    root = ctx.label.workspace_root
    paths = []
    for directory in directories:
        path = "/".join([part for part in (root, directory) if part not in ("", ".")]) or "."
        paths += [path, ctx.bin_dir.path if path == "." else ctx.bin_dir.path + "/" + path]
    return paths

def _command(ctx, toolchain, features, wrapper, context):
    """The source's compile command line, preprocessing its wrapper instead."""
    is_c = ctx.file.src.extension == "c"
    action = ACTION_NAMES.c_compile if is_c else ACTION_NAMES.cpp_compile

    # cc_library's order: --copt, then --conlyopt or --cxxopt, then the library's copts.
    # They can change the preprocessing, as -D or an -O level's __OPTIMIZE__ do.
    cpp = ctx.fragments.cpp
    options = cpp.copts + (cpp.conlyopts if is_c else cpp.cxxopts) + _tokens(ctx.attr.copts)
    flags = [
        option
        for option in options
        if option not in _SILENCING and not option.startswith("-Werror")
    ]
    variables = cc_common.create_compile_variables(
        cc_toolchain = toolchain,
        feature_configuration = features,
        source_file = wrapper.path,
        output_file = "/dev/null",
        # The wrapper includes the source by its execution root path.
        user_compile_flags = flags + [
            "-iquote",
            ".",
            "-E",
            "-Wunused-macros",
            "-Wno-error=unused-macros",
        ],
        include_directories = depset(
            _package_paths(ctx, ctx.attr.includes),
            transitive = [context.includes],
            order = "preorder",
        ),
        quote_include_directories = depset(
            _package_paths(ctx, ["."]),
            transitive = [context.quote_includes],
            order = "preorder",
        ),
        system_include_directories = context.system_includes,
        framework_include_directories = context.framework_includes,
        preprocessor_defines = context.defines,
    )
    tool = cc_common.get_tool_for_action(feature_configuration = features, action_name = action)
    arguments = cc_common.get_memory_inefficient_command_line(
        feature_configuration = features,
        action_name = action,
        variables = variables,
    )
    env = cc_common.get_environment_variables(
        feature_configuration = features,
        action_name = action,
        variables = variables,
    )
    requirements = {
        requirement: ""
        for requirement in cc_common.get_execution_requirements(
            feature_configuration = features,
            action_name = action,
        )
    }
    return [tool] + arguments, env, requirements

def _included_path(source, wrapper):
    """
    The path the wrapper includes its source by.

    A source file keeps its execution root path. A generated source lies in the wrapper's
    output directory, which path mapping renames, so the wrapper names it relative to itself.
    """
    if source.is_source:
        return source.path
    depth = len(wrapper.dirname[len(wrapper.root.path) + 1:].split("/"))
    return "../" * depth + source.path[len(source.root.path) + 1:]

def _source_defines_impl(ctx):
    toolchain = find_cc_toolchain(ctx)
    features = cc_common.configure_features(
        ctx = ctx,
        cc_toolchain = toolchain,
        requested_features = ctx.features,
        unsupported_features = ctx.disabled_features,
    )
    source = ctx.file.src

    # cc_library puts local_defines before the options.
    lines = ["#define {} 1".format(name) for name in ctx.attr.local_defines]
    lines += [_definition(option) for option in _tokens(ctx.attr.defines)]
    definitions = "".join([line + "\n" for line in lines])
    wrapper = ctx.actions.declare_file("_macros/{}.wrapper.{}".format(ctx.label.name, source.extension))
    ctx.actions.write(wrapper, _CANARY + definitions + '#include "{}"\n'.format(_included_path(source, wrapper)))
    context = cc_common.merge_compilation_contexts(
        compilation_contexts = [dep[CcInfo].compilation_context for dep in ctx.attr.deps],
    )
    command, env, requirements = None, {}, {}
    if toolchain.compiler not in _CL_COMPILERS and not ctx.attr._per_file_copt_set[BuildSettingInfo].value:
        command, env, requirements = _command(ctx, toolchain, features, wrapper, context)
    return [GodotSourceDefinesInfo(
        definitions = definitions,
        wrapper = wrapper,
        command = command,
        env = env,
        execution_requirements = requirements,
        inputs = depset([source, wrapper], transitive = [context.headers]),
    )]

godot_source_defines = rule(
    doc = "A source's macro definitions and the command line that tells which it reads.",
    implementation = _source_defines_impl,
    attrs = {
        "src": attr.label(allow_single_file = [".c", ".cc", ".cpp", ".cxx"], mandatory = True, doc = "The source."),
        "copts": attr.string_list(doc = "The library's compiler options other than -D and -U."),
        "defines": attr.string_list(doc = "The library's -D and -U options, in order."),
        "local_defines": attr.string_list(doc = "Names the library defines as 1."),
        "includes": attr.string_list(doc = "The library's include directories."),
        "deps": attr.label_list(providers = [CcInfo], doc = "The library's dependencies."),
        "_per_file_copt_set": attr.label(default = _PER_FILE_COPT_SET),
    },
    cfg = _per_file_copt,
    toolchains = use_cc_toolchain(),
    fragments = ["cpp"],
)

# ==== godot_define_analysis ===================================================

# Runs the sources' preprocessing on one lane per processor; define_analysis.awk turns
# each one's diagnostics into its header. A failed preprocessing fails the action.
_SCRIPT = """\
set -eu
program=$1
{ROOTS}
analyze() {
  out=$1; wrapper=$2; shift 2
  if ! log=$("$@" 2>&1 >/dev/null); then printf '%s\\n' "$log" >&2; exit 1; fi
  printf '%s\\n' "$log" | awk -v wrapper="$wrapper" -f "$program" > "$out"
}
run() {
  case $1 in
{CASES}
  esac
}
sources={COUNT}
lanes=$(getconf _NPROCESSORS_ONLN)
pids=""
lane=0
while [ "$lane" -lt "$lanes" ] && [ "$lane" -lt "$sources" ]; do
  (
    index=$lane
    while [ "$index" -lt "$sources" ]; do
      run "$index"
      index=$((index + lanes))
    done
  ) &
  pids="$pids $!"
  lane=$((lane + 1))
done
status=0
for pid in $pids; do wait "$pid" || status=1; done
exit $status
"""

def _quote(text):
    return "'" + text.replace("'", "'\\''") + "'"

def _case(index, info, header):
    return "  {}) analyze {} {} {} ;;".format(
        index,
        _quote(header.path),
        _quote(info.wrapper.path),
        " ".join([_quote(argument) for argument in info.command]),
    )

def _root_path(file):
    return file.root.path

def _output_roots(text):
    """The output directories, such as bazel-out/<configuration>/bin, that text names, in order."""
    roots = []
    for part in text.split("bazel-out/")[1:]:
        root = "bazel-out/" + part.split("/")[0] + "/bin"
        if root not in roots:
            roots.append(root)
    return roots

def _first_by_root(files, by_root):
    """The first of the files in each output directory, added to by_root's."""
    result = dict(by_root)
    for file in files:
        result.setdefault(file.root.path, file)
    return result

def _root_files(label, roots, candidates, toolchain_files):
    """
    One file of each output directory, whose root path mapping rewrites.

    The analysis' own headers and wrappers lie in the directories its sources name; only a
    directory none of them lies in takes a file of the C++ toolchain, whose files are many.
    """
    by_root = _first_by_root(candidates, {})
    if [root for root in roots if root not in by_root]:
        by_root = _first_by_root(toolchain_files.to_list(), by_root)
    missing = [root for root in roots if root not in by_root]
    if missing:
        fail("%s: no input or output lies in %s" % (label, missing[0]))
    return [by_root[root] for root in roots]

def _portable_script(ctx, analyzed, candidates, toolchain_files):
    """
    Write the analysis script with ${ROOT<n>} for each output directory it names.

    Returns the script and one file of each output directory, in the order of n.
    """
    cases = "\n".join([_case(index, info, header) for index, (info, header) in enumerate(analyzed)])
    roots = _output_roots(cases)
    for index, root in enumerate(roots):
        cases = cases.replace(root, "'\"${ROOT%d}\"'" % index)
    root_lines = "".join(["ROOT%d=$%d\n" % (index, index + 2) for index in range(len(roots))])
    content = _SCRIPT.replace("{ROOTS}\n", root_lines).replace("{CASES}", cases)
    script = ctx.actions.declare_file("_macros/{}.sh".format(ctx.label.name))
    ctx.actions.write(script, content.replace("{COUNT}", str(len(analyzed))))
    return script, _root_files(ctx.label, roots, candidates, toolchain_files)

def _analyze(ctx, analyzed):
    """
    Run the analysis of the sources that have a command, as (info, header) pairs.

    The script names no output directory: each becomes ${ROOT<n>}, whose value an argument
    takes from a file of that directory. Path mapping rewrites the argument, so the script
    and the action's command are the same in every configuration.
    """
    toolchain_files = find_cc_toolchain(ctx).all_files
    candidates = [header for _, header in analyzed] + [info.wrapper for info, _ in analyzed]
    script, representatives = _portable_script(ctx, analyzed, candidates, toolchain_files)
    env, requirements = {}, dict(PATH_MAPPING)
    for info, _ in analyzed:
        env |= info.env
        requirements |= info.execution_requirements
    arguments = ctx.actions.args()
    arguments.add(script)
    arguments.add(ctx.file._program)
    arguments.add_all(representatives, map_each = _root_path)
    ctx.actions.run_shell(
        command = 'bash "$@"',
        arguments = [arguments],
        env = env,
        execution_requirements = requirements,
        inputs = depset(
            [script, ctx.file._program],
            transitive = [info.inputs for info, _ in analyzed] + [toolchain_files],
        ),
        outputs = [header for _, header in analyzed],
        mnemonic = "DefineAnalysis",
        progress_message = "Analyzing the macro definitions of %{label}",
    )

def _define_analysis_impl(ctx):
    infos = [source[GodotSourceDefinesInfo] for source in ctx.attr.sources]
    if len(infos) != len(ctx.outputs.outs):
        fail("Every source needs one header in outs.")
    analyzed = []
    for info, header in zip(infos, ctx.outputs.outs):
        if info.command == None:
            ctx.actions.write(header, info.definitions)
        else:
            analyzed.append((info, header))
    if analyzed:
        _analyze(ctx, analyzed)
    return [DefaultInfo(files = depset(ctx.outputs.outs))]

godot_define_analysis = rule(
    doc = "Write the macro definitions that each of several sources' preprocessing reads.",
    implementation = _define_analysis_impl,
    attrs = {
        "sources": attr.label_list(
            providers = [GodotSourceDefinesInfo],
            doc = "The sources' godot_source_defines targets.",
        ),
        "outs": attr.output_list(doc = "Each source's header, in the order of sources."),
        "_program": attr.label(default = Label("//godot/engine/private:define_analysis.awk"), allow_single_file = True),
    },
    toolchains = use_cc_toolchain(),
    fragments = ["cpp"],
)
