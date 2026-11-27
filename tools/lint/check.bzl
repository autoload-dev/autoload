"""
The lint check, which `--config=check` (shared.bazelrc) adds to a build or test in the root
module and the ruleset: the aspect `python`, which runs Ruff and ty (linters.bzl) and fails the
build with their reports through check.sh.
"""

load("//:addons.bzl", "ADDON_REPOSITORIES")
load(":linters.bzl", "ruff", "ty")

_LintChecksInfo = provider(
    doc = "The stamps of the lint checks of a target and of what it depends on.",
    fields = {"stamps": "depset of File: a stamp per linted target"},
)

# The tag that has rules_lint lint the sources of a target outside the main repository.
_OPT_IN = "lint-genfiles"

# The kinds rules_lint's Ruff and ty aspects visit: their default `rule_kinds`, which
# linters.bzl keeps.
_PYTHON = ["py_binary", "py_library", "py_test"]

def _skips(target, ctx):
    """Whether rules_lint skips the target: one outside the main repository, not opted in."""
    return target.label.workspace_name and _OPT_IN not in ctx.rule.attr.tags

def _addon_repositories():
    """The canonical names of the add-on modules' repositories, which the root module lints.

    Empty in another module's workspace, such as the ruleset's, which declares no add-on module.
    """
    if Label("//:BUILD.bazel").workspace_name:
        return []
    return [Label(repository + "//:BUILD.bazel").repo_name for repository in ADDON_REPOSITORIES]

def _unseen(target, ctx):
    """Whether the target is an add-on module's Python, which rules_lint would skip unseen.

    The root module lints the add-on modules' Python with its own; rules_lint sees an add-on
    module's sources only when the target opts in with the tag.
    """
    return (
        ctx.rule.kind in _PYTHON and
        _skips(target, ctx) and
        target.label.repo_name in _addon_repositories()
    )

def _reports(target, ctx):
    """Pairs of exit code file and report of the linters that ran on the target.

    None for a target outside the main repository whose sources rules_lint skips, such as a
    PyPI package.
    """
    if _skips(target, ctx):
        return []
    groups = target[OutputGroupInfo] if OutputGroupInfo in target else None
    if not hasattr(groups, "rules_lint_human"):
        return []
    files = {file.path: file for file in groups.rules_lint_human.to_list()}
    return [
        (file, files[path.removesuffix(".exit_code")])
        for path, file in files.items()
        if path.endswith(".out.exit_code")
    ]

def _check(target, ctx, reports):
    """The action that fails with the reports of the linters that found something."""
    stamp = ctx.actions.declare_file(target.label.name + ".lint")
    files = [file for pair in reports for file in pair]
    ctx.actions.run(
        executable = ctx.executable._check,
        arguments = [ctx.actions.args().add(stamp).add_all(files)],
        inputs = files,
        outputs = [stamp],
        mnemonic = "LintCheck",
        progress_message = "Checking the lint of %{label}",
    )
    return stamp

def _python_impl(target, ctx):
    if _unseen(target, ctx):
        fail(
            "%s: an add-on module's %s needs tags = [\"%s\"]: without it, the root module's" %
            (target.label, ctx.rule.kind, _OPT_IN),
            "lint check skips its sources",
        )
    deps = getattr(ctx.rule.attr, "deps", [])
    stamps = [dep[_LintChecksInfo].stamps for dep in deps if _LintChecksInfo in dep]
    reports = _reports(target, ctx)
    if not reports and not stamps:
        return []
    checks = depset([_check(target, ctx, reports)] if reports else [], transitive = stamps)
    return [
        _LintChecksInfo(stamps = checks),
        # A validation runs in every build and test; `lint_checks` names the check alone.
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
