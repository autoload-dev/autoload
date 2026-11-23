#!/bin/bash
# replays.sh <engine> <pck>: Lichtpost's replay results on an engine and pack.
L=$(git rev-parse --show-toplevel)/rules_godot/examples/projects/lichtpost
for r in delivery fall pipe; do
  printf "%-9s %s\n" "$r" "$(perl -e 'alarm 60; exec @ARGV' "$1" --headless --main-pack "$2" -- --replay="$L/tests/$r.json" 2>&1 | grep LICHTPOST_RESULT)"
done
