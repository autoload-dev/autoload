#!/bin/bash
# An Emscripten tool of this SDK repository, run by the toolchain's Python. Every path is
# relative to the execution root, so neither sandbox nor repository cache paths reach the
# command lines, the dependency files or the outputs.
set -euo pipefail
export EMSDK_ROOT="{SDK_ROOT}"
export EM_CONFIG="$EMSDK_ROOT/emscripten_config"
# The SDK is a read-only input: no bytecode beside its sources, no sanity file in its cache.
export PYTHONDONTWRITEBYTECODE=1
export EMCC_SKIP_SANITY_CHECK=1
exec "$EMSDK_PYTHON" "$EMSDK_ROOT/emscripten/{TOOL}.py" "$@"
