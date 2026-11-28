#!/usr/bin/env bash
write_module() {
    cat >MODULE.bazel <<EOF
module(name = "q5")

bazel_dep(name = "platforms", version = "1.1.0")
bazel_dep(name = "rules_cc", version = "0.2.28")
EOF
    for d in "$@"; do
        case $d in
            fallback) printf 'bazel_dep(name = "web_cc_fallback")\nlocal_path_override(module_name = "web_cc_fallback", path = "fallback")\n' >>MODULE.bazel ;;
            emsdk) printf 'bazel_dep(name = "emsdk", version = "7.0.0")\nemscripten_deps = use_extension("@emsdk//:emscripten_deps.bzl", "emscripten_deps")\nemscripten_deps.config(version = "4.0.20")\n' >>MODULE.bazel ;;
        esac
    done
}
