#!/bin/bash
# emcc/em++/emar from this SDK repository, with a Python from the toolchain's inputs.
# Every path is relative to the execution root: no `pwd -P`, so neither sandbox nor
# repository-cache paths reach the command lines, the .d files or the outputs.
set -euo pipefail
export EMSDK_ROOT="{SDK_ROOT}"
export EM_CONFIG="$EMSDK_ROOT/emscripten_config"
exec "$EMSDK_PYTHON" "$EMSDK_ROOT/emscripten/{TOOL}.py" "$@"
