"""
The repository's Python linters as rules_lint aspects: the lint check runs them in Bazel's
builds (check.bzl), `aspect lint` for their fixes; the other modules load them as
@autoload_dev. Ruff is configured in pyproject.toml, ty in ty.toml.

The linters of files without targets of their own run in the file lint (files.py), Buildifier
in //tools/format, and jactionlint on the workflows in //tools/lint:workflows_test.
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
