"""Python modules of the workspace as syntax trees, for the rules that read their structure."""

import ast

from tools.conventions.context import EvidenceError, Workspace


def parse(workspace: Workspace, name: str) -> ast.Module:
    """The syntax tree of a Python module; one that does not parse fails the audit."""
    try:
        return ast.parse(workspace.text(name), name)
    except SyntaxError as error:
        raise EvidenceError(f"{name}: cannot parse as Python: {error.msg}") from error
