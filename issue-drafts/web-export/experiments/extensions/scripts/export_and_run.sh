#!/bin/bash
# Export the test project with each preset and run every case in headless Chrome.
# usage: export_and_run.sh <godot editor> <project dir> <out dir>
set -uo pipefail
G="$1"
P="$2"
OUT="$3"
HERE="$(cd "$(dirname "$0")" && pwd)"
"$G" --headless --path "$P" --import >/dev/null 2>&1
for preset in WebNoThreads WebThreads; do
    dir="$OUT/$preset"
    rm -rf "$dir"
    mkdir -p "$dir"
    "$G" --headless --path "$P" --export-debug "$preset" "$dir/index.html" >"$dir.export.log" 2>&1
    echo "== $preset: $(grep -o '"gdextensionLibs":[^]]*]' "$dir/index.html")"
done
for case in "WebNoThreads" "WebNoThreads --isolation" "WebThreads --isolation" "WebThreads"; do
    set -- $case
    echo "== run $case"
    python3 -I "$HERE/run_in_chrome.py" "$OUT/$1" ${2:-} --timeout=45 2>&1 | grep "WEBHELLO\|VERDICT\|Build configuration\|rror\|xception\|abort" | grep -v "AudioWorkletNode"
done
