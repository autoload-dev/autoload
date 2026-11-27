"""
Release the Aspect CLI worktree pool's slots whose work is done, so the pool keeps free, warm
slots instead of growing (docs/internal/agent-setup.md, "Worktrees").

A leased slot is done when its branch's pull request has merged, or its branch was deleted on
origin, and nothing in it would be lost: the checkout is clean, its HEAD is on origin or is the
head of that pull request, no pull request of the branch is open, and nothing has used the slot
for an hour. Each such slot is released as its holder would release it, with `aspect worktree
release`, which keeps the slot's output bases warm and refuses once more a checkout that holds
work. Everything else stays leased.

    release_done.py             release the done slots of the pool of the current checkout
    release_done.py --dry-run   only say which slots are done and why the others stay

It uses only the standard library, so hooks run it with any Python 3, and reports on stderr.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

# How long a slot must have been unused before it is released: a session that has just merged
# its pull request may still be looking at its checkout.
IDLE_GRACE_MS = 60 * 60 * 1000

# What reading a checkout raises when it is gone or Git cannot read it. A tuple of its own, so
# that the formatter keeps the `except` readable by the older Pythons hooks may run.
UNREADABLE = (subprocess.CalledProcessError, OSError)

# How long a fetch or a request to GitHub may take, within the hook's own time limit.
NETWORK_TIMEOUT_S = 30


@dataclasses.dataclass(frozen=True)
class PullRequest:
    """A pull request whose head is the slot's branch."""

    number: int
    state: str  # OPEN, MERGED or CLOSED, as `gh` reports it
    head: str  # the commit its head pointed at last


@dataclasses.dataclass(frozen=True)
class Slot:
    """What the decision reads about one leased slot."""

    slot: str
    branch: str
    idle_ms: int
    dirty: bool
    head_on_origin: bool  # some remote-tracking ref of the clone reaches HEAD
    head: str
    branch_on_origin: bool
    had_upstream: bool  # the branch was pushed with an upstream once
    pull_requests: tuple[PullRequest, ...] | None  # None when they could not be read

    @property
    def known_pull_requests(self) -> tuple[PullRequest, ...]:
        return self.pull_requests or ()


@dataclasses.dataclass(frozen=True)
class Verdict:
    release: bool
    reason: str


def _first(pull_requests: Iterable[PullRequest], state: str) -> PullRequest | None:
    return next((pr for pr in pull_requests if pr.state == state), None)


def _pushed(slot: Slot) -> bool:
    """Whether origin has the slot's HEAD, or had it as a pull request's head."""
    return slot.head_on_origin or slot.head in {
        pr.head for pr in slot.known_pull_requests
    }


def _blocker(slot: Slot) -> str:
    """Why the slot must stay leased whatever happened to its branch, or ""."""
    reasons = (
        (not slot.branch, "detached HEAD"),
        (slot.idle_ms < IDLE_GRACE_MS, "used within the last hour"),
        (slot.dirty, "uncommitted changes"),
        (slot.pull_requests is None, "pull requests unknown"),
    )
    for applies, reason in reasons:
        if applies:
            return reason
    opened = _first(slot.known_pull_requests, "OPEN")
    if opened:
        return f"pull request #{opened.number} is open"
    if not _pushed(slot):
        return "unpushed commits"
    return ""


def _deleted_on_origin(slot: Slot) -> bool:
    """Whether the branch was on origin once and is gone."""
    was_pushed = bool(slot.pull_requests) or slot.had_upstream
    return was_pushed and not slot.branch_on_origin


def _done(slot: Slot) -> str:
    """Why the slot's work is done, or ""."""
    merged = _first(slot.known_pull_requests, "MERGED")
    if merged:
        return f"pull request #{merged.number} merged"
    if _deleted_on_origin(slot):
        return "branch deleted on origin"
    return ""


