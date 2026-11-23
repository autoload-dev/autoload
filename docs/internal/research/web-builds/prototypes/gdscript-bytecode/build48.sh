#!/bin/bash
# build48.sh <variant> <extra scons args...>: Godot 4.8-beta1 minimal web template.
set -e
X=$(cd "$(dirname "$0")" && pwd)
V=$1; shift
source "$X/emsdk/emsdk_env.sh" >/dev/null 2>&1
cd "$X/src48/godot"
start=$(date +%s)
"$X/venv/bin/scons" -j12 platform=web target=template_release threads=no production=yes \
  modules_enabled_by_default=no module_gdscript_enabled=yes module_text_server_fb_enabled=yes \
  module_freetype_enabled=yes module_webp_enabled=yes \
  disable_physics_2d=yes disable_physics_3d=yes disable_navigation_2d=yes disable_navigation_3d=yes \
  disable_xr=yes disable_advanced_gui=yes rendering_device=no \
  "$@" > "$X/build48_$V.log" 2>&1
end=$(date +%s)
mkdir -p "$X/out48/$V"
cp bin/godot.web.template_release.wasm32.nothreads.zip "$X/out48/$V/"
echo "variant $V done in $((end-start))s"
