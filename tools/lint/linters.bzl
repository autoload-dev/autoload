"""
The repository's linters as rules_lint aspects, and the lint check that runs them in Bazel's
builds: the aspect `python`, which `--config=check` applies in the root module and the ruleset
(shared.bazelrc). `aspect lint` applies `ruff` and `ty` themselves, for their fixes; the other
modules load them from here as @autoload_dev.
Configured once: Ruff in pyproject.toml, ty in ty.toml. Buildifier lints Starlark in
//tools/format, and jactionlint the workflows in //tools/lint:workflows_test.
"""

load("@aspect_rules_lint//lint:ruff.bzl", "lint_ruff_aspect")
load("@aspect_rules_lint//lint:ty.bzl", "lint_ty_aspect")

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

_LintChecksInfo = provider(
    doc = "The stamps of the lint checks of a target and of what it depends on.",
    fields = {"stamps": "depset of File: a stamp per linted target"},
)

def _reports(target):
    """Pairs of exit code file and report of the linters that ran on the target."""
    if OutputGroupInfo not in target or not hasattr(target[OutputGroupInfo], "rules_lint_human"):
        return []
    files = {file.path: file for file in target[OutputGroupInfo].rules_lint_human.to_list()}
    return [
        (file, files[path.removesuffix(".exit_code")])
        for path, file in files.items()
        if path.endswith(".out.exit_code")
    ]

def _python_impl(target, ctx):
    stamps = [dep[_LintChecksInfo].stamps for dep in getattr(ctx.rule.attr, "deps", []) if _LintChecksInfo in dep]
    reports = _reports(target)
    own = []
    if reports:
        stamp = ctx.actions.declare_file(target.label.name + ".lint")
        arguments = ctx.actions.args().add(stamp)
        for exit_code, report in reports:
            arguments.add(exit_code).add(report)
        ctx.actions.run(
            executable = ctx.executable._check,
            arguments = [arguments],
            inputs = [file for pair in reports for file in pair],
            outputs = [stamp],
            mnemonic = "LintCheck",
            progress_message = "Checking the lint of %{label}",
        )
        own = [stamp]
    checks = depset(own, transitive = stamps)
    return [
        _LintChecksInfo(stamps = checks),
        # As a validation, the check runs in every build and test; `lint_checks` names it alone.
        OutputGroupInfo(_validation = checks, lint_checks = checks),
    ]

python = aspect(
    doc = """
    The lint check: Ruff and ty on each Python target the build reaches through `deps`, which
    fails the build with their reports when one of them finds something. The linters write
    their exit codes as rules_lint does without `fail_on_violation`, so the check shares their
    configuration and actions with every other build and with `aspect lint`.
    """,
    implementation = _python_impl,
    attr_aspects = ["deps"],
    requires = [ruff, ty],
    attrs = {
        "_check": attr.label(
            default = Label(":check.sh"),
            allow_single_file = True,
            executable = True,
            cfg = "exec",
        ),
    },
)
