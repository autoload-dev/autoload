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

Sections: Decision, Git and GitHub, Sweep, Command line.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# ==== Decision ================================================================

# How long a slot must have been unused before it is released: a session that has just merged
# its pull request may still be looking at its checkout.
IDLE_GRACE_MS = 60 * 60 * 1000


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
    head_on_origin: bool  # a remote-tracking ref of origin reaches HEAD
    head: str
    branch_on_origin: bool
    had_upstream: bool  # the branch tracked a branch of origin once
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


def _merged(slot: Slot) -> PullRequest | None:
    """The merged pull request whose head is the slot's HEAD: later commits are not in it."""
    merged = (pr for pr in slot.known_pull_requests if pr.head == slot.head)
    return _first(merged, "MERGED")


def _done(slot: Slot) -> str:
    """Why the slot's work is done, or ""."""
    merged = _merged(slot)
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


# ==== Git and GitHub ==========================================================

# How long one fetch, request to GitHub or Aspect CLI call may take, and how long the whole
# sweep may spend reading and releasing: the hook that runs it has two minutes for this and
# for taking its own slot.
NETWORK_TIMEOUT_S = 15
SWEEP_BUDGET_S = 60


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


def _git_config(directory: Path | str, key: str) -> str:
    try:
        return git(directory, "config", key)
    except subprocess.CalledProcessError:
        return ""


@dataclasses.dataclass(frozen=True)
class Checkout:
    """What Git says about a slot's checkout."""

    dirty: bool
    head: str
    head_on_origin: bool  # a ref of origin reaches HEAD
    branch_on_origin: bool
    had_upstream: bool  # the branch tracked a branch of origin


# A checkout the decision does not need to read: its slot stays for another reason.
UNREAD = Checkout(
    dirty=False, head="", head_on_origin=False, branch_on_origin=False, had_upstream=False
)


def inspect_checkout(path: Path | str, branch: str) -> Checkout:
    """Read a checkout's state from Git; the clone's remote-tracking refs should be fresh."""
    head = git(path, "rev-parse", "HEAD")
    return Checkout(
        dirty=bool(git(path, "status", "--porcelain")),
        head=head,
        head_on_origin=bool(
            git(
                path,
                "for-each-ref",
                "--count=1",
                f"--contains={head}",
                "refs/remotes/origin",
            )
        ),
        branch_on_origin=git_succeeds(
            path, "show-ref", "--verify", "--quiet", f"refs/remotes/origin/{branch}"
        ),
        had_upstream=_git_config(path, f"branch.{branch}.remote") == "origin"
        and bool(_git_config(path, f"branch.{branch}.merge")),
    )


def github_repository(clone: Path) -> str:
    """origin as `gh --repo` takes it: [host/]owner/name."""
    url = git(clone, "remote", "get-url", "origin").removesuffix(".git")
    url = url.split("://", 1)[-1].split("@", 1)[-1]
    # host:owner/name of scp-like URLs, host:port/owner/name of ssh:// ones
    url = re.sub(r"^([^/:]+):(\d+/)?", r"\1/", url)
    return url.removeprefix("github.com/")


# What `gh`'s output raises when it is not the JSON asked for.
MALFORMED = (ValueError, KeyError, TypeError)


def pull_requests_from_gh(
    gh: str | None, repository: str, deadline: float
) -> Callable[[str], tuple[PullRequest, ...] | None]:
    """
    A function that lists a branch's pull requests with `gh`, None where that fails or the
    sweep's time is up.
    """

    def pull_requests(branch: str) -> tuple[PullRequest, ...] | None:
        if gh is None or time.monotonic() > deadline:
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
        try:
            return tuple(
                PullRequest(entry["number"], entry["state"], entry["headRefOid"])
                for entry in json.loads(result.stdout)
            )
        except MALFORMED:
            return None

    return pull_requests


# ==== Sweep ===================================================================


def _leased_here(slot: dict) -> bool:
    if slot.get("state") != "leased" or slot.get("stranded"):
        return False
    return bool(slot.get("owned_here"))


def leased_slots(listing: dict) -> Iterable[dict]:
    """The slots of a `aspect worktree list --output=json` document that this clone leases."""
    for pool in listing.get("pools", []):
        yield from filter(_leased_here, pool.get("slots", []))


# What reading a checkout raises when it is gone or Git cannot read it. A tuple of its own, so
# that the formatter keeps the `except` readable by the older Pythons hooks may run.
UNREADABLE = (subprocess.CalledProcessError, OSError)


@dataclasses.dataclass(frozen=True)
class Actions:
    """How the sweep reads a slot's state and releases it."""

    inspect: Callable[[str, str], Checkout]
    pull_requests: Callable[[str], tuple[PullRequest, ...] | None]
    release: Callable[[dict], tuple[bool, str]] | None  # None for a dry run


