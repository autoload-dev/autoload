import os
ROOT = os.environ["EMSDK_ROOT"]
LLVM_ROOT = os.path.join(ROOT, "bin")
BINARYEN_ROOT = ROOT
EMSCRIPTEN_ROOT = os.path.join(ROOT, "emscripten")
CACHE = os.path.join(ROOT, "emscripten", "cache")
FROZEN_CACHE = True
# Side modules need no JavaScript output, so no Node.js among the inputs.
NODE_JS = os.environ.get("EM_NODE_JS", "node-is-not-an-input")