def decide(slot: Slot) -> Verdict:
    """Whether a leased slot's work is done, and why it is or is not."""
    blocker = _blocker(slot)
    if blocker:
        return Verdict(False, blocker)
    done = _done(slot)
    return Verdict(True, done) if done else Verdict(False, "not merged")


def git(directory: Path | str, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(directory), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def git_succeeds(
    directory: Path | str, *arguments: str, timeout: float | None = None
) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), *arguments],
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


@dataclasses.dataclass(frozen=True)
class Checkout:
    """What Git says about a slot's checkout."""

    dirty: bool
    head: str
    head_on_origin: bool
    branch_on_origin: bool
    had_upstream: bool


def inspect_checkout(path: Path | str, branch: str) -> Checkout:
    """Read a checkout's state from Git; the clone's remote-tracking refs should be fresh."""
    head = git(path, "rev-parse", "HEAD")
    return Checkout(
        dirty=bool(git(path, "status", "--porcelain")),
        head=head,
        head_on_origin=bool(
            git(path, "for-each-ref", "--count=1", f"--contains={head}", "refs/remotes")
        ),
        branch_on_origin=git_succeeds(
            path, "show-ref", "--verify", "--quiet", f"refs/remotes/origin/{branch}"
        ),
        had_upstream=git_succeeds(path, "config", f"branch.{branch}.merge"),
    )


def github_repository(clone: Path) -> str:
    """origin as `gh --repo` takes it: [host/]owner/name."""
    url = git(clone, "remote", "get-url", "origin").removesuffix(".git")
    url = url.split("://", 1)[-1].split("@", 1)[-1].replace(":", "/", 1)
    return url.removeprefix("github.com/")


