"""no-claude-md: agent instructions live in AGENTS.md, never in CLAUDE.md."""

from collections.abc import Iterable
from pathlib import Path

from tools.conventions.context import Context, Location
from tools.conventions.framework import Finding, RuleInfo


class AgentInstructions:
    info = RuleInfo(
        "no-claude-md",
        "Agent instructions live in AGENTS.md",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        for name in context.workspace.entries:
            # Claude Code reads AGENTS.md only while no CLAUDE.md is in or above its directory.
            if Path(name).name == "CLAUDE.md":
                yield Finding(
                    Location(name, 1),
                    "move these agent instructions to AGENTS.md, which both agents read, "
                    "and remove CLAUDE.md",
                )
