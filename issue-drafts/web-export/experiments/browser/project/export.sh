#!/bin/bash
# Exports the probe project with the pinned Godot editor and the official web templates.
# Usage: export.sh <godot-editor-binary> <templates-dir> <out-dir>
# Writes <out-dir>/<preset>/index.* for each preset below, and keeps the editor's data
# (editor settings, caches) inside <out-dir>/home instead of the user's home.
set -euo pipefail
GODOT=$1 TEMPLATES=$2 OUT=$3
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=$OUT/project
rm -rf "$WORK" && mkdir -p "$WORK" "$OUT/home"
cp "$HERE"/project.godot "$HERE"/main.tscn "$HERE"/main.gd "$WORK"/

# name  threads  pwa  debug-template  release-template
PRESETS=(
    "nt     false false web_nothreads_debug.zip web_nothreads_release.zip"
    "th     true  false web_debug.zip           web_release.zip"
    "th_pwa true  true  web_debug.zip           web_release.zip"
    "nt_pwa false true  web_nothreads_debug.zip web_nothreads_release.zip"
)
i=0
for row in "${PRESETS[@]}"; do
    read -r name threads pwa dbg rel <<<"$row"
    cat >>"$WORK/export_presets.cfg" <<CFG
[preset.$i]

name="$name"
platform="Web"
runnable=false
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter=""
exclude_filter=""
export_path=""
script_export_mode=2

[preset.$i.options]

custom_template/debug="$TEMPLATES/$dbg"
custom_template/release="$TEMPLATES/$rel"
variant/extensions_support=false
variant/thread_support=$threads
vram_texture_compression/for_desktop=true
vram_texture_compression/for_mobile=false
html/export_icon=true
html/custom_html_shell=""
html/head_include=""
html/canvas_resize_policy=2
html/focus_canvas_on_start=true
html/experimental_virtual_keyboard=false
progressive_web_app/enabled=$pwa
progressive_web_app/ensure_cross_origin_isolation_headers=true
progressive_web_app/offline_page=""
progressive_web_app/display=1
progressive_web_app/orientation=0

CFG
    i=$((i + 1))
done

export HOME=$OUT/home CFFIXED_USER_HOME=$OUT/home
"$GODOT" --headless --path "$WORK" --import >"$OUT/import.log" 2>&1 || true
for row in "${PRESETS[@]}"; do
    read -r name _ <<<"$row"
    for variant in release debug; do
        dest=$OUT/${name}_$variant
        rm -rf "$dest" && mkdir -p "$dest"
        "$GODOT" --headless --path "$WORK" "--export-$variant" "$name" "$dest/index.html" \
            >"$OUT/export_${name}_$variant.log" 2>&1
        echo "exported $dest: $(ls "$dest" | tr '\n' ' ')"
    done
done