def pull_requests_from_gh(
    gh: str | None, repository: str
) -> Callable[[str], tuple[PullRequest, ...] | None]:
    """A function that lists a branch's pull requests with `gh`, None where that fails."""

    def pull_requests(branch: str) -> tuple[PullRequest, ...] | None:
        if gh is None:
            return None
        try:
            result = subprocess.run(
                [
                    gh,
                    "pr",
                    "list",
                    f"--repo={repository}",
                    f"--head={branch}",
                    "--state=all",
                    "--json=number,state,headRefOid",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=NETWORK_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return None
        if result.returncode != 0:
            return None
        return tuple(
            PullRequest(entry["number"], entry["state"], entry["headRefOid"])
            for entry in json.loads(result.stdout)
        )

    return pull_requests


def _leased_here(slot: dict) -> bool:
    if slot.get("state") != "leased" or slot.get("stranded"):
        return False
    return bool(slot.get("owned_here"))


def leased_slots(listing: dict) -> Iterable[dict]:
    """The slots of a `aspect worktree list --output=json` document that this clone leases."""
    for pool in listing.get("pools", []):
        yield from filter(_leased_here, pool.get("slots", []))


@dataclasses.dataclass(frozen=True)
class Actions:
    """How the sweep reads a slot's state and releases it."""

    inspect: Callable[[str, str], Checkout]
    pull_requests: Callable[[str], tuple[PullRequest, ...] | None]
    release: Callable[[dict], tuple[bool, str]] | None  # None for a dry run


def _verdict(entry: dict, branch: str, actions: Actions) -> Verdict:
    """The decision for one listed slot, reading only what it needs."""
    idle_ms = int(entry.get("idle_ms", 0))
    if not branch or idle_ms < IDLE_GRACE_MS:
        return decide(
            Slot(entry["slot"], branch, idle_ms, False, False, "", False, False, ())
        )
    try:
        checkout = actions.inspect(entry["path"], branch)
    except UNREADABLE:
        return Verdict(False, "checkout unreadable")
    # The pull requests cost a request to GitHub; a dirty checkout stays anyway.
    prs = () if checkout.dirty else actions.pull_requests(branch)
    return decide(
        Slot(entry["slot"], branch, idle_ms, pull_requests=prs, **vars(checkout))
    )


def sweep(listing: dict, actions: Actions, report: Callable[[str], None]) -> int:
    """Release the done slots of a listing; returns how many were released."""
    released = 0
    for entry in leased_slots(listing):
        branch = "" if entry.get("detached") else entry.get("branch", "")
        verdict = _verdict(entry, branch, actions)
        name = f"{entry['slot']} {branch or '(detached)'}"
        if not verdict.release:
            report(f"keep    {name}: {verdict.reason}")
        elif actions.release is None:
            report(f"done    {name}: {verdict.reason}")
        else:
            ok, detail = actions.release(entry)
            report(f"{'release' if ok else 'refused'} {name}: {verdict.reason}{detail}")
            released += ok
    return released


def _aspect_env() -> dict[str, str]:
    return {**os.environ, "DO_NOT_TRACK": "1"}


def release_with_aspect(aspect: str, clone: Path) -> Callable[[dict], tuple[bool, str]]:
    """A function that ends a slot's lease as its holder, through `aspect worktree release`."""

    def release(entry: dict) -> tuple[bool, str]:
        agent = entry.get("agent") or {}
        command = [aspect, "worktree", "release", entry["slot"]]
        # As the holder, so that only the CLI's own refusals for work in the checkout apply.
        if agent.get("kind"):
            command.append(f"--agent-kind={agent['kind']}")
        if agent.get("id"):
            command.append(f"--agent-id={agent['id']}")
        result = subprocess.run(
            command,
            cwd=clone,
            capture_output=True,
            text=True,
            check=False,
            env=_aspect_env(),
        )
        if result.returncode == 0:
            return True, ""
        lines = [line for line in result.stderr.splitlines() if line.strip()]
        return False, f" ({lines[-1].strip() if lines else f'exit {result.returncode}'})"

    return release


def _git_config(clone: Path, key: str) -> str:
    try:
        return git(clone, "config", key)
    except subprocess.CalledProcessError:
        return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1].strip())
    parser.add_argument(
        "--dry-run", action="store_true", help="release nothing, only report"
    )
    parser.add_argument(
        "--aspect", help="the Aspect CLI (default: on PATH or aspect.launcher)"
    )
    arguments = parser.parse_args(argv)

    common = Path(git(".", "rev-parse", "--path-format=absolute", "--git-common-dir"))
    clone = common.parent
    aspect = (
        arguments.aspect
        or shutil.which("aspect")
        or _git_config(clone, "aspect.launcher")
    )
    if not aspect:
        print(
            "release_done.py: the Aspect CLI is missing; run ./bootstrap.sh",
            file=sys.stderr,
        )
        return 1
    gh = shutil.which("gh") or next(
        (
            path
            for path in ("/opt/homebrew/bin/gh", "/usr/local/bin/gh")
            if os.access(path, os.X_OK)
        ),
        None,
    )
    # Fresh remote-tracking refs, so that merged and deleted branches show as such.
    if not git_succeeds(
        clone, "fetch", "--quiet", "--prune", "origin", timeout=NETWORK_TIMEOUT_S
    ):
        print(
            "release_done.py: fetching origin failed; releasing nothing", file=sys.stderr
        )
        return 1
    listing = json.loads(
        subprocess.run(
            [aspect, "worktree", "list", "--output=json"],
            cwd=clone,
            capture_output=True,
            text=True,
            check=True,
            env=_aspect_env(),
        ).stdout
    )
    actions = Actions(
        inspect=inspect_checkout,
        pull_requests=pull_requests_from_gh(gh, github_repository(clone)),
        release=None if arguments.dry_run else release_with_aspect(aspect, clone),
    )
    released = sweep(
        listing, actions, lambda line: print(f"release_done.py: {line}", file=sys.stderr)
    )
    if not arguments.dry_run:
        print(f"release_done.py: released {released} slot(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
