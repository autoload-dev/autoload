"""Tests of which pool slots release_done.py releases and of the Git state it reads."""

import dataclasses
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar

from tools.worktree import release_done
from tools.worktree.release_done import Checkout, PullRequest, Slot, decide

HOUR = release_done.IDLE_GRACE_MS

DONE = Slot(
    slot="a1",
    branch="claude/x",
    idle_ms=2 * HOUR,
    dirty=False,
    head_on_origin=False,
    head="h1",
    branch_on_origin=False,
    had_upstream=True,
    pull_requests=(PullRequest(7, "MERGED", "h1"),),
)


class DecideTest(unittest.TestCase):
    def test_releases_a_merged_clean_branch(self) -> None:
        self.assertEqual(
            decide(DONE), release_done.Verdict(True, "pull request #7 merged")
        )

    def test_releases_a_merged_branch_still_on_origin(self) -> None:
        slot = dataclasses.replace(DONE, branch_on_origin=True, head_on_origin=True)
        self.assertTrue(decide(slot).release)

    def test_releases_a_branch_deleted_on_origin_with_a_closed_pull_request(self) -> None:
        slot = dataclasses.replace(DONE, pull_requests=(PullRequest(3, "CLOSED", "h1"),))
        self.assertEqual(
            decide(slot), release_done.Verdict(True, "branch deleted on origin")
        )

    def test_releases_a_deleted_upstream_whose_head_is_on_origin(self) -> None:
        slot = dataclasses.replace(DONE, pull_requests=(), head_on_origin=True)
        self.assertEqual(decide(slot).reason, "branch deleted on origin")

    def test_keeps(self) -> None:
        cases = {
            "detached HEAD": dataclasses.replace(DONE, branch=""),
            "used within the last hour": dataclasses.replace(DONE, idle_ms=HOUR - 1),
            "uncommitted changes": dataclasses.replace(DONE, dirty=True),
            "pull requests unknown": dataclasses.replace(DONE, pull_requests=None),
            "pull request #8 is open": dataclasses.replace(
                DONE,
                pull_requests=(
                    PullRequest(7, "MERGED", "h1"),
                    PullRequest(8, "OPEN", "h1"),
                ),
            ),
            # Commits after the merge that only this clone has.
            "unpushed commits": dataclasses.replace(DONE, head="h2"),
            # A closed pull request whose branch origin still has.
            "not merged": dataclasses.replace(
                DONE,
                pull_requests=(PullRequest(3, "CLOSED", "h1"),),
                branch_on_origin=True,
            ),
        }
        for reason, slot in cases.items():
            with self.subTest(reason):
                self.assertEqual(decide(slot), release_done.Verdict(False, reason))

    def test_keeps_a_branch_that_was_never_pushed(self) -> None:
        # A new session's branch: at origin/main, without upstream or pull request.
        slot = dataclasses.replace(
            DONE, pull_requests=(), head_on_origin=True, had_upstream=False
        )
        self.assertEqual(decide(slot), release_done.Verdict(False, "not merged"))


def run_git(directory: Path | str, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(directory), *arguments], check=True, capture_output=True
    )


