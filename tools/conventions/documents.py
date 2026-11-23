"""Which documentation is internal: the repository's and the ruleset's docs/internal/."""

from tools.conventions.context import DOCS

# The ruleset's internal pages live beside its public guides.
INTERNAL_DOCS = tuple(f"{docs}internal" for docs in DOCS)


def internal_document(path: str) -> bool:
    """Whether a repository-relative path is internal documentation or one of its directories."""
    return any(path == docs or path.startswith(f"{docs}/") for docs in INTERNAL_DOCS)