def _verdict(entry: dict, branch: str, actions: Actions) -> Verdict:
    """The decision for one listed slot, reading only what it needs."""
    idle_ms = int(entry.get("idle_ms") or 0)
    if not branch or idle_ms < IDLE_GRACE_MS:
        return decide(
            Slot(entry["slot"], branch, idle_ms, pull_requests=(), **vars(UNREAD))
        )
    try:
        checkout = actions.inspect(entry.get("path", ""), branch)
    except UNREADABLE:
        return Verdict(False, "checkout unreadable")
    # The pull requests cost a request to GitHub; a dirty checkout stays anyway.
    prs = () if checkout.dirty else actions.pull_requests(branch)
    return decide(
        Slot(entry["slot"], branch, idle_ms, pull_requests=prs, **vars(checkout))
    )


def _branch(entry: dict) -> str:
    return "" if entry.get("detached") else entry.get("branch", "")


def sweep(listing: dict, actions: Actions, report: Callable[[str], None]) -> int:
    """Release the done slots of a listing; returns how many were released."""
    entries = list(leased_slots(listing))
    # Reading the slots costs Git and GitHub round trips each; the hook waits for them.
    with ThreadPoolExecutor(max_workers=8) as pool:
        verdicts = list(
            pool.map(lambda entry: _verdict(entry, _branch(entry), actions), entries)
        )
    released = 0
    for entry, verdict in zip(entries, verdicts):
        name = f"{entry['slot']} {_branch(entry) or '(detached)'}"
        if not verdict.release:
            report(f"keep    {name}: {verdict.reason}")
        elif actions.release is None:
            report(f"done    {name}: {verdict.reason}")
        else:
            ok, detail = actions.release(entry)
            report(f"{'release' if ok else 'refused'} {name}: {verdict.reason}{detail}")
            released += ok
    return released


# ==== Command line ============================================================


def _aspect_env() -> dict[str, str]:
    return {**os.environ, "DO_NOT_TRACK": "1"}


def release_with_aspect(
    aspect: str, clone: Path, deadline: float
) -> Callable[[dict], tuple[bool, str]]:
    """
    A function that ends a slot's lease as its holder, through `aspect worktree release`,
    until the sweep's time is up.
    """

    def release(entry: dict) -> tuple[bool, str]:
        if time.monotonic() > deadline:
            return False, " (out of time; the next sweep releases it)"
        agent = entry.get("agent") or {}
        command = [aspect, "worktree", "release", entry["slot"]]
        # As the holder, so that only the CLI's own refusals for work in the checkout apply.
        if agent.get("kind"):
            command.append(f"--agent-kind={agent['kind']}")
        if agent.get("id"):
            command.append(f"--agent-id={agent['id']}")
        try:
            result = subprocess.run(
                command,
                cwd=clone,
                capture_output=True,
                text=True,
                check=False,
                env=_aspect_env(),
                timeout=NETWORK_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return False, " (the Aspect CLI took too long)"
        if result.returncode == 0:
            return True, ""
        lines = [line for line in result.stderr.splitlines() if line.strip()]
        return False, f" ({lines[-1].strip() if lines else f'exit {result.returncode}'})"

    return release


def _gh() -> str | None:
    """GitHub's CLI, also where Homebrew puts it when a hook's PATH is short."""
    candidates = [shutil.which("gh") or "", "/opt/homebrew/bin/gh", "/usr/local/bin/gh"]
    return next((path for path in candidates if path and os.access(path, os.X_OK)), None)


def _pool_listing(aspect: str, clone: Path) -> dict:
    """The pool of the clone as `aspect worktree list --output=json` describes it."""
    result = subprocess.run(
        [aspect, "worktree", "list", "--output=json"],
        cwd=clone,
        capture_output=True,
        text=True,
        check=True,
        env=_aspect_env(),
        timeout=NETWORK_TIMEOUT_S,
    )
    return json.loads(result.stdout)


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
    deadline = time.monotonic() + SWEEP_BUDGET_S
    # Fresh remote-tracking refs, so that merged and deleted branches show as such.
    if not git_succeeds(
        clone, "fetch", "--quiet", "--prune", "origin", timeout=NETWORK_TIMEOUT_S
    ):
        print(
            "release_done.py: fetching origin failed; releasing nothing", file=sys.stderr
        )
        return 1
    actions = Actions(
        inspect=inspect_checkout,
        pull_requests=pull_requests_from_gh(_gh(), github_repository(clone), deadline),
        release=None
        if arguments.dry_run
        else release_with_aspect(aspect, clone, deadline),
    )
    released = sweep(
        _pool_listing(aspect, clone),
        actions,
        lambda line: print(f"release_done.py: {line}", file=sys.stderr),
    )
    if not arguments.dry_run:
        print(f"release_done.py: released {released} slot(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
