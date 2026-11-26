"""
The repository's linters as rules_lint aspects: the lint check runs them in Bazel's builds
(check.bzl), `aspect lint` for their fixes; the other modules load them as @autoload_dev.

Configured once: Ruff in pyproject.toml, ty in ty.toml, gdlint in .gdlintrc, rumdl in
.rumdl.toml. Ruff and ty lint Python targets; gdlint and rumdl the filegroups of GDScript and
Markdown that Gazelle declares in every package (tools/gazelle/lint), by their tags. Buildifier
lints Starlark in //tools/format, and jactionlint the workflows in //tools/lint:workflows_test.

Sections: Python, Sources without targets.
"""

load("@aspect_rules_lint//lint:ruff.bzl", "lint_ruff_aspect")
load("@aspect_rules_lint//lint:ty.bzl", "lint_ty_aspect")

# rules_lint builds its own linters' aspects with these helpers and offers no public ones; with
# them, gdlint and rumdl write the outputs that `aspect lint` and the lint check read.
# buildifier: disable=bzl-visibility
load(
    "@aspect_rules_lint//lint/private:lint_aspect.bzl",
    "LintOptionsInfo",
    "noop_lint_action",
    "output_files",
    "should_visit",
)

# ==== Python ==================================================================

# Ruff picks the configuration above a file, which the other modules' files do not have, so the
# root module's is named; its path in the execution root depends on the module being linted.
_PYPROJECT = Label("//:pyproject.toml")

ruff = lint_ruff_aspect(
    binary = Label("@aspect_rules_lint//lint:ruff_bin"),
    configs = [_PYPROJECT],
    args = ["--config", "/".join([p for p in [_PYPROJECT.workspace_root, _PYPROJECT.name] if p])],
)

ty = lint_ty_aspect(
    binary = Label("@aspect_rules_lint//lint:ty_bin"),
    # A ty.toml, unlike a pyproject.toml, leaves the project root at the linted module.
    config = Label("//:ty.toml"),
)

# ==== Sources without targets =================================================

def _lint(ctx, outputs):
    """
    Run the aspect's linter on the filegroup's sources, as rules_lint's aspects do.

    Its report is both outputs; its exit code fails the action or lands in the exit code files.
    """
    linter = ctx.executable._linter
    config = getattr(ctx.file, "_config", None)
    module = getattr(ctx.file, "_module", None)
    codes = [f for f in [outputs.human.exit_code, outputs.machine.exit_code] if f]
    record = "".join([' && echo "$code" >"%s"' % f.path for f in codes])
    command = '"%s" %s "$@" >"%s" 2>&1; code=$?; cp "%s" "%s"%s; %s' % (
        linter.path,
        ctx.attr._arguments.format(
            config = config.path if config else "",
            module = module.path if module else "",
        ),
        outputs.human.out.path,
        outputs.human.out.path,
        outputs.machine.out.path,
        record,
        "exit 0" if codes else 'exit "$code"',
    )
    ctx.actions.run_shell(
        command = command,
        arguments = [ctx.actions.args().add_all(ctx.rule.files.srcs)],
        inputs = [f for f in [config, module] if f] + ctx.rule.files.srcs,
        tools = [linter],
        outputs = [outputs.human.out, outputs.machine.out] + codes,
        mnemonic = ctx.attr._mnemonic,
        progress_message = "Linting %{label} with " + ctx.attr._mnemonic,
    )

def _sources_impl(target, ctx):
    if not should_visit(ctx.rule, [], ctx.attr._tags):
        return []
    outputs, info = output_files(ctx.attr._mnemonic, target, ctx)
    if ctx.rule.files.srcs:
        _lint(ctx, outputs)
    else:
        noop_lint_action(ctx, outputs)
    return [info]

def _sources_aspect(tags, mnemonic, linter):
    """
    A rules_lint aspect that lints the sources of each filegroup with one of the tags.

    Args:
      tags: The tags of the filegroups it lints.
      mnemonic: Its actions' mnemonic and the name of its outputs.
      linter: A struct of the linter's `executable`, its `config` file, if any, whether it
        reads the main repository's `module`, and its `arguments` before the sources, where
        `{config}` stands for the configuration's path and `{module}` for the MODULE.bazel.
    """
    attrs = {}
    if hasattr(linter, "config"):
        attrs["_config"] = attr.label(default = linter.config, allow_single_file = True)
    if getattr(linter, "module", False):
        # The module of the main repository, which names the module being checked.
        attrs["_module"] = attr.label(default = Label("@@//:MODULE.bazel"), allow_single_file = True)
    return aspect(
        implementation = _sources_impl,
        attrs = attrs | {
            "_options": attr.label(
                default = "@aspect_rules_lint//lint:options",
                providers = [LintOptionsInfo],
            ),
            "_linter": attr.label(default = linter.executable, executable = True, cfg = "exec"),
            "_arguments": attr.string(default = linter.arguments),
            "_tags": attr.string_list(default = tags),
            "_mnemonic": attr.string(default = mnemonic),
        },
    )

gdlint = _sources_aspect(
    tags = ["gdscript"],
    mnemonic = "gdlint",
    linter = struct(
        executable = Label(":gdscript"),
        config = Label("//:.gdlintrc"),
        arguments = "{config}",
    ),
)

rumdl = _sources_aspect(
    tags = ["markdown"],
    mnemonic = "rumdl",
    linter = struct(
        executable = Label("@multitool//tools/rumdl"),
        config = Label("//:.rumdl.toml"),
        arguments = "check --quiet --no-cache --config {config}",
    ),
)

# The convention rules that judge each file on its own (tools/conventions/per_file.py), on
# every kind of file that Gazelle declares filegroups for; each rule picks its own files.
conventions = _sources_aspect(
    tags = ["cc", "gdscript", "markdown", "python_files", "starlark"],
    mnemonic = "Conventions",
    linter = struct(
        executable = Label("//tools/conventions:files"),
        module = True,
        arguments = "--module-file={module} --",
    ),
)
