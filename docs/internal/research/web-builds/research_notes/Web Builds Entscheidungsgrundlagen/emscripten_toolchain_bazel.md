# Emscripten C++ toolchain in Bazel (Bzlmod) and unsupported native targets on the web platform

Research date: 2026-11-23. Bazel used for experiments: 9.3.0 (the repository's `.bazelversion`). Godot sources read locally: Godot 4.7.2-stable source and export templates from the Bazel repository cache, and godot-cpp as fetched by the examples. "Local source" citations give absolute paths on this Mac. "Local experiment" findings come from throwaway workspaces that were built during this research; their BUILD content is quoted so that they can be reproduced.

## 1. Options for an Emscripten toolchain in Bazel (late 2026)

### Takeaway
The only Bazel toolchain that targets `wasm32-unknown-emscripten` is emsdk's own (`emscripten-core/emsdk`, `bazel/` directory). It is on the BCR as module `emsdk`, version 7.0.0 published 2026-11-07, and it is Bzlmod-only. Its module registers C++ toolchains for target `@platforms//cpu:wasm32` on five execution platforms. The Emscripten version is chosen by the singleton extension `emscripten_deps.config(version = ...)`, which accepts any version from 3.1.x to 7.0.0. toolchains_llvm and hermetic_cc_toolchain (zig) support only freestanding or WASI wasm, not Emscripten.

### Cited Findings
- The BCR lists `emsdk` versions 4.0.13 to 7.0.0, 25 versions in all. 7.0.0 was published 2026-11-07 and 6.0.13 on 2026-10-20, and the earliest listed, 4.0.13, is from 2025-08-26. None are yanked. The maintainers are Sam Clegg (sbc100) and Nenad Mikša (DoDoENT). — [BCR emsdk](https://registry.bazel.build/modules/emsdk); [BCR metadata.json](https://raw.githubusercontent.com/bazelbuild/bazel-central-registry/main/modules/emsdk/metadata.json)
- emsdk 7.0.0's MODULE.bazel depends on platforms 1.0.0, bazel_skylib 1.8.2, rules_nodejs 6.7.3 (`node.toolchain(node_version = "20.18.0")`), rules_cc 0.2.16 and rules_python 1.8.4 (`python.toolchain(python_version = "3.14")`). It calls `use_repo` on five `emscripten_bin_{linux,linux_arm64,mac,mac_arm64,win}` repositories and on `emscripten_cache`. It runs `register_toolchains` for `//emscripten_toolchain:cc-toolchain-wasm-emscripten_{linux,linux_arm64,mac,mac_arm64,win}`. The source archive is `github.com/emscripten-core/emsdk/archive/refs/tags/7.0.0.tar.gz` with `strip_prefix = "emsdk-7.0.0/bazel"`. — [BCR emsdk 7.0.0 MODULE.bazel](https://raw.githubusercontent.com/bazelbuild/bazel-central-registry/main/modules/emsdk/7.0.0/MODULE.bazel); [source.json](https://raw.githubusercontent.com/bazelbuild/bazel-central-registry/main/modules/emsdk/7.0.0/source.json)
- The README says WORKSPACE support was removed and that 4.0.6 was the last version to support it. Bzlmod is the only integration, with `bazel_dep(name = "emsdk")` (or a `git_override` with `strip_prefix = "bazel"`). The README also says to add `--incompatible_enable_cc_toolchain_resolution` to `.bazelrc`. — [emsdk bazel/README.md](https://github.com/emscripten-core/emsdk/blob/main/bazel/README.md)
- Version choice (from `emscripten_deps.bzl` in 7.0.0):
  - The extension collects `config(version = ...)` tags from **all** modules and fails with `"More than one emscripten version specified!"` if more than one module sets one. Without a tag it uses `"latest"`, the highest key in `revisions.bzl`.
  - Allowed values are `["latest"] + EMSCRIPTEN_TAGS.keys()`. That list contains 146 versions, among them 4.0.11, 4.0.20, 6.0.12 and 7.0.0, back to 3.1.x.
  - Binaries come from `https://storage.googleapis.com/webassembly/emscripten-releases-builds/{os}/{hash}/wasm-binaries{-arm64}.{tar.xz|zip}`, pinned by sha256.

  — [emsdk 7.0.0 tag, bazel/emscripten_deps.bzl and revisions.bzl](https://github.com/emscripten-core/emsdk/tree/7.0.0/bazel)
- Toolchain declaration (`remote_emscripten_repository.bzl`, `create_toolchains`): `native.toolchain(name = "cc-toolchain-wasm-" + name, target_compatible_with = ["@platforms//cpu:wasm32"], exec_compatible_with = exec_compatible_with, toolchain_type = "@rules_cc//cc:toolchain_type")`.
  - The exec constraints are linux/x86_64, linux/arm64, macos/x86_64, macos/arm64 and windows/x86_64.
  - There is **no `@platforms//os:emscripten` target constraint and no wasm64 toolchain**.
  - The module also defines `@emsdk//:platform_wasm` (`cpu:wasm32` + `os:emscripten`) and `@emsdk//:platform_wasi` (`cpu:wasm32` + `os:wasi`).

  — [emsdk 7.0.0 bazel/remote_emscripten_repository.bzl, emscripten_toolchain/BUILD.bazel, BUILD](https://github.com/emscripten-core/emsdk/tree/7.0.0/bazel)
- `wasm_cc_binary` (in `@emsdk//emscripten_toolchain:wasm_rules.bzl`) applies a transition. The transition sets `--platforms=@emsdk//:platform_wasm` (or `platform_wasi` when `standalone`), the legacy `--cpu=wasm`/`--compiler=emscripten`, `--dynamic_mode=off`, `--custom_malloc=@emsdk//emscripten_toolchain:malloc`, and features from the `threads` (`use_pthreads`), `simd` (`wasm_simd`, `wasm_relaxed_simd`) and `exit_runtime` attributes. The rule then unpacks the link output, a tar of `.js`/`.wasm`/`.data`/`.html`/etc. — [emsdk 7.0.0 bazel/emscripten_toolchain/wasm_cc_binary.bzl](https://github.com/emscripten-core/emsdk/tree/7.0.0/bazel/emscripten_toolchain)
- Issue #919 (opened 2021-10-26, still open in 2026) records that the toolchain historically used a `wasm` CPU name rather than `@platforms//cpu:wasm32`. A maintainer agreed it should move to the platforms constraint. — [emsdk #919](https://github.com/emscripten-core/emsdk/issues/919)
- toolchains_llvm knows the target pairs `("none","wasm32")`, `("none","wasm64")`, `("wasip1","wasm32")` and `("wasip1","wasm64")`. There is no Emscripten target. — [toolchains_llvm toolchain/internal/common.bzl](https://github.com/bazel-contrib/toolchains_llvm/blob/master/toolchain/internal/common.bzl)
- hermetic_cc_toolchain (zig cc) offers `@zig_sdk//toolchain:wasip1_wasm`, which is WASI and not Emscripten. — [hermetic_cc_toolchain README](https://github.com/uber/hermetic_cc_toolchain/blob/main/README.md)
- IREE defines its own freestanding wasm32 and wasm32-wasi toolchains on top of rules_cc with clang and wasi-sdk, which is again not Emscripten. — [IREE build_tools/bazel/wasm/BUILD.bazel](https://opensecura.googlesource.com/3p/openxla/iree/+/HEAD/build_tools/bazel/wasm/BUILD.bazel)
- Bazel 9 compatibility: issue #1642 ("emsdk can't be used with Bazel 9/10", opened 2025-12-12) was closed after fixes. A maintainer says "We certainly test with bazel 9 these days". — [emsdk #1642](https://github.com/emscripten-core/emsdk/issues/1642)

### Inferences
- Godot's side modules must be linked against Emscripten's JS runtime and its dynamic-linking ABI (`dylink.0`, `SIDE_MODULE`/`MAIN_MODULE`). A WASI or freestanding clang toolchain cannot produce them. emsdk's toolchain, or a custom rules_cc toolchain that wraps the same Emscripten release archives, are the realistic options.
- emsdk registers its toolchains from its own MODULE.bazel. Any `bazel_dep(name = "emsdk")` anywhere in the graph therefore makes a `cpu:wasm32` C++ toolchain available. rules_godot's `web_wasm32` (`os:emscripten` + `cpu:wasm32`) would match it without further constraints.
- Because emsdk's toolchain only constrains `cpu:wasm32`, it would also match a WASI platform. That does not matter for rules_godot.

### Gaps
- I did not verify a build of godot-cpp with emsdk's Bazel toolchain. All flag compatibility statements below come from source reading.
- The LLVM/clang version bundled with Emscripten 4.0.20 was not checked (see the clang include-path issue in section 3).

## 2. Hermeticity, remote execution, hosts, downloads, size and cache

### Takeaway
emsdk's toolchain is hermetic in principle: it uses pinned Emscripten archives, a rules_python 3.14 interpreter and a rules_nodejs Node 20.18.0, all fetched by Bazel. It declares Linux x86_64/arm64 execution platforms, so Linux remote executors are covered. Three things cost money or cache hits:
- Each per-host archive is about 280–355 MB compressed.
- The Emscripten system-library cache is built by a repository rule on the host when non-default variants (PIC, LTO, wasm64) are needed. Users report non-deterministic outputs from that step, which invalidate the remote cache.
- There is only one cache configuration per build graph.

### Cited Findings
- Download sizes from GCS `Content-Length`, measured 2026-11-23:

  | Emscripten | linux x86_64 | linux arm64 | mac arm64 |
  | --- | --- | --- | --- |
  | 4.0.20 | 354,605,144 B | 336,914,796 B | 297,205,984 B |
  | 6.0.12 | 304,160,128 B | 283,863,684 B | 280,157,468 B |
  | 7.0.0 | 322,310,412 B | 300,955,976 B | 293,601,928 B |

  — URLs built from [emsdk revisions.bzl](https://github.com/emscripten-core/emsdk/blob/7.0.0/bazel/revisions.bzl), for example `https://storage.googleapis.com/webassembly/emscripten-releases-builds/linux/c387d7a7e9537d0041d2c3ae71b7538cc978104e/wasm-binaries.tar.xz` (4.0.20)
- The archive contains clang/wasm-ld and the LLVM tools, binaryen (`wasm-opt`, `wasm-emscripten-finalize`, `wasm-metadce`, …), the `emscripten/` Python tree with `node_modules` (closure compiler), and a prebuilt default sysroot cache (`emscripten/cache/sysroot`). The filegroups `compiler_files` and `linker_files` select from it. — [emsdk 7.0.0 bazel/emscripten_build_file.bzl](https://github.com/emscripten-core/emsdk/blob/7.0.0/bazel/emscripten_build_file.bzl)
- The wrappers `emcc.sh`, `emcc_link.sh` and `emar.sh` are bash scripts. They `source env.sh`, which sets `ROOT_DIR=$(pwd -P)`, `EMSCRIPTEN`, `EM_CONFIG` and `EMSDK_PYTHON` relative to the execroot, and then run the Bazel Python on `emcc.py`. The generated `emscripten_config` sets `FROZEN_CACHE = True`. Its `CLOSURE_COMPILER` points at Node and `cli.js` explicitly, "to work around an issue with Bazel RBE where the symlinks in node_modules/.bin are uploaded as the linked files". — [emsdk 7.0.0 bazel/emscripten_toolchain/{env.sh,emcc.sh,default_config}](https://github.com/emscripten-core/emsdk/tree/7.0.0/bazel/emscripten_toolchain)
- The toolchain's `common_files` include `@emscripten_cache//:emscripten_config`, `@emscripten_cache//:emscripten_cache`, `@rules_nodejs//nodejs:current_node_toolchain` and a Python interpreter target. — [emsdk 7.0.0 bazel/remote_emscripten_repository.bzl](https://github.com/emscripten-core/emsdk/blob/7.0.0/bazel/remote_emscripten_repository.bzl)
- Cache extension (`emscripten_cache.bzl`):
  - Without tags, `@emscripten_cache//:emscripten_cache` is an alias to the host's `emscripten_bin_*//:builtin_cache`. The repository rule picks it with `repository_ctx.os`, so on a macOS arm64 host it points at `@emscripten_bin_mac_arm64`.
  - With `configuration(flags = [...])` or `targets(...)`, the repository rule runs `embuilder build <targets or ALL>` **on the host** during fetch to build a secondary cache.
  - With `prebuilt_cache(http_archive_url, sha256, strip_prefix)`, it downloads a cache instead, and that takes precedence.
  - The tags of all modules are merged, so there is a single `emscripten_cache` repository per graph.

  — [emsdk 7.0.0 bazel/emscripten_cache.bzl](https://github.com/emscripten-core/emsdk/blob/7.0.0/bazel/emscripten_cache.bzl); [README](https://github.com/emscripten-core/emsdk/blob/main/bazel/README.md)
- The README says the default cache does not include LTO, 64-bit or PIC builds of the system libraries and ports. Those need `emscripten_cache.configuration`/`targets` or a `prebuilt_cache`. — [emsdk bazel/README.md](https://github.com/emscripten-core/emsdk/blob/main/bazel/README.md)
- Issue #1581 ("Bazel support for multiple emscripten caches", opened 2025-08-04, open):
  - LTO and non-LTO configurations cannot coexist.
  - The documented targets were incomplete; the reporter had to list `crtbegin`, `libc-mt` and `libc++-mt-noexcept`, among others.
  - The reporter wrote that CI machines "occasionally need to rebuild this cache, and this results in different binaries (different hashes), which completely invalidates the build cache".

  — [emsdk #1581](https://github.com/emscripten-core/emsdk/issues/1581)
- Issue #1675 ("Bazel toolchain uses system python on MacOS") was closed 2026-02-24. Issue #1263 (use the Bazel Python via py_binary) is still open. — [emsdk #1675](https://github.com/emscripten-core/emsdk/issues/1675); [emsdk #1263](https://github.com/emscripten-core/emsdk/issues/1263)
- Godot's own CI installs Emscripten with `emscripten-core/setup-emsdk@v16` and `no-cache: true` on `ubuntu-24.04`, with a 60-minute job timeout. — Local source `.../54778939-c1da-48e8-9545-4f94becb5969/.github/workflows/web_builds.yml` (Godot 4.7.2 source in the Bazel repository cache)

### Inferences
- Remote execution on BuildBuddy's Linux x86_64 executors should resolve `emscripten_linux`. Every compile action then ships the clang binaries, the Python tree, the sysroot headers and Node as inputs. That is a large input root, but it is content-addressed and uploaded once. The bash wrappers need `/bin/bash` on the executor image.
- On a macOS host with remote execution, the host's `@emscripten_cache` alias points at the **mac** archive's builtin cache, and that alias is part of the Linux toolchain's `common_files`. Such builds would likely fetch both the mac (~297 MB) and the linux (~355 MB) archive. The cache directory's bytes should be identical across hosts (wasm objects), which needs an experiment to confirm.
- A secondary cache (`--pic`, `--lto=thin`, which a dlink engine build or LTO needs) is built by embuilder in a repository rule on each machine. It is not a Bazel action, so it is neither remotely cached nor remotely executed. Per #1581 it can be non-deterministic and thereby defeat cross-machine cache hits. A `prebuilt_cache` archive hosted by the ruleset or consumer avoids both problems.
- The extension is a singleton: one Emscripten version and one cache configuration per build graph. A ruleset that sets `emscripten_deps.config` or `emscripten_cache.configuration` imposes them on every consumer, and conflicts with a consumer that sets its own version.

### Gaps
- I found no public report of emsdk's toolchain on BuildBuddy or another RBE service beyond the closure-compiler symlink workaround. RBE with a macOS host is unverified.
- The secondary-cache build time (embuilder `ALL`) was not measured.

## 3. Side modules (`.wasm`) with rules_cc and emsdk's toolchain

### Takeaway
emsdk's Bazel toolchain does not support shared libraries well. It disables `supports_pic` and `supports_dynamic_linker`, and `cc_binary(linkshared = True)` fails with Emscripten 6+ because objects are not compiled with `-fPIC`. Issue #1714 (open) defers "true shared libraries in bazel" until after Emscripten 6.0. A GDExtension side module therefore needs either `-fPIC -sSIDE_MODULE=1` (plus the ABI flags below) forced onto **every** compile in the extension's transitive closure, godot-cpp included, or a custom or extended toolchain config with those flags as features.

### Cited Findings
- Toolchain features (`toolchain.bzl`, emsdk 7.0.0):
  - `feature(name = "supports_pic", enabled = False)` and `feature(name = "supports_dynamic_linker", enabled = False)`.
  - A `pic` feature exists and adds `-fPIC` only `expand_if_available = "pic"`.
  - `cpp_link_dynamic_library` and `cpp_link_nodeps_dynamic_library` get `-shared`.
  - A `use_pthreads` feature adds `-pthread`.
  - Other features: `wasm_simd`, `wasm_relaxed_simd`, `wasm_warnings_as_errors`, `wasm_asan`, `wasm_ubsan`, `wasm_standalone`, `exit_runtime`, `output_format_js`, `wasm_exceptions`.

  — [emsdk 7.0.0 bazel/emscripten_toolchain/toolchain.bzl](https://github.com/emscripten-core/emsdk/blob/7.0.0/bazel/emscripten_toolchain/toolchain.bzl)
- Issue #1714 ("bazel build seems to have trouble with the transition to true shared libraries", opened 2026-06-01, open):
  - After emscripten PR 25930, a `cc_binary` with `linkshared = True` fails with `wasm-ld: error: ... relocation R_WASM_MEMORY_ADDR_SLEB ...`.
  - A co-maintainer wrote "I've never seen `linkshared` working with emscripten".
  - sbc100 wrote: "Once emscripten 6.0.0 ships we can try to enable true shared libraries in bazel. I'll leave this bug open for that."

  — [emsdk #1714](https://github.com/emscripten-core/emsdk/issues/1714)
- Emscripten's Dynamic Linking docs (headed "7.0.2-git (dev)", marked "somewhat outdated"):
  - "These days Emscripten will produce real dynamic libraries by default when `-shared` is used."
  - An explicit `SIDE_MODULE` setting takes precedence.
  - `SIDE_MODULE=2` exports only what you ask for, while `SIDE_MODULE=1` exports all default-visibility symbols.
  - "only the main module is linked against system libraries".
  - "Dynamic linking + pthreads is still experimental".

  — [Emscripten Dynamic Linking](https://emscripten.org/docs/compiling/Dynamic-Linking.html)
- Issue #1580 (open since 2025-08-01): the toolchain hard-codes the clang resource include directory and has to be updated by hand for each clang bump. In 7.0.0, `toolchain.bzl` passes `-isystem <emscripten>/lib/clang/24/include` but lists `lib/clang/21/include` in `cxx_builtin_include_directories`. — [emsdk #1580](https://github.com/emscripten-core/emsdk/issues/1580); [toolchain.bzl](https://github.com/emscripten-core/emsdk/blob/7.0.0/bazel/emscripten_toolchain/toolchain.bzl)
- Other open usability issues: #972 (closed; forcing copts/linkopts for `wasm_cc_binary` and its dependencies), #1400 (feature flags for the toolchain), and #1689 (emsdk ≥5.0.2 fails in rules_foreign_cc cmake). — [emsdk issues](https://github.com/emscripten-core/emsdk/issues?q=bazel)
- godot-cpp's web tool (`tools/web.py`):
  - The flags are CC=`emcc` and CXX=`em++`.
  - `-sSIDE_MODULE=1` goes on compile **and** link.
  - `-sUSE_PTHREADS=1` goes on compile and link if `threads`.
  - `-sWASM_BIGINT` goes on link, with the comment "This must match the flag used to build Godot (true in official builds since 4.3)".
  - `-sSUPPORT_LONGJMP='wasm'` goes on compile and link.
  - Defines: `WEB_ENABLED` and `UNIX_ENABLED`.
  - LTO is `full` by default.
  - Only `arch=wasm32` is supported, and `SHLIBSUFFIX` is `.wasm`.

  — Local source `<bazel-output-user-root>/eeca9632300f1e4a84a8ad7867b8ecd2/external/+godot_cpp_bindings+godot_cpp/tools/web.py`
- Godot's engine (`platform/web/detect.py`, 4.7.2) with `dlink_enabled`:
  - Compiles and links the engine with `-sSIDE_MODULE=2` and `-fvisibility=hidden` into `godot.side.wasm`.
  - Links a small main module with `-s MAIN_MODULE=1 -s EXPORT_ALL=1` (`platform/web/SCsub`).
  - Always passes `-sWASM_BIGINT`, `-sSUPPORT_LONGJMP='wasm'`, `-sMEMORY64=0` for wasm32, and `-msimd128` when `wasm_simd`, which defaults to true.
  - Threads use `-sUSE_PTHREADS=1` on compile and link.

  — Local source `.../54778939-c1da-48e8-9545-4f94becb5969/platform/web/detect.py` and `platform/web/SCsub`
- The godot-rust book says the extension "is a _side module_ which is dynamically loaded by Godot's _main module_ at runtime". It links with `-sSIDE_MODULE=2`, uses `-Z default-visibility=hidden`, and requires `-pthread`/atomics for threaded builds, which must match the template. — [godot-rust: Export to Web](https://godot-rust.github.io/book/toolchain/export-web.html)

### Inferences
- Since `supports_pic` is disabled, Bazel never requests `pic`, so `-fPIC` is never added by the toolchain. Every `cc_library` that ends up in a side module needs to be compiled position-independent, godot-cpp's generated bindings included. Practical routes:
  - (a) The extension rule applies a transition that adds `--copt=-fPIC --copt=-sSIDE_MODULE=1` and the ABI flags. This is what `wasm_cc_binary`'s transition does for its own flags.
  - (b) The ruleset uses its own toolchain config or a fork with a feature that enables PIC/side-module flags.
  - (c) The flags go into `copts`/`linkopts` of every library, which is fragile.

  emsdk's `wasm_cc_binary` produces a main program and has no side-module mode.
- `cc_binary(linkshared = True)` with explicit `linkopts = ["-sSIDE_MODULE=1", ...]` is the closest fit. Explicit `-sSIDE_MODULE` takes precedence over `-shared`. The link wrapper (`link_wrapper.py`) renames outputs according to `--oformat`. The output name will be `lib<name>.so`, and Emscripten accepts `.so` or `.wasm` for side modules. This still needs an experiment, given #1714.
- `cc_shared_library` additionally needs the toolchain to support dynamic linking (`supports_dynamic_linker` is disabled). It is not expected to work with emsdk's toolchain unmodified.
- The ABI flags that must match the engine template are: threads (`-sUSE_PTHREADS=1`/`-pthread`, or not), `-sWASM_BIGINT`, `-sSUPPORT_LONGJMP='wasm'`, wasm32 (`MEMORY64=0`), and the Emscripten version. They map naturally onto platform constraints (decision 1B of the prototype) plus a transition that turns them into features and copts.
- The hard-coded clang include directories (#1580) tie emsdk module versions to Emscripten versions. Pinning an older Emscripten (e.g. 4.0.20) under a newer emsdk module may break `cxx_builtin_include_directories` checks, which needs an experiment. Choosing the emsdk module version whose default Emscripten version matches is the safer pairing.

### Gaps
- No build of a godot-cpp side module with emsdk's Bazel toolchain was attempted. Whether `R_WASM_MEMORY_ADDR_SLEB` errors disappear with `--copt=-fPIC` alone is unverified.
- Whether the side module must be linked with the PIC variant of any system library (e.g. libc++abi) when `SIDE_MODULE=1` was not determined.

## 4. Version pinning per Godot release and who provides the toolchain

### Takeaway
Godot 4.7.2's official web templates were built with **Emscripten 4.0.20**: the template's `godot.js` returns `"4.0.20"` from `godot_js_emscripten_get_version`, and build-containers' `4.7` branch pins it. Godot's CI (`web_builds.yml`) and godot-cpp's CI use 4.0.11, and build-containers' `main` moved to 6.0.12 on 2026-10-09 to fix dlink+pthread builds. So "the Emscripten version of a Godot release" is a release-build fact, not the CI value. The emsdk extension allows only one version per graph, and that limits a ruleset that serves several Godot versions at once.

### Cited Findings
- The Godot 4.7.2-stable web template (`templates/web_dlink_nothreads_release.zip`, `version.txt` = `4.7.2.stable`) contains in `godot.js`: `_godot_js_emscripten_get_version(){const emscriptenVersionPtr=GodotRuntime.allocString("4.0.20");...}`. — Local experiment on `<bazel-output-user-root>/cache/repos/v1/contents/ec460259e0f68a4dad40302f323f3bc1fe0fa68f966108afb37749de5776dc4e/477f9d39-4f54-4c71-9ada-414e1460c3e9/templates/`
- The same archive ships all eight web templates (`web_{,nothreads_,dlink_,dlink_nothreads_}{debug,release}.zip`, about 10–12 MB each). In the dlink nothreads release template, `godot.wasm` is 1.5 MB and `godot.side.wasm` is 44 MB. — Local experiment, same path
- build-containers branch `4.7`, `Dockerfile.web`: `ENV EMSCRIPTEN_VERSION=4.0.20`. Its README says "Web: Emscripten 4.0.20". The commit "Update various toolchains for 4.6 … Emscripten 4.0.20" is dated 2025-11-22. — [godotengine/build-containers@4.7 Dockerfile.web](https://github.com/godotengine/build-containers/blob/4.7/Dockerfile.web); [README@4.7](https://github.com/godotengine/build-containers/blob/4.7/README.md)
- build-containers `main`: `ENV EMSCRIPTEN_VERSION=6.0.12`. The commit of 2026-10-09 is "Web: Update to emscripten 6.0.12 (#169) — Previous versions produced invalid dlink+pthread builds due to an upstream bug." An earlier commit of 2026-08-18 is "Update Emscripten to 6.0.1 (#168)". — [build-containers main Dockerfile.web](https://github.com/godotengine/build-containers/blob/main/Dockerfile.web); [commit history](https://github.com/godotengine/build-containers/commits/main/Dockerfile.web)
- Godot 4.7.2 `web_builds.yml`: `EM_VERSION: 4.0.11`. The matrix builds `threads=yes arch=wasm64` and `threads=no arch=wasm32` release templates. `detect.py` requires Emscripten ≥ 4.0.0, and `lto=thin` needs ≥ 4.0.9. — Local source `.../54778939-c1da-48e8-9545-4f94becb5969/.github/workflows/web_builds.yml`, `platform/web/detect.py`
- godot-cpp CI (`ci-scons.yml`, `ci-cmake.yml`) also uses `EM_VERSION: 4.0.11`. — Local source `.../+godot_cpp_bindings+godot_cpp/.github/workflows/`
- emsdk's `emscripten_deps` fails when more than one module sets `config(version)`. — [emsdk 7.0.0 emscripten_deps.bzl](https://github.com/emscripten-core/emsdk/blob/7.0.0/bazel/emscripten_deps.bzl)
- rules_go: "with SDKs registered in the root module taking precedence over those registered in dependencies". Multiple SDKs can be registered, selected per target, and downloaded lazily. — [rules_go docs/go/core/bzlmod.md](https://github.com/bazel-contrib/rules_go/blob/master/docs/go/core/bzlmod.md)
- Bazel's toolchain priority is: `--extra_toolchains` (last wins), then the root module's `register_toolchains`, then WORKSPACE, then non-root modules. — [Bazel: Toolchains](https://bazel.build/extending/toolchains)
- rules_godot's Android approach: the ruleset's own `godot_android_toolchains` extension creates SDK/NDK repositories pinned by version and integrity, with explicit `exec_compatible_with`. They are registered with `--extra_toolchains` priority because rules_android and rules_android_ndk's toolchains "carry no execution constraints and resolve this host's tools". — Local source `<repo>/rules_godot/godot/platforms/private/android_toolchains.bzl`

### Inferences
- A profile per Godot release could record the Emscripten version of its official templates, e.g. `4.7.x → 4.0.20`. Release builds after 2026-10-09 on build-containers `main` would use 6.0.12. The version is recoverable from any template's `godot.js` (`godot_js_emscripten_get_version`), which also gives `check_engine` a web counterpart: compare the extension toolchain's version with the runtime's.
- Options for who provides the toolchain:
  - **(A) Consumer registers emsdk.** The consumer sets the single `emscripten_deps.config(version)` and the ruleset only validates the match, failing or warning when the version differs from the engine's. This mirrors rules_go's root-precedence model and keeps rules_godot out of the singleton conflict. It cannot serve two Godot versions with different Emscripten versions in one graph.
  - **(B) Ruleset provides its own Emscripten repositories and toolchains per Godot profile.** For each profile it downloads the matching `wasm-binaries` archive, using the same GCS URLs and hashes as emsdk's `revisions.bzl`. It registers toolchains with `target_settings` or a constraint per engine version, like the Android hub. This allows several engine versions side by side, but means maintaining a cc toolchain config or reusing emsdk's `create_toolchains` (whose labels refer to `@emscripten_cache` and `@emsdk`), plus ~300 MB per version and host.
  - **(C) The ruleset depends on emsdk and sets the version.** This conflicts with any consumer who also sets it, and is not advisable for a BCR module.
- Because templates for one Godot minor (4.7) are built with one Emscripten version, while main moved to 6.0.12 for dlink+pthread correctness, threaded dlink support may in practice require Godot ≥ the first release built with 6.0.12.

### Gaps
- Godot does not document an official rule that GDExtension side modules must use exactly the engine's Emscripten version. The 4.7 docs page on compiling for the web does not state it. The requirement follows from Emscripten's dynamic-linking ABI (system libraries are only in the main module) and from community guidance, not from a Godot policy statement. — [Godot 4.7 docs: Compiling for the Web](https://docs.godotengine.org/en/4.7/engine_details/development/compiling/compiling_for_web.html)
- Which Emscripten version Godot 4.8 or later releases use was not checked against actual templates.
- A forum thread says official templates lack GDExtension support. The 4.7.2 template archive does contain `web_dlink_*` templates. The forum claim likely refers to the default (non-dlink) template selection. — [Godot forum](https://forum.godotengine.org/t/how-to-build-a-gdextension-c-library-for-web/129067)

## 5. Skipping unsupported native targets on a new platform

### Takeaway
Bazel skips a target in wildcard builds only when it is incompatible, either directly through `target_compatible_with` or transitively through an incompatible dependency. A missing mandatory toolchain is an analysis **error**. A pattern verified locally on Bazel 9.3.0 avoids touching every add-on: register a **fallback toolchain for `@bazel_tools//tools/cpp:toolchain_type` with `target_compatible_with = ["@platforms//os:emscripten"]` whose `toolchain` target is `@platforms//:incompatible`**. Every `cc_library`/`cc_binary` for the web, and everything depending on them, is then skipped. A real Emscripten toolchain registered with higher priority takes over automatically.

### Cited Findings
- `target_compatible_with`:
  - "Incompatibility is transitive."
  - `select()` with `@platforms//:incompatible` expresses OR and NOT logic.
  - "Incompatible targets are skipped when they appear in a target pattern expansion, such as `//...`".
  - Explicitly requested incompatible targets fail unless `--skip_incompatible_explicit_targets` is set.

  — [Bazel: Platforms, skipping incompatible targets](https://bazel.build/extending/platforms)
- Mandatory toolchains: if no toolchain resolves, "this is an error and analysis halts". `config_common.toolchain_type(..., mandatory = False)` makes a type optional, and the rule then gets `None`. `target_settings` on `toolchain()` filter by configuration. — [Bazel: Toolchains](https://bazel.build/extending/toolchains)
- Bazel's integration tests `test_incompatible_with_missing_toolchain` (regression for bazel#12897) and `test_skipping_with_missing_toolchain` show that a **directly** incompatible target does not fail on a missing toolchain. Toolchain resolution is skipped for it. — [bazel src/test/shell/integration/target_compatible_with_test.sh](https://github.com/bazelbuild/bazel/blob/master/src/test/shell/integration/target_compatible_with_test.sh)
- Local experiment 1 (Bazel 9.3.0):
  - Setup:
    - A custom `toolchain_type` `tt`.
    - Its toolchain implementation `tc(name = "stub", target_compatible_with = [":never_set"])`, registered via `register_toolchains("//pkg:stub_toolchain")`.
    - A rule `r` with `toolchains = ["//pkg:tt"]`.
    - A `genrule` depending on that rule.
  - `bazel build //pkg/...` printed "Target //pkg:downstream was skipped", "Target //pkg:user was skipped" and "Target //pkg:stub was skipped", and the unrelated genrule was built. The build succeeded.
  - An incompatible resolved toolchain makes its users, and their dependents, incompatible.

  — Local experiment (scratchpad `emtc_exp`)
- Local experiment 2 (Bazel 9.3.0, rules_cc 0.2.16, platforms 1.0.0):
  - Setup:
    - Platform `web` = `@platforms//os:emscripten` + `@platforms//cpu:wasm32`.
    - `filegroup(name = "unsupported", target_compatible_with = ["@platforms//:incompatible"])`.
    - `toolchain(name = "web_cc_unsupported", target_compatible_with = ["@platforms//os:emscripten"], toolchain = ":unsupported", toolchain_type = "@bazel_tools//tools/cpp:toolchain_type")`, registered in MODULE.bazel.
    - A `cc_library`, a `cc_binary(linkshared = True)`, a genrule consuming it, and a plain genrule.
  - With `--platforms=//cc:web //cc/...`, `lib`, `ext` and `pkg` were skipped, the plain genrule was built, and the build succeeded.
  - Without the fallback registration, the same command failed: "While resolving toolchains for target //cc:lib: No matching toolchains found for types: … Analysis of target '//cc:lib' failed".

  — Local experiment (scratchpad `emtc_exp2`)
- Mature rulesets use `target_compatible_with` on specific targets to skip unsupported platforms. For example, rules_rust #1391 "Use `target_compatible_with` to make `macos` with `Xcode` happy". — [rules_rust commit d77b9f7](https://pigweed.googlesource.com/third_party/github/bazelbuild/rules_rust/+/d77b9f7c6a5be0eae1bb6eb9347bfce44137195e)
- Bazel discussion #19200 proposes making incompatibility propagation more visible and configurable. — [bazel discussions #19200](https://github.com/bazelbuild/bazel/discussions/19200)
- emsdk's README asks for `--incompatible_enable_cc_toolchain_resolution`. Issue #984/PR #1036 moved emsdk to platform-based toolchain resolution. With Bazel 7+, C++ toolchain resolution through platforms is the default. — [emsdk bazel/README.md](https://github.com/emscripten-core/emsdk/blob/main/bazel/README.md); [emsdk #984](https://github.com/emscripten-core/emsdk/issues/984)

### Inferences
- For rules_godot, the fallback-toolchain pattern means native add-ons, `godot_cc_extension`, sqlite, app_auth, platform_paths and the generated godot-cpp libraries are skipped on `web_wasm32` without each add-on declaring `target_compatible_with`. Once a consumer registers emsdk, the same targets build. Ordering:
  - Bazel picks the first matching registration.
  - The root module's registrations come before non-root modules, and `--extra_toolchains` comes first of all.
  - A consumer's `bazel_dep(emsdk)` toolchains are non-root registrations, as are rules_godot's.
  - So the relative order of emsdk's and rules_godot's fallback depends on the dependency order among non-root modules. This needs a test. Alternatively, the fallback can carry a `target_settings` that is false when a web C++ toolchain is opted in, or be registered only through a consumer-facing config.
- The same trick works for rules_dart's toolchain type: an incompatible fallback for `os:emscripten`. The 8 failing Dart targets would then be skipped instead of failing.
- A `godot_application` for web that depends, through a pack, on a skipped extension would itself be skipped, because incompatibility is transitive. This is correct for "extension not buildable for web". It hides the reason, though: the user sees "skipped" rather than "no Emscripten toolchain". A dedicated diagnostic, such as an analysis-time note when the application is explicitly requested, may be worth adding.
- For tests, the prototype's decision 3A ("web tests are incompatible") can use the same mechanism on `default_test_toolchain_type` or on `godot_test`'s own exec-platform mapping.

### Gaps
- No experiment covered the precedence between the fallback and emsdk's registered toolchain when both come from non-root modules.
- Whether `--skip_incompatible_explicit_targets` is advisable for consumers was not evaluated.

## 6. Building the Godot engine for the web from source

### Takeaway
Godot's web build uses SCons with `platform=web` and `emcc`/`em++`/`emar` as the POSIX toolchain. Its options include `threads`, `dlink_enabled`, `javascript_eval`, `wasm_simd`, `lto=thin`, `use_closure_compiler`, `initial_memory`, `stack_size` and `proxy_to_pthread`, plus many `-s` settings on both compile and link. The link step involves JS libraries, pre/post JS, optional closure compilation, an engine JS file and a template ZIP. I found no prior art of building Godot for the web with Bazel.

### Cited Findings
- `platform/web/detect.py` (4.7.2):
  - `can_build()` requires `emcc` on PATH, and the minimum Emscripten version is 4.0.0.
  - Arches are `wasm32` and `wasm64`.
  - Defaults: `optimize=size` (`-Os`), `vulkan=False`, `module_raycast_enabled=False` (Embree too heavy), and `builtin_pcre2_with_jit=False`.
  - Options: `initial_memory` (32 MiB), `stack_size` (5120 KiB), `default_pthread_stack_size`, `use_assertions`, sanitizers, `javascript_eval` (true), `dlink_enabled` (false), `use_closure_compiler`, `proxy_to_pthread`, `wasm_simd` (true).
  - `lto=auto` becomes `thin`.
  - Link flags include `-sMAX_WEBGL_VERSION=2`, `-sOFFSCREEN_FRAMEBUFFER=1`, `-sGL_ENABLE_GET_PROC_ADDRESS=0`, `-sSTACK_SIZE`, `-sWASM_BIGINT`, `-sMEMORY64=0/1`, `-sENVIRONMENT=web,worker`, `-sMODULARIZE=1 -sEXPORT_NAME='Godot'`, `-sSUPPORT_LONGJMP='wasm'`, `-sALLOW_MEMORY_GROWTH=1`, `-sINVOKE_RUN=0` and `-sEXIT_RUNTIME=1`.
  - Threads add `-sUSE_PTHREADS=1`, `-sPTHREAD_POOL_SIZE=...` and `-sWASM_MEM_MAX=2048MB`.
  - `dlink_enabled` adds `-sSIDE_MODULE=2` and `-fvisibility=hidden`, and the suffix `.dlink`.
  - The emitter makes every object depend on the compiler version.

  — Local source `.../54778939-c1da-48e8-9545-4f94becb5969/platform/web/detect.py`
- Godot 4.7 docs:
  - Templates come from `scons platform=web target=template_release|template_debug`. `javascript_eval=no` removes JavaScriptBridge (official templates enable it). `threads=no` disables threads. `dlink_enabled=yes` enables GDExtension.
  - Output names follow the pattern `godot.web.template_release.wasm32[.dlink].zip`, renamed to `web_[dlink_]release.zip`.
  - The page gives no build times or sizes.

  — [Godot 4.7 docs: Compiling for the Web](https://docs.godotengine.org/en/4.7/engine_details/development/compiling/compiling_for_web.html)
- With `dlink_enabled`, `platform/web/SCsub` builds the engine as `godot.side.wasm` and a main module with `MAIN_MODULE=1` and `EXPORT_ALL=1`. — Local source `.../platform/web/SCsub`
- Godot's CI web jobs have `timeout-minutes: 60` and use SCons caches. — Local source `.../.github/workflows/web_builds.yml`
- Searches for Bazel-based Godot web builds found only SCons, godot-cpp and godot-rust material. — [search results incl. godot-rust export-web](https://godot-rust.github.io/book/toolchain/export-web.html)

### Inferences
- A source-built web engine in rules_godot's SCons translation needs the same Emscripten toolchain as extensions. It also needs:
  - `-s` settings on compile actions, which rules_cc passes as copts unchanged.
  - JS library, pre-js and post-js inputs on the link action.
  - A multi-output link: `.js`, `.wasm`, plus `.side.wasm` for dlink. emsdk's link wrapper only tars outputs for `cc_binary`.
  - Node for the closure compiler.
  - The engine-file and template-ZIP steps.
- A dlink engine is a `MAIN_MODULE`, which in Emscripten needs PIC system libraries. With emsdk this means a secondary cache (`--pic`, likely `--lto=thin`), with the repository-rule and determinism caveats from section 2.
- Official templates are prebuilt for all eight variants. For a first release, "web is prebuilt-only" (as the prototype states) avoids the hardest part.

### Gaps
- No measurements of build time or output size for a source web build (the prebuilt template sizes are in section 4). Godot's docs do not give them either.
- No Bazel prior art for Godot web builds was found. Absence of evidence comes from searches only.
