"""Regressions for agent instructions outside AGENTS.md."""

import unittest

from tools.conventions.rules.rg017 import AgentInstructions
from tools.conventions.test_support import RepositoryTest


class AgentInstructionsTest(RepositoryTest):
    def test_every_claude_md_is_reported(self) -> None:
        self.write("AGENTS.md", "")
        self.write("CLAUDE.md", "@AGENTS.md\n")
        self.write("rules_godot/CLAUDE.md", "")
        self.write("docs/claude.md", "")
        self.assertEqual(
            [item.location.path for item in AgentInstructions().evaluate(self.context())],
            ["CLAUDE.md", "rules_godot/CLAUDE.md"],
        )

    def test_agents_md_alone_passes(self) -> None:
        self.write("AGENTS.md", "")
        self.write("addons/AGENTS.md", "")
        self.assertEqual(list(AgentInstructions().evaluate(self.context())), [])


if __name__ == "__main__":
    unittest.main()
