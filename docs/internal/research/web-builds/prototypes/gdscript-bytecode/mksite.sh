#!/bin/bash
# mksite.sh <site name> <template zip> <pck>: a Lichtpost site from a template and a pack.
set -e
X=$(cd "$(dirname "$0")" && pwd)
S=$X/sites/$1; rm -rf "$S"; mkdir -p "$S"
cp $X/site_L/index.html $X/site_L/index.png $X/site_L/index.audio*.js "$S/"
cp "$3" "$S/index.pck"
unzip -o -q -j "$2" godot.wasm godot.js -d "$S"
mv -f "$S/godot.wasm" "$S/index.wasm"; mv -f "$S/godot.js" "$S/index.js"
W=$(stat -f%z "$S/index.wasm"); P=$(stat -f%z "$S/index.pck")
sed -i '' -E "s/\"index.wasm\": [0-9]+/\"index.wasm\": $W/; s/\"index.pck\": [0-9]+/\"index.pck\": $P/" "$S/index.html"
grep -o '"fileSizes": {[^}]*}' "$S/index.html"
