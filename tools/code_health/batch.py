"""Reviewing many files in one run of the CodeScene CLI, with each result cached.

`cs review` starts a JVM for each call, about 0.2 s, while one call reviews dozens of files
a second in parallel. The reviewer therefore writes the files to review into a scratch Git
repository that holds the chosen Code Health rules, which `cs` reads from its working
directory's repository, each at its own virtual path so that the rules' path globs match as
they would in the repository, and reviews them all at once; two revisions of one path go to
separate runs. Each result is cached under the CLI's identity, the rules, the file's virtual
path and its translated source, so a file that has not changed is not reviewed again.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from tools.code_health.translation import Translation


def cache_directory() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "autoload" / "code-health"


def cli_identity(cli: str, env: dict[str, str]) -> str | None:
    """
    What identifies the CLI's version for the cache, or None when nothing does.

    The binary's path, size and modification time cost no process; a mise shim resolves to
    mise itself, so for one the CLI is asked for its version.
    """
    binary = Path(cli).resolve()
    if binary.name == "cs":
        status = binary.stat()
        return f"{binary}:{status.st_size}:{status.st_mtime_ns}"
    result = subprocess.run(
        [cli, "version"], env=env, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() or None


def batches(translations: dict[str, Translation]) -> list[dict[str, Translation]]:
    """The translations by key, split so that no virtual path occurs twice in a batch."""
    split: list[dict[str, Translation]] = []
    for key, translation in translations.items():
        free = (
            b
            for b in split
            if all(t.virtual_name != translation.virtual_name for t in b.values())
        )
        batch = next(free, None)
        if batch is None:
            batch = {}
            split.append(batch)
        batch[key] = translation
    return split


def outside_repository(env: dict[str, str]) -> dict[str, str]:
    """
    The environment without Git's GIT_* variables, for work in the scratch repository.

    A Git hook exports GIT_DIR, GIT_WORK_TREE and GIT_INDEX_FILE; under them `git init`
    re-initializes the hook's repository, writing its worktree into the shared config's
    core.worktree, and `cs` reads that repository instead of the scratch one.
    """
    return {name: value for name, value in env.items() if not name.startswith("GIT_")}


def parse_row(line: str) -> dict | None:
    """A JSON object the CLI printed for a file, or None for any other output line."""
    try:
        row = json.loads(line)
    except ValueError:
        return None
    return row if isinstance(row, dict) else None


@dataclass(frozen=True)
class Reviewer:
    cli: str
    env: dict[str, str]
    identity: str | None  # the CLI's identity; None keeps the cache out of use
    rules: str | None  # the Code Health rules to apply, or None for CodeScene's defaults
    cache: Path

    def review(self, translations: list[Translation]) -> list[dict]:
        """
        The CLI's result for each translation, from the cache or from as few runs as
        possible; a file the CLI did not review gets its error under "error".
        """
        keys = [self.key(translation) for translation in translations]
        results = {key: self.cached(key) for key in keys}
        missing = {
            key: t
            for key, t in zip(keys, translations, strict=True)
            if results[key] is None
        }
        for batch in batches(missing):
            results.update(self.run(batch))
        return [results[key] or {} for key in keys]

    def key(self, translation: Translation) -> str:
        fields = [self.identity, self.rules, translation.virtual_name, translation.source]
        return hashlib.sha256(json.dumps(fields).encode()).hexdigest()

    def entry(self, key: str) -> Path:
        return self.cache / key[:2] / f"{key}.json"

    def cached(self, key: str) -> dict | None:
        if self.identity is None:
            return None
        try:
            return json.loads(self.entry(key).read_text())
        except OSError, ValueError:
            return None

    def store(self, key: str, result: dict) -> None:
        """Cache a result whole or not at all, also when another run writes it too."""
        if self.identity is None or "score" not in result:
            return
        entry = self.entry(key)
        entry.parent.mkdir(parents=True, exist_ok=True)
        temporary = entry.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(result))
        os.replace(temporary, entry)

    def run(self, batch: dict[str, Translation]) -> dict[str, dict]:
        """Review a batch in one run of the CLI and cache what it reviewed."""
        with tempfile.TemporaryDirectory(prefix="code-health-") as directory:
            workspace = Path(directory)
            self.prepare(workspace, batch)
            results = self.reviewed(workspace, batch)
        for key, result in results.items():
            self.store(key, result)
        return results

    def prepare(self, workspace: Path, batch: dict[str, Translation]) -> None:
        """Write the rules and each translation, at its virtual path, into the workspace."""
        subprocess.run(
            ["git", "init", "-q", str(workspace)],
            env=outside_repository(dict(os.environ)),
            check=True,
        )
        if self.rules is not None:
            (workspace / ".codescene").mkdir()
            (workspace / ".codescene" / "code-health-rules.json").write_text(self.rules)
        for translation in batch.values():
            path = workspace / translation.virtual_name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(translation.source)
        names = "\n".join(t.virtual_name for t in batch.values())
        (workspace / ".files.txt").write_text(names + "\n")

    def reviewed(self, workspace: Path, batch: dict[str, Translation]) -> dict[str, dict]:
        """The CLI's result for each file of the batch by key, or its error."""
        command = [
            self.cli,
            "review",
            "--file-list",
            ".files.txt",
            "--output-format",
            "jsonl",
        ]
        result = subprocess.run(
            command,
            cwd=workspace,
            env=outside_repository(self.env),
            capture_output=True,
            text=True,
            check=False,
        )
        rows = [row for row in map(parse_row, result.stdout.splitlines()) if row]
        by_path = {row.get("path"): row for row in rows}
        failed = {
            "error": result.stderr.strip()[:200] or f"cs exited with {result.returncode}"
        }
        return {
            key: by_path.get(translation.virtual_name, failed)
            for key, translation in batch.items()
        }
