"""RG016: local links in documentation and agent instructions resolve."""

from collections.abc import Iterable
from pathlib import PurePosixPath

from tools.conventions.context import Context, Location, Workspace
from tools.conventions.documents import Link, agent_instructions, anchors, local_links
from tools.conventions.framework import Finding, RuleInfo


class Targets:
    """The paths of the repository and the anchors of its Markdown pages, read once."""

    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        # Listed paths, compared case-sensitively as on GitHub, and their directories;
        # ignored local files such as user.bazelrc are no link targets.
        self.paths = {
            str(path)
            for entry in workspace.entries
            for path in (PurePosixPath(entry), *PurePosixPath(entry).parents)
        }
        self.fragments: dict[str, frozenset[str]] = {}

    def problem(self, link: Link) -> str | None:
        """Why a link does not resolve, if it does not."""
        if link.path == ".." or link.path.startswith("../"):
            return f"link leaves the repository: {link.path}"
        if link.path not in self.paths:
            return f"link target does not exist: {link.path}"
        # Only Markdown pages have anchors this check can read.
        if link.fragment and link.path.endswith(".md"):
            return self.fragment_problem(link)
        return None

    def fragment_problem(self, link: Link) -> str | None:
        """Why a link's fragment names nothing on its Markdown page, if it does not."""
        if link.path not in self.fragments:
            text = self.workspace.text(link.path)
            self.fragments[link.path] = frozenset(a.lower() for a in anchors(text))
        if link.fragment.lower() in self.fragments[link.path]:
            return None
        return f"no heading or anchor {link.fragment!r} in {link.path}"


class LocalLinks:
    info = RuleInfo(
        "RG016",
        "Local links resolve",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        targets = Targets(workspace)
        for name in sorted({*workspace.documents, *agent_instructions(workspace)}):
            links = local_links(name, workspace.text(name))
            # Broken links on one line with the same problem are one finding.
            problems = dict.fromkeys(
                (link.line, problem)
                for link in links
                if (problem := targets.problem(link))
            )
            for line, problem in problems:
                yield Finding(Location(name, line), problem)
