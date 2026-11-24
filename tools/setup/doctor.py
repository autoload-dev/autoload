"""
Check a checkout's setup and say what is missing (`aspect doctor`).

`aspect bootstrap` runs it last. A missing tool or Git hook that every change needs is an
error; what only some work needs, such as the Android SDK, Code Health's sign-in or Entire's
session capture, is a warning. It reads only the environment, Git's configuration and the
files the tools leave; it prints no secret.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from tools.android.sdk import NDK_VERSION, missing_packages

ROOT = Path(__file__).absolute().parents[2]
# The Git hooks `aspect bootstrap` configures, by event.
ASPECT_HOOKS = ("pre-commit", "pre-push")
# The Git hooks Entire installs carry this line and name the binary they run.
ENTIRE_MARKER = "# Entire CLI hooks"
QUOTED_PATH = re.compile(r"'(/[^']+/entire)'")


@dataclass(frozen=True)
class Finding:
    error: bool
    message: str


def error(message: str) -> Finding:
    return Finding(True, message)


def warning(message: str) -> Finding:
    return Finding(False, message)


def git_config(name: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "config", "--get", name],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def tool_findings(which=shutil.which) -> list[Finding]:
    """Bazelisk and the Aspect CLI, which every task needs."""
    return [
        error(f"`{name}` is not on PATH: run ./bootstrap.sh")
        for name in ("bazel", "aspect")
        if not which(name)
    ]


def hook_findings(config=git_config) -> list[Finding]:
    """The Git hooks that format, check and review every commit and push."""
    return [
        error(f"The {event} hook is not installed: run aspect bootstrap")
        for event in ASPECT_HOOKS
        if not config(f"hook.aspect-{event}.command")
    ]


def android_findings(env: dict[str, str]) -> list[Finding]:
    """The pinned Android SDK packages, which Android builds and the lanes need."""
    sdk = env.get("ANDROID_SDK_ROOT") or env.get("ANDROID_HOME")
    if not sdk:
        return [warning("No Android SDK is selected: run aspect bootstrap")]
    ndk = Path(env.get("ANDROID_NDK_HOME") or Path(sdk) / "ndk" / NDK_VERSION)
    missing = missing_packages(Path(sdk), ndk_root=ndk)
    if not missing:
        return []
    return [
        warning(
            f"The Android SDK at {sdk} lacks {', '.join(missing)}: run aspect bootstrap"
        )
    ]


def code_health_findings(env: dict[str, str]) -> list[Finding]:
    """CodeScene's sign-in, without which the hooks skip the Code Health review."""
    if env.get("CS_ACCESS_TOKEN"):
        return []
    return [
        warning(
            "CS_ACCESS_TOKEN is not set: the hooks review Code Health only with it or a "
            "`cs auth login` session (docs/internal/code-health.md#setup)"
        )
    ]


def entire_findings(root: Path, hooks: Path, which=shutil.which) -> list[Finding]:
    """Entire's session capture, when the repository enables it."""
    settings = root / ".entire/settings.json"
    if not settings.is_file() or not json.loads(settings.read_text()).get("enabled"):
        return []
    if not which("entire"):
        return [
            warning(
                "Entire is not on PATH, so agent sessions are not recorded "
                "(docs/internal/agent-setup.md#entire)"
            )
        ]
    installed = [
        hook
        for hook in sorted(hooks.glob("*"))
        if hook.is_file() and ENTIRE_MARKER in hook.read_text(errors="replace")
    ]
    if not installed:
        return [warning("Entire's Git hooks are not installed: run entire enable")]
    stale = sorted(
        {
            path
            for hook in installed
            for path in QUOTED_PATH.findall(hook.read_text(errors="replace"))
            if not Path(path).is_file()
        }
    )
    return [
        warning(
            f"Entire's Git hooks run {path}, which no longer exists: "
            "run entire configure --force"
        )
        for path in stale
    ]


def hooks_directory() -> Path:
    common = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return Path(common) / "hooks"


def main() -> int:
    env = dict(os.environ)
    findings = [
        *tool_findings(),
        *hook_findings(),
        *android_findings(env),
        *code_health_findings(env),
        *entire_findings(ROOT, hooks_directory()),
    ]
    for finding in findings:
        print(("error: " if finding.error else "warning: ") + finding.message)
    if not findings:
        print("The checkout is set up.")
    return 1 if any(finding.error for finding in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
