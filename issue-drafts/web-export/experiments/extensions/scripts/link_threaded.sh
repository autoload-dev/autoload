#!/bin/bash
# Link a threaded side module from Bazel-compiled objects with a writable copy of the SDK's
# cache, because the SDK archive has no PIC crtbegin.o that -pthread side modules need.
# usage: link_threaded.sh <output base> <sdk repo name> <bazel bin dir> <work dir> <out.wasm>
set -euo pipefail
OB="$1"
REPO="$2"
BIN="$3"
WORK="$4"
OUT="$5"
SDK="$(cd "$OB/external/$REPO" && pwd -P)"
mkdir -p "$WORK"
rm -rf "$WORK/cache"
cp -cR "$SDK/emscripten/cache" "$WORK/cache"
chmod -R u+w "$WORK/cache"
cat >"$WORK/em_config" <<CFG
LLVM_ROOT = "$SDK/bin"
BINARYEN_ROOT = "$SDK"
EMSCRIPTEN_ROOT = "$SDK/emscripten"
CACHE = "$WORK/cache"
NODE_JS = "node-is-not-needed"
FROZEN_CACHE = False
CFG
EM_IGNORE_SANITY=1 EM_CONFIG="$WORK/em_config" python3 "$SDK/emscripten/em++.py" -shared -o "$OUT" \
    "$BIN/ext/_objs/web_hello.wasm/hello.pic.o" "$BIN/external/+godot_cpp_bindings+godot_cpp/libgodot_cpp.a" \
    -pthread -sSIDE_MODULE=1 -sWASM_BIGINT -sSUPPORT_LONGJMP=wasm
echo "generated in the cache:"
(cd "$WORK" && find cache -newer em_config -type f)
