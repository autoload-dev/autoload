#!/bin/bash
# buildmac48.sh <variant> <extra scons args...>: Godot 4.8-beta1 minimal macOS template, the bytecode compiler.
set -e
X=$(cd "$(dirname "$0")" && pwd)
V=$1; shift
cd "$X/src48/godot"
start=$(date +%s)
"$X/venv/bin/scons" -j12 platform=macos arch=arm64 target=template_release \
  modules_enabled_by_default=no module_gdscript_enabled=yes module_text_server_fb_enabled=yes \
  module_freetype_enabled=yes module_webp_enabled=yes \
  disable_physics_2d=yes disable_physics_3d=yes disable_navigation_2d=yes disable_navigation_3d=yes \
  disable_xr=yes disable_advanced_gui=yes disable_2d=yes vulkan=no metal=no rendering_device=no \
  accesskit=no sdl=no build_profile="$X/profile48/lichtpost48.gdbuild" \
  "$@" > "$X/buildmac48_$V.log" 2>&1
end=$(date +%s)
mkdir -p "$X/outmac48/$V"
cp bin/godot.macos.template_release.arm64 "$X/outmac48/$V/"
echo "variant $V done in $((end-start))s"
