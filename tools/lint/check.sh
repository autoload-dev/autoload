#!/usr/bin/env bash
# The gate of the lint check, which the aspect `python` of check.bzl runs for each linted
# target: it prints the report of every linter that found something and then fails, or writes
# its stamp when all of them passed.
# Usage: check.sh <stamp> [<exit code file> <report>]...
set -u

stamp=$1
shift
status=0
while [ $# -gt 0 ]; do
    if [ "$(cat "$1")" != 0 ]; then
        cat "$2"
        status=1
    fi
    shift 2
done
if [ "$status" = 0 ]; then
    : >"$stamp"
fi
exit "$status"
