#!/usr/bin/env bash
set -euo pipefail
runfiles="${RUNFILES_DIR:-${TEST_SRCDIR:-$0.runfiles}}"
exec "$runfiles/{INSPECTOR}" {ARGUMENTS}
