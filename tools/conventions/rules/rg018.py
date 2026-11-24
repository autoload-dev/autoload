"""RG018: each skill lives once in .agents/skills/ and is linked from .claude/skills/."""

import os
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from tools.conventions.context import Context, Location
from tools.conventions.framework import Finding, RuleInfo

SKILLS = PurePosixPath(".agents/skills")
LINKS = PurePosixPath(".claude/skills")


def child(name: str, parent: PurePosixPath) -> str | None:
    """The first path segment of name below parent, if name lies below it."""
    path = PurePosixPath(name)
    if path.is_relative_to(parent) and path != parent:
        return path.relative_to(parent).parts[0]
    return None


class SharedSkills:
    info = RuleInfo(
        "RG018",
        "Skills live in .agents/skills and are linked for Claude Code",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        workspace = context.workspace
        # A skill is a directory of .agents/skills/ with a SKILL.md.
        skills = {
            path.parent.name
            for name in workspace.files
            if (path := PurePosixPath(name)).parent.parent == SKILLS
            and path.name == "SKILL.md"
        }
        # One finding per entry of .claude/skills/, however many files a copy holds.
        entries = {entry for name in workspace.entries if (entry := child(name, LINKS))}
        for entry in sorted(entries | skills):
            problem = self.problem(
                workspace.root, entry, entry in skills, entry in entries
            )
            if problem:
                yield Finding(Location(problem[0].as_posix(), 1), problem[1])

    @staticmethod
    def problem(
        root: Path, entry: str, skill: bool, linked: bool
    ) -> tuple[PurePosixPath, str] | None:
        """Where and why a skill or an entry of .claude/skills/ breaks the rule."""
        link = LINKS / entry
        wanted = os.path.relpath(SKILLS / entry, LINKS)
        if not linked:
            return SKILLS / entry, f"link the skill for Claude Code: {link} -> {wanted}"
        if not skill:
            return (
                link,
                f"{link} has no skill in {SKILLS}/; move the skill there and link it",
            )
        path = root / link
        if path.is_symlink() and os.readlink(path) == wanted:
            return None
        return (
            link,
            f"{link} must be a symbolic link to {wanted}, not a copy or another target",
        )
