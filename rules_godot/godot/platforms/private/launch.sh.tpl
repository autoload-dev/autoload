#!/usr/bin/env bash
# bazel run on a godot_app: the host's python3 runs the launcher, which drives the
# host's devices whatever platform executed the build.
set -euo pipefail
runfiles="${RUNFILES_DIR:-${TEST_SRCDIR:-$0.runfiles}}"
exec python3 "$runfiles/{LAUNCHER}" "$runfiles/{MANIFEST}" "$runfiles" "$@"