class InspectCheckoutTest(unittest.TestCase):
    """The Git state of a clone of a temporary origin."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.origin = root / "origin.git"
        self.clone = root / "clone"
        run_git(
            root, "init", "--quiet", "--bare", "--initial-branch=main", str(self.origin)
        )
        run_git(root, "clone", "--quiet", str(self.origin), str(self.clone))
        for key, value in (("user.name", "Test"), ("user.email", "test@example.com")):
            run_git(self.clone, "config", key, value)
        self.commit("first")
        run_git(self.clone, "push", "--quiet", "origin", "HEAD:main")
        run_git(self.clone, "switch", "--quiet", "--create", "claude/x")

    def commit(self, name: str) -> None:
        (self.clone / name).write_text(name)
        run_git(self.clone, "add", name)
        run_git(self.clone, "commit", "--quiet", "--message", name)

    def inspect(self) -> Checkout:
        return release_done.inspect_checkout(self.clone, "claude/x")

    def test_a_new_branch(self) -> None:
        checkout = self.inspect()
        self.assertEqual(
            (checkout.dirty, checkout.head_on_origin, checkout.branch_on_origin),
            (False, True, False),
        )
        self.assertFalse(checkout.had_upstream)

    def test_untracked_and_modified_files_are_dirty(self) -> None:
        (self.clone / "new").write_text("new")
        self.assertTrue(self.inspect().dirty)
        (self.clone / "new").unlink()
        (self.clone / "first").write_text("changed")
        self.assertTrue(self.inspect().dirty)

    def test_ignored_files_are_not_dirty(self) -> None:
        (self.clone / ".git" / "info" / "exclude").write_text("bazel-*\n")
        (self.clone / "bazel-out").write_text("")
        self.assertFalse(self.inspect().dirty)

    def test_a_pushed_branch_then_deleted_on_origin(self) -> None:
        self.commit("second")
        run_git(self.clone, "push", "--quiet", "--set-upstream", "origin", "claude/x")
        checkout = self.inspect()
        self.assertEqual(
            (checkout.head_on_origin, checkout.branch_on_origin), (True, True)
        )
        self.assertTrue(checkout.had_upstream)
        run_git(self.clone, "push", "--quiet", "origin", "--delete", "claude/x")
        run_git(self.clone, "fetch", "--quiet", "--prune", "origin")
        checkout = self.inspect()
        self.assertEqual(
            (checkout.head_on_origin, checkout.branch_on_origin), (False, False)
        )
        self.assertTrue(checkout.had_upstream)

    def test_a_local_commit_is_not_on_origin(self) -> None:
        self.commit("second")
        self.assertFalse(self.inspect().head_on_origin)


class SweepTest(unittest.TestCase):
    """Which listed slots the sweep reads, releases and reports."""

    LISTING: ClassVar[dict] = {
        "pools": [
            {
                "slots": [
                    {
                        "slot": "done",
                        "state": "leased",
                        "owned_here": True,
                        "branch": "claude/done",
                        "idle_ms": 2 * HOUR,
                        "path": "/done",
                        "agent": {"kind": "k", "id": "i"},
                    },
                    {
                        "slot": "dirty",
                        "state": "leased",
                        "owned_here": True,
                        "branch": "claude/dirty",
                        "idle_ms": 2 * HOUR,
                        "path": "/dirty",
                    },
                    {
                        "slot": "busy",
                        "state": "leased",
                        "owned_here": True,
                        "branch": "claude/busy",
                        "idle_ms": 1,
                        "path": "/busy",
                    },
                    {
                        "slot": "free",
                        "state": "free",
                        "owned_here": True,
                        "branch": "",
                        "idle_ms": 2 * HOUR,
                        "path": "/free",
                    },
                    {
                        "slot": "other",
                        "state": "leased",
                        "owned_here": False,
                        "branch": "claude/other",
                        "idle_ms": 2 * HOUR,
                        "path": "/other",
                    },
                    {
                        "slot": "stranded",
                        "state": "leased",
                        "owned_here": True,
                        "stranded": True,
                        "branch": "claude/stranded",
                        "idle_ms": 2 * HOUR,
                        "path": "/stranded",
                    },
                ]
            }
        ]
    }

    def sweep(self, dry_run: bool, release_result: tuple[bool, str] = (True, "")) -> int:
        self.inspected, self.asked, self.released, self.lines = [], [], [], []

        def inspect(path: str, branch: str) -> Checkout:
            self.inspected.append(path)
            return Checkout(path == "/dirty", "h", False, False, True)

        def pull_requests(branch: str) -> tuple[PullRequest, ...]:
            self.asked.append(branch)
            return (PullRequest(1, "MERGED", "h"),)

        def release(entry: dict) -> tuple[bool, str]:
            self.released.append(entry["slot"])
            return release_result

        actions = release_done.Actions(
            inspect, pull_requests, None if dry_run else release
        )
        return release_done.sweep(self.LISTING, actions, self.lines.append)

    def test_releases_only_done_slots_of_this_clone(self) -> None:
        self.assertEqual(self.sweep(dry_run=False), 1)
        self.assertEqual(self.released, ["done"])
        self.assertEqual(self.inspected, ["/done", "/dirty"])
        # A dirty checkout stays without asking GitHub.
        self.assertEqual(self.asked, ["claude/done"])
        self.assertEqual(
            self.lines,
            [
                "release done claude/done: pull request #1 merged",
                "keep    dirty claude/dirty: uncommitted changes",
                "keep    busy claude/busy: used within the last hour",
            ],
        )

    def test_a_dry_run_releases_nothing(self) -> None:
        self.assertEqual(self.sweep(dry_run=True), 0)
        self.assertEqual(self.released, [])
        self.assertEqual(
            self.lines[0], "done    done claude/done: pull request #1 merged"
        )

    def test_reports_the_cli_refusal(self) -> None:
        self.assertEqual(
            self.sweep(dry_run=False, release_result=(False, " (holds work)")), 0
        )
        self.assertEqual(
            self.lines[0], "refused done claude/done: pull request #1 merged (holds work)"
        )


class GithubRepositoryTest(unittest.TestCase):
    def test_origin_urls(self) -> None:
        for url in (
            "https://github.com/autoload-dev/autoload.git",
            "git@github.com:autoload-dev/autoload.git",
            "ssh://git@github.com/autoload-dev/autoload",
        ):
            with self.subTest(url), tempfile.TemporaryDirectory() as clone:
                run_git(clone, "init", "--quiet")
                run_git(clone, "remote", "add", "origin", url)
                self.assertEqual(
                    release_done.github_repository(Path(clone)), "autoload-dev/autoload"
                )


if __name__ == "__main__":
    unittest.main()
