"""Regressions for skills shared by both agents."""

import os
import unittest

from tools.conventions.rules.rg018 import SharedSkills
from tools.conventions.test_support import RepositoryTest


class SharedSkillsTest(RepositoryTest):
    def skill(self, name: str) -> None:
        self.write(f".agents/skills/{name}/SKILL.md", "---\nname: x\n---\n")
        self.write(f".agents/skills/{name}/references/notes.md", "")

    def link(self, name: str, target: str | None = None) -> None:
        path = self.root / ".claude/skills" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target or f"../../.agents/skills/{name}", path)
        self.files.add(f".claude/skills/{name}")

    def findings(self) -> list[str]:
        return [
            f"{item.location.path}: {item.message}"
            for item in SharedSkills().evaluate(self.context())
        ]

    def test_linked_skills_pass(self) -> None:
        self.skill("api")
        self.skill("docs")
        self.link("api")
        self.link("docs")
        self.write(".claude/settings.json", "{}")
        self.assertEqual(self.findings(), [])

    def test_skill_without_link_is_reported(self) -> None:
        self.skill("api")
        self.assertEqual(
            self.findings(),
            [
                (
                    ".agents/skills/api: link the skill for Claude Code: "
                    ".claude/skills/api -> ../../.agents/skills/api"
                ),
            ],
        )

    def test_copies_and_wrong_targets_are_reported_once(self) -> None:
        self.skill("api")
        self.skill("docs")
        self.write(".claude/skills/api/SKILL.md", "")
        self.write(".claude/skills/api/references/notes.md", "")
        self.link("docs", "../../.agents/skills/api")
        self.assertEqual(
            self.findings(),
            [
                (
                    ".claude/skills/api: .claude/skills/api must be a symbolic link to "
                    "../../.agents/skills/api, not a copy or another target"
                ),
                (
                    ".claude/skills/docs: .claude/skills/docs must be a symbolic link to "
                    "../../.agents/skills/docs, not a copy or another target"
                ),
            ],
        )

    def test_entries_without_a_skill_are_reported(self) -> None:
        self.write(".claude/skills/local/SKILL.md", "")
        self.link("gone")
        self.write(".agents/skills/README.md", "")
        self.link("README.md")
        self.assertEqual(
            self.findings(),
            [
                (
                    ".claude/skills/README.md: .claude/skills/README.md has no skill in "
                    ".agents/skills/; move the skill there and link it"
                ),
                (
                    ".claude/skills/gone: .claude/skills/gone has no skill in "
                    ".agents/skills/; move the skill there and link it"
                ),
                (
                    ".claude/skills/local: .claude/skills/local has no skill in "
                    ".agents/skills/; move the skill there and link it"
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
