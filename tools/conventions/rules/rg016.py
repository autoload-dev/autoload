"""RG016: local links in documentation and agent instructions resolve."""

from collections.abc import Iterable

from tools.conventions.context import Context, Location
from tools.conventions.documents import Link, agent_instructions, anchors, local_links
from tools.conventions.framework import Finding, RuleInfo


class LocalLinks:
    info = RuleInfo(
        "RG016",
        "Local links resolve",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        fragments: dict[str, frozenset[str]] = {}
        for name in sorted({*workspace.documents, *agent_instructions(workspace)}):
            # Repeated links on one line are one finding.
            for link in dict.fromkeys(local_links(name, workspace.text(name))):
                problem = self._problem(context, link, fragments)
                if problem:
                    yield Finding(Location(name, link.line), problem)

    @staticmethod
    def _problem(
        context: Context, link: Link, fragments: dict[str, frozenset[str]]
    ) -> str | None:
        workspace = context.workspace
        if link.path == ".." or link.path.startswith("../"):
            return f"link leaves the repository: {link.path}"
        if not (workspace.root / link.path).exists():
            return f"link target does not exist: {link.path}"
        # Only Markdown pages have anchors this check can read.
        if not link.fragment or not link.path.endswith(".md"):
            return None
        if link.path not in fragments:
            fragments[link.path] = anchors(workspace.text(link.path))
        if link.fragment not in fragments[link.path]:
            return f"no heading or anchor {link.fragment!r} in {link.path}"
        return None
