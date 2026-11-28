#!/bin/bash
# An Emscripten tool of this SDK repository, run by the toolchain's Python. Every path is
# relative to the execution root, so neither sandbox nor repository cache paths reach the
# command lines, the dependency files or the outputs.
set -euo pipefail
export EMSDK_ROOT="{SDK_ROOT}"
export EM_CONFIG="$EMSDK_ROOT/emscripten_config"
exec "$EMSDK_PYTHON" "$EMSDK_ROOT/emscripten/{TOOL}.py" "$@"
