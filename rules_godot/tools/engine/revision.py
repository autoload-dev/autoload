"""
Write the build name, hash and time stamp a source-built engine names in its version.

A stamped build names the commit its workspace status reports as
STABLE_GIT_COMMIT, with the build name's suffix -git, and the commit time
STABLE_GIT_COMMIT_TIMESTAMP reports; otherwise the engine names the hash of its
declared inputs, with the suffix -bazel, and no time stamp. The recipe's hash covers its
custom modules' code by path; the code's contents, which come by label, join it here.
"""

import argparse
import hashlib
import re
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

COMMIT = "STABLE_GIT_COMMIT"
TIMESTAMP = "STABLE_GIT_COMMIT_TIMESTAMP"
_COMMIT = re.compile(r"[0-9a-f]{7,64}")
_TIMESTAMP = re.compile(r"[0-9]+")


class Revision(NamedTuple):
    """Where the hash comes from, the hash, and the Unix time of its commit."""

    origin: str
    hash: str
    timestamp: str = "0"


def _value(status: dict[str, str], key: str, pattern: re.Pattern[str], kind: str) -> str:
    value = status[key]
    if not pattern.fullmatch(value):
        raise SystemExit(f"{key} must be {kind}: {value!r}")
    return value


def revision(status: str, inputs_hash: str) -> Revision:
    """Return the workspace status's commit and its time, else the inputs hash."""
    values = {}
    for line in status.splitlines():
        key, _, value = line.partition(" ")
        values[key] = value.strip()
    if COMMIT not in values:
        return Revision("bazel", inputs_hash)
    commit = _value(values, COMMIT, _COMMIT, "a lowercase hexadecimal commit hash")
    if TIMESTAMP not in values:
        return Revision("git", commit)
    timestamp = _value(values, TIMESTAMP, _TIMESTAMP, "a Unix time in seconds")
    return Revision("git", commit, timestamp)


def code_hash(inputs_hash: str, code: Sequence[Path]) -> str:
    """The inputs hash with the contents of the custom modules' code, as long as a commit's."""
    if not code:
        return inputs_hash
    digest = hashlib.sha256(inputs_hash.encode())
    for path in code:
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()[:40]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--status", type=Path, help="stable-status.txt of a stamped build"
    )
    parser.add_argument("--build-name", required=True)
    parser.add_argument("--inputs-hash", required=True)
    parser.add_argument(
        "--code", type=Path, action="append", default=[], help="a custom module's file"
    )
    parser.add_argument("--build-output", type=Path, required=True)
    parser.add_argument("--hash-output", type=Path, required=True)
    parser.add_argument("--timestamp-output", type=Path, required=True)
    args = parser.parse_args()
    status = args.status.read_text(encoding="utf-8") if args.status else ""
    value = revision(status, code_hash(args.inputs_hash, args.code))
    args.build_output.write_text(f"{args.build_name}-{value.origin}", encoding="utf-8")
    args.hash_output.write_text(value.hash, encoding="utf-8")
    args.timestamp_output.write_text(value.timestamp, encoding="utf-8")


if __name__ == "__main__":
    main()
