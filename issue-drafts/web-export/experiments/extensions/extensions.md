# Web extensions: experiments for "Build and ship extensions for the web" (#201)

Experiments that answer the questions #201 lists under "To establish first", run on
2026-11-28. Every claim below is either measured here or marked as reading or inference.

## Setup

| Item | Value |
| --- | --- |
| Host | MacBook Pro, Apple silicon (arm64), macOS 27.2.1 (26B131) |
| Bazel | 9.3.0 (Bazelisk 1.29.0) |
| Ruleset | prototype commit `3d91f7c5e` (branch `claude/web-builds-prototyp-df2828`), worktree `exp-web-extensions` |
| godot-cpp | the ruleset's pin `507ed9d840c01a3c5b2a39af8bb4000bfac30bf5`, bindings from `extension_api-4-7.json`, `bits = "32"` |
| Engines | `4.7.2.stable.official.ed1daf0bf`, `4.8.beta1.official.4d10419ca` (editors and export templates from the prototype's Bazel output bases, not downloaded again) |
| Emscripten | 4.0.20 and 6.0.12; BCR `emsdk` 7.0.0 |
| Browser | the Google Chrome installed on this Mac, 158.0.8127.37, `--headless=new` (not rules_browsers' chrome-headless-shell) |
| Remote execution | BuildBuddy, `toolchains_buildbuddy` 0.0.4, `UBUNTU24_04_IMAGE`, Linux x86_64 |

Files in this directory:

- `module/`: the Bazel module of the experiments. It sat at `exp/` in the prototype's
  checkout (`local_path_override(path = "../rules_godot")`).
  - `emscripten/`: the own toolchain (Q1, Q2): module extension, SDK repository rule,
    toolchain config, wrapper and config templates.
  - `ext/`: the trivial extension `WebHello` (`hello.cc`), the BCR attempt
    `web_hello_bcr.wasm`, the own-toolchain target `web_hello.wasm` and the two-version
    targets `for_godot_4_7` / `for_godot_4_8` (`versions.bzl`).
  - `sqlite/`: the examples' SQLite extension, unchanged, as a side module.
  - `prebuilt/`: three shapes of a prebuilt extension without a web library (Q5).
- `q5_fallback/`: the module of the fallback-toolchain precedence experiment (Q5).
- `godot_project/`, `godot_project_sqlite/`: the Godot projects exported for the browser.
- `scripts/`: `run_in_chrome.py` (serves an export with or without COOP/COEP and runs it in
  headless Chrome), `export_and_run.sh`, `link_threaded.sh` (Q4), `wasm_info.py` (prints a
  wasm module's custom sections and imports).
- `logs/`: the remote-execution runs.

## Summary

| Question | Answer |
| --- | --- |
| 1. godot-cpp as a side module under Bazel | **Yes.** BCR emsdk works only with three workarounds and produces a tar instead of a `.wasm`. An own `cc_toolchain` config over the same archives (about 340 lines in all) produces a plain side module. It needs no PIC system libraries without threads, builds nothing at fetch time and ran unchanged on BuildBuddy's Linux executors, with byte-identical output. |
| 2. Two Emscripten versions in one build | **Yes, with own repositories and toolchains.** One SDK repository per version and execution platform, toolchains selected by `target_settings` on a version setting. One invocation built 4.0.20 and 6.0.12 side modules. From emsdk only the release table and the SDK's filegroups were reused. |
| 3. Does it load, without cross-origin isolation | **Yes.** The side module loads and works in the official 4.7.2 `web_dlink_nothreads_debug` template served without COOP/COEP (`crossOriginIsolated=false`). The same holds for 4.8 beta1 and for SQLite. The source is right, the documentation is outdated. |
| 4. Threads with extensions on 4.7 | **Works on 4.7.2** with COOP/COEP, including extension calls and `thread_local` on a worker thread. The upstream bug that moved Godot to 6.0.12 was in Emscripten 6.0.1, not 4.0.20. A threaded side module needs one PIC system object, `crtbegin.o`, that the SDK archives lack. |
| 5. Incompatible add-ons | **`toolchain = "@platforms//:incompatible"` fails on Bazel 9.3.0.** A toolchain whose target is a `filegroup` with `target_compatible_with = ["@platforms//:incompatible"]` works. It wins or loses against a real toolchain by module order. A prebuilt add-on like Sentry fails at analysis on the web. A ruleset-provided "unsupported" library in the select default makes it incompatible. |

Cross-checks that change the premises of #201:

- **The Emscripten version did not have to match** in this test. Side modules built with
  4.0.20 loaded and passed in 4.8 beta1 (6.0.12), and the other way round, for the
  trivial extension and for SQLite. The issue's "an extension must be built with the
  Emscripten version of the engine that loads it" is a safe policy, not an observed
  necessity. A version check could warn rather than fail. Not covered: C++ exceptions,
  `std::` types crossing the boundary, or code whose libc++ inline ABI changed between
  versions.
- **The threads ABI must match**, and a mismatch fails only in the browser. The loader
  then waits forever, see Q4.
- **godot-cpp's bindings are 32-bit on the web.** The ruleset's `godot_cpp_bindings`
  generates them for `bits = "64"` by default, so a web build needs 32-bit bindings
  ("Built-in type config: float_32"). godot-cpp also defines `THREADS_ENABLED`
  unconditionally in the ruleset's BUILD template, while upstream defines it only for
  threaded builds. The nothreads side module with `THREADS_ENABLED` still loaded, because
  the template exports libc++'s `std::mutex`. The ruleset should still follow upstream.

---

## 1. Can a godot-cpp extension be built as an Emscripten side module under Bazel?

**Answer.** Yes. BCR emsdk 7.0.0 needs three workarounds and wraps the result in a tar.
An own toolchain config over the same Emscripten archives builds a plain `.wasm` side
module for 4.0.20 and 6.0.12. It needs no PIC system libraries, runs no `embuilder` at
fetch time and ran unchanged on Linux remote executors.

### Attempt A: BCR emsdk 7.0.0, `emscripten_deps.config(version = "4.0.20")`

Target `//ext:web_hello_bcr.wasm`: `cc_binary(linkshared = True)` with
`linkopts = ["-sSIDE_MODULE=1", "-sWASM_BIGINT", "-sSUPPORT_LONGJMP=wasm"]`, deps
`@godot_cpp`, platform `//:web` (`os:emscripten`, `cpu:wasm32`). Each step below fixes the
previous error:

1. Plain `bazel build //ext:web_hello_bcr.wasm --platforms=//:web`. The link fails
   because emsdk's toolchain sets `supports_pic` to false, so nothing is compiled
   position-independent:

   ```text
   wasm-ld: error: bazel-out/darwin_arm64-fastbuild/bin/ext/_objs/web_hello_bcr.wasm/hello.o: relocation R_WASM_MEMORY_ADDR_LEB cannot be used against symbol `guard variable for godot::Object::_gde_engine_class_registration_helper`; recompile with -fPIC
   ```

   This is the error of emsdk #1714. It also occurs with **4.0.20**, not only from
   Emscripten 6, and the same with 6.0.12.
2. With `--copt=-fPIC`, the toolchain's default feature `output_format_js` adds
   `--oformat=js`, and emcc refuses to run its JS compiler for a side module:

   ```text
   AssertionError [ERR_ASSERTION]: JS compiler should only run on side modules if asyncify is used.
   ```

3. With `--features=-output_format_js`, emsdk's `link_wrapper.py` finds no output:
   `em++.py did not appear to output any known files!` It derives the output names from
   `--oformat`.
4. With `--oformat=wasm` in `linkopts`, the build succeeds. The output
   `bazel-bin/ext/web_hello_bcr.wasm` is a **POSIX tar archive** holding
   `web_hello_bcr.wasm`, because the wrapper always tars `cc_binary`'s outputs. The
   extracted module is a valid side module (custom section `dylink.0`).

The same four steps with `emscripten_deps.config(version = "6.0.12")`: step 1 fails the
same way, and step 4 succeeds.

Further observations on emsdk 7.0.0, from reading its code and the command lines:

- `toolchain.bzl` hardcodes `-isystem <sdk>/lib/clang/24/include` and
  `cxx_builtin_include_directories` `lib/clang/21/include`. 4.0.20 ships `lib/clang/22`,
  6.0.12 ships `lib/clang/24`. 4.0.20 compiled anyway, through the sysroot headers. This
  is emsdk #1580's risk.
- `env.sh` uses `pwd -P`, so emcc runs on resolved paths into Bazel's repository contents
  cache (`.../cache/repos/v1/contents/<hash>/...` on its command lines).
- `@emscripten_cache//:emscripten_cache` is an alias to the *host's* archive
  (`get_bin_deps_repo_name(repository_ctx)` from `repository_ctx.os`), and so is the
  config. The Linux toolchain of a Mac host therefore also loads the Mac archive (by
  reading; not run).
- The flags apply to the whole build (`--copt`, `--features`). A ruleset would need a
  transition that sets these command-line options for the extension's closure.

### Attempt B: an own `cc_toolchain` config (works)

`module/emscripten/`:

- `extensions.bzl`: a module extension `emscripten` with a `version` tag. For each
  version and execution platform (Linux x86_64/arm64, macOS arm64/x86_64) it declares an
  `emscripten_sdk` repository: `download_and_extract` of the official
  `wasm-binaries.tar.xz`, pinned by emsdk's `revisions.bzl` hash. A hub
  `@emscripten_toolchains` holds the `toolchain()` declarations.
- `toolchain_config.bzl`: `create_cc_toolchain_config_info` with `supports_pic` and
  `supports_dynamic_linker` on, plus one enabled feature `godot_web_abi`. It compiles
  every object with `-sSIDE_MODULE=1 -sSUPPORT_LONGJMP=wasm -fno-exceptions
  -no-canonical-prefixes`, as godot-cpp's `tools/web.py` does, and links shared libraries
  with `-sSIDE_MODULE=1 -sWASM_BIGINT -sSUPPORT_LONGJMP=wasm`. A feature `use_pthreads`
  adds `-pthread`. Python comes from rules_python's exec toolchain (emsdk's pattern).
- `emcc.sh.tpl`: `emcc.py` / `emar.py` with `EM_CONFIG` in the SDK repository. All paths
  are relative to the execution root. `emscripten_config.tpl` sets
  `CACHE = <sdk>/emscripten/cache`, `FROZEN_CACHE = True`, and a placeholder `NODE_JS`.

```sh
cd exp
bazel build //ext:web_hello.wasm --platforms=//:web
```

The result is `bazel-bin/ext/web_hello.wasm`, a plain side module with sections `dylink.0`
and `target_features`. The link command line:

```text
external/+emscripten+emscripten_4_0_20_macos_arm64/emcc.sh -shared -o bazel-out/.../ext/web_hello.wasm
  .../hello.pic.o .../libgodot_cpp.a -Wl,-S '-sSIDE_MODULE=1' -sWASM_BIGINT '-sSUPPORT_LONGJMP=wasm'
```

Three problems fixed on the way, which a ruleset toolchain has to handle as well:

- Absolute paths: with `ROOT=$(pwd)/...` the include check failed with `absolute path
  inclusion(s) found in rule '@@+godot_cpp_bindings+godot_cpp//:godot_cpp'`. emcc passes
  `--sysroot=` from `config.CACHE` unresolved, so a relative `CACHE` keeps it relative.
  `-no-canonical-prefixes` keeps clang's resource directory relative to the invoked path
  instead of its real path in the repository cache.
- `NODE_JS = ""` fails every compile with `NODE_JS is set to empty value`. Any nonempty
  value works, because side modules never run Node.js. Node.js is therefore not among the
  toolchain's inputs.
- C sources: `gcc` must call `emcc.py`, not `em++.py`, or SQLite's `sqlite3.c` compiles
  as C++ and fails.

No output or `.d` file contains an absolute path (`strings` finds no `/Users`; no `.d`
file contains one).

### PIC system libraries, `embuilder` at fetch time

- The 4.0.20 and 6.0.12 archives contain no `sysroot/lib/wasm32-emscripten/pic/`
  directory. A side module **without threads needs none**: the link searches `-L.../pic`
  but links no system library. libc, libc++ and compiler-rt symbols (`__cxa_atexit`,
  `__dynamic_cast`, `_Znwm`, `__multi3`, `printf`, `realloc`, `std::mutex`) are imports
  that the engine's main module (`MAIN_MODULE`, `EXPORT_ALL`) provides at load time.
- **With `-pthread`, a side module needs `pic/crtbegin.o`** (4.0.20), respectively
  `pic/crtbegin-mt.o` (6.0.12), which the archives lack (see Q4). That is one object,
  compiled from one C file in 0.28 s. It does not need a whole PIC sysroot.
- Nothing is built at fetch time: BCR emsdk runs `embuilder` only when a module sets
  `emscripten_cache.configuration`/`targets` tags. The own toolchain never runs it.

### Remote execution

```sh
bazel build //ext:web_hello.wasm --platforms=//:web --config=buildbuddy --remote_download_toplevel
```

The build resolved
`@@+emscripten+emscripten_4_0_20_linux_x86_64//:cc_toolchain` on
`platform_linux_x86_64`. Result: `82 processes: 16 internal, 66 remote`, `Build completed
successfully` (`logs/rbe_buildbuddy_linux.log`). The output from Linux executors with
the Linux SDK is **byte-identical** to the Mac build with the Mac SDK
(`d07dae7f60b79c0485eb7214074c762f3bcea72a2ece16499c744add86a20998`). A fresh output base
with the same command fetched only the Linux SDK, not the host's, and hit the remote cache
for all 66 actions (`logs/rbe_fresh_output_base.log`).

**Unverified:** RBE with BCR emsdk, and the claim that it loads the host archive too
(reading only). Windows execution platforms. The size of the inputs that the first
remote build uploads: BuildBuddy already held the archive's blobs, the build took 35 s.
Optimized builds: everything here is `fastbuild` (`-O0`); `-c opt` with LTO, which
godot-cpp's `tools/web.py` defaults to (`lto=full`), was not tried.

Sizes: an unpacked SDK takes 1.5 to 1.6 GB per version and host (archives 280 to 355 MB).
The side module is 314 KB (4.0.20) and 304 KB (6.0.12) at `-O0`.

## 2. Two Emscripten versions in one build

**Answer.** Yes. The versions coexist as separate repositories with toolchains selected by
`target_settings` on a version setting. One `bazel build` produced side modules for 4.0.20
and 6.0.12. From emsdk only the release table (`revisions.bzl`) and the SDK's filegroup
template (`emscripten_build_file.bzl`) were reusable. Toolchain config, wrappers, Emscripten
config, cache and registration had to be owned.

Evidence:

- `emscripten.version(version = "4.0.20")` and `emscripten.version(version = "6.0.12")`
  create `emscripten_4_0_20_<exec>` and `emscripten_6_0_12_<exec>`. The hub declares, per
  version and execution platform:

  ```starlark
  toolchain(
      name = "emscripten_6_0_12_macos_arm64",
      exec_compatible_with = ["@platforms//os:macos", "@platforms//cpu:arm64"],
      target_compatible_with = ["@platforms//os:emscripten", "@platforms//cpu:wasm32"],
      target_settings = [":is_6_0_12"],   # config_setting on //emscripten:version
      toolchain = "@emscripten_6_0_12_macos_arm64//:cc_toolchain",
      toolchain_type = "@bazel_tools//tools/cpp:toolchain_type",
  )
  ```

- `ext/versions.bzl`'s `side_module_for` sets `//emscripten:version` through an incoming
  dependency transition, as an engine-bound extension rule would.
  `bazel build //ext:both --platforms=//:web` linked with
  `external/+emscripten+emscripten_4_0_20_macos_arm64/emcc.sh` in `darwin_arm64-fastbuild`
  and `external/+emscripten+emscripten_6_0_12_macos_arm64/emcc.sh` in
  `darwin_arm64-fastbuild-ST-429743899bf6`. The two outputs differ, as expected.
- 6.0.12 warns `WASM_BIGINT is deprecated`. The flag belongs to the version's profile,
  not to the toolchain in general.
- BCR emsdk cannot do this (by reading its 7.0.0 code; not run). `emscripten_deps` fails
  on a second version ("More than one emscripten version specified!"), and its repository names and its
  `@emscripten_cache` are fixed. Its `create_toolchains` macro binds to
  `@emscripten_cache` and `@emsdk//emscripten_toolchain:*`. A `bazel_dep(emsdk)` anywhere
  also registers emsdk's toolchains, which match any `cpu:wasm32` platform.

What a ruleset owns, by this experiment: the SDK repository rule and the hub, 123 lines;
the toolchain config, 127 lines; the SDK's BUILD template, the wrapper and the Emscripten
config, about 70 lines.
The release table can be copied into `profiles.bzl`: four SHA-256 per version, plus the
commit hash that names the archive URL. Copying avoids a dependency on emsdk, whose module
registers toolchains in every consumer's graph. In the ruleset, the selecting setting
would be the engine (`--@autoload_rules_godot//godot:engine`) and its profile, not a flag
of its own.

**Unverified:** the 6.0.12 path on Linux execution (only 4.0.20 ran remotely). Running
both versions remotely in one invocation.

## 3. Does the side module load in the dlink template without cross-origin isolation?

**Answer.** Yes. A nothreads side module loaded and ran in the official 4.7.2
`web_dlink_nothreads_debug` template served **without** COOP/COEP
(`crossOriginIsolated=false`), and with them. The same holds for 4.8 beta1 with 6.0.12
and for the SQLite extension. Godot's documentation is outdated on this point: 4.7.2
requires cross-origin isolation only for threads.

Procedure (`scripts/export_and_run.sh`):

1. The side module from `//ext:for_godot_4_7` goes to `godot_project/bin/`.
   `web_hello.gdextension` selects it with `web.debug.wasm32` (nothreads) and the threaded
   one with `web.debug.threads.wasm32`.
2. Export with the 4.7.2 editor:
   `Godot --headless --path godot_project --export-debug WebNoThreads out/index.html`.
   Preset `variant/extensions_support=true`, `variant/thread_support=false`,
   `custom_template/debug=<templates>/web_dlink_nothreads_debug.zip`. The exporter writes
   `"gdextensionLibs":["web_hello.nothreads.wasm"]` and `GODOT_THREADS_ENABLED = false`
   into the page, and copies the library beside it. `fileSizes` lists only `index.pck`
   and `index.wasm`.
3. `scripts/run_in_chrome.py out` serves the directory with Python's HTTP server, with
   `--isolation` adding COOP `same-origin` and COEP `require-corp`. Headless Chrome opens
   the page, and the script reads its console from Chrome's stderr log. `main.gd` prints
   feature tags, `crossOriginIsolated`, calls the extension and quits.

Console without COOP/COEP (4.7.2):

```text
Build configuration: Emscripten 4.0.20, single-threaded, GDExtension support.
WEBHELLO features: web=true web_extensions=true threads=false nothreads=true
WEBHELLO crossOriginIsolated=false
WEBHELLO add(40, 2)=42
WEBHELLO Hello from wasm, Godot (sizeof(void*)=4)
WEBHELLO main thread bump()=[1, 2]
WEBHELLO RESULT=PASS
```

| Engine / side module | Template | Headers | Result |
| --- | --- | --- | --- |
| 4.7.2 / 4.0.20 | `web_dlink_nothreads_debug` | none | PASS, `crossOriginIsolated=false` |
| 4.7.2 / 4.0.20 | `web_dlink_nothreads_debug` | COOP/COEP | PASS |
| 4.8 beta1 / 6.0.12 | `web_dlink_nothreads_debug` | none | PASS, `Emscripten 6.0.12, single-threaded, GDExtension support` |
| 4.8 beta1 / 6.0.12 | `web_dlink_nothreads_debug` | COOP/COEP | PASS |
| 4.7.2 / SQLite, 4.0.20 | `web_dlink_nothreads_debug` | none | PASS: table created, two rows, `sqlite_version()` 3.54.1 |
| 4.8 beta1 / SQLite, 6.0.12 | `web_dlink_nothreads_debug` | none | PASS |
| 4.7.2 / module built with 6.0.12 | `web_dlink_nothreads_debug` | none | PASS (cross-version) |
| 4.8 beta1 / module built with 4.0.20 | `web_dlink_nothreads_debug` | none | PASS (cross-version) |
| 4.7.2 / SQLite built with 6.0.12 | `web_dlink_nothreads_debug` | none | PASS (cross-version) |
| 4.8 beta1 / SQLite built with 4.0.20 | `web_dlink_nothreads_debug` | none | PASS (cross-version) |

Every passing page also logs `TypeError: Failed to construct 'AudioWorkletNode'` after
`quit()`, an audio start after the main loop ended. It has nothing to do with the
extension.

**Unverified:** release templates (only `*_debug` exports). Browsers other than Chrome:
Safari and Firefox are untested. `rules_browsers`' pinned chrome-headless-shell was not
used. Extensions that use C++ exceptions, or that call JavaScript (`EM_JS`, JS
libraries). The ruleset's own packaging: Godot's editor did the export here, not
`godot_web_application`.

## 4. Threads with extensions on 4.7

**Answer.** It works on 4.7.2. A `-pthread` side module in the official 4.7.2
`web_dlink_debug` template, served with COOP/COEP, loaded and was called from the main
thread and from a GDScript `Thread`, with `thread_local` state kept per thread. The
combination does not have to start with 4.8. The bug behind Godot's move to Emscripten
6.0.12 was in 6.0.1, the version 4.8's development builds had used.

Evidence:

- Building with `--features=use_pthreads` fails in Bazel at link time:

  ```text
  Exception: FROZEN_CACHE is set, but cache file is missing: "sysroot/lib/wasm32-emscripten/pic/crtbegin.o" (in cache root path "external/+emscripten+emscripten_4_0_20_macos_arm64/emscripten/cache")
  ```

  BCR emsdk fails the same way: `missing: "sysroot/lib/wasm32-emscripten/pic/crtbegin.o"`
  (its cache root is an absolute repository-cache path). 6.0.12 needs
  `pic/crtbegin-mt.o`.
- `scripts/link_threaded.sh` linked the Bazel-compiled `-pthread` objects outside Bazel,
  against a writable copy of the SDK cache. Emscripten generated exactly one file,
  `cache/sysroot/lib/wasm32-emscripten/pic/crtbegin.o` (`crtbegin-mt.o` for 6.0.12), and
  warned `dynamic linking + pthreads is experimental`. **This link step is not
  hermetic.** In the ruleset, that object would be a build action or a shipped file.
- Results (`main.gd` starts a `Thread` that calls `bump()` twice and `add(1, 2)`):

| Engine / side module | Template | Headers | Result |
| --- | --- | --- | --- |
| 4.7.2 / 4.0.20 `-pthread` | `web_dlink_debug` | COOP/COEP | PASS: `Emscripten 4.0.20, multi-threaded, GDExtension support`; `worker thread bump()=[1, 2] add=3` |
| 4.8 beta1 / 6.0.12 `-pthread` | `web_dlink_debug` | COOP/COEP | PASS, same output |
| either | `web_dlink_debug` | none | Godot does not start: "The following features required to run Godot projects on the Web are missing: Cross-Origin Isolation … SharedArrayBuffer …" |

- Negative controls for the ABI. Without them, a mismatch would only surface in the
  browser, and the page then hangs:
  - Threaded module in the nothreads template: `LinkError: WebAssembly.instantiate():
    Import #0 "env" "memory": mismatch in shared state of memory, declared = 1, imported =
    0`, then `still waiting on run dependencies: dependency: loadDylibs` forever.
  - Nothreads module in the threaded template: the same with `declared = 0, imported = 1`.
- Upstream: build-containers PR #169 "Web: Update to emscripten 6.0.12" says "Previous
  versions produced invalid dlink+pthread builds due to an upstream bug" and links
  emscripten #27852. That issue reads "Since updating Godot build system to use
  emscripten `6.0.1`…" (`_emscripten_glGetVertexAttribIuiv is undefined` with
  `-sMAIN_MODULE=1 … -pthread`). The 4.7 branch stayed on 4.0.20, and its official
  `web_dlink_debug` template works.

**Unverified:** heavier threaded workloads (`WorkerThreadPool`, many threads, extension
code that starts its own pthreads). The upstream bug affected the engine's main module,
so a source-built 4.7 engine was not in scope. The threaded side module was linked
outside Bazel.

## 5. Incompatible add-ons

**Answer.** The research's fallback, a toolchain whose `toolchain` is
`@platforms//:incompatible`, **fails on Bazel 9.3.0**. What works is a toolchain whose
target is itself incompatible, a `filegroup` with
`target_compatible_with = ["@platforms//:incompatible"]`. It then skips cc targets and
everything depending on them. Its precedence against a real toolchain from another module
follows module order: whichever registers first wins, so the fallback can shadow a real
toolchain. A prebuilt add-on like Sentry has no cc target and fails at analysis on the
web. The ruleset can make it incompatible with a ruleset-provided "unsupported" library
target in the `select` default.

### The fallback toolchain (`q5_fallback/`)

Module `q5` with `cc_library(:native)`, `cc_binary(:native_shared, linkshared)`, a
`genrule(:consumer)` on it and a `genrule(:script_only)`. Module `web_cc_fallback`
registers the fallback. Platform `os:emscripten` + `cpu:wasm32`.

| Setup | `bazel build //... --platforms=//:web --nobuild` |
| --- | --- |
| no fallback, no Emscripten toolchain | `No matching toolchains found for types: @@bazel_tools//tools/cpp:toolchain_type` |
| fallback A: `toolchain = "@platforms//:incompatible"` | `toolchain type @@bazel_tools//tools/cpp:toolchain_type resolved to target @@platforms//:incompatible, but that target does not provide ToolchainInfo` |
| fallback B: `toolchain = ":no_web_cc"`, a filegroup with `target_compatible_with = ["@platforms//:incompatible"]` | Build completed successfully; `:native`, `:native_shared`, `:consumer` skipped, `:script_only` built |

An explicit request with fallback B fails with the reason, as #88 decides:

```text
ERROR: Target //:consumer is incompatible and cannot be built, but was explicitly requested.
Dependency chain:
    //:consumer (73de67)
    //:native_shared (73de67)
    //:native (73de67)
    @@web_cc_fallback+//:no_web_cc (73de67)   <-- target platform (//:web) didn't satisfy constraint @@platforms//:incompatible
```

The last target's name appears in the message, so a ruleset should name it for the reader,
for example `no_web_cc_toolchain_for_this_engine`.

Precedence against BCR emsdk, a real Emscripten toolchain registered by another module
(`bazel cquery //:native` with `--toolchain_resolution_debug`):

| Root module's `bazel_dep` order | Selected | `//:native` on the web |
| --- | --- | --- |
| `web_cc_fallback` | `@@web_cc_fallback+//:no_web_cc` | incompatible |
| `emsdk`, then `web_cc_fallback` | `@@emsdk+//emscripten_toolchain:cc-compiler-wasm-emscripten_mac_arm64` | compatible |
| `web_cc_fallback`, then `emsdk` | `@@web_cc_fallback+//:no_web_cc` | incompatible: the real toolchain is shadowed |

Toolchains of non-root modules are ordered breadth-first by `bazel_dep` order, so which
of the two wins depends on the consumer's MODULE.bazel. In a design where the ruleset
provides the Emscripten toolchains itself, it registers its real toolchains before the
fallback in its own `register_toolchains`. The fallback then catches only what the
ruleset has no toolchain for: an engine without a pinned Emscripten version, an
execution platform without an SDK. A consumer's own toolchain wins only from the root
module or with `--extra_toolchains`. Whether consumers may substitute their own toolchain
is a design question. If yes, a `target_settings` opt-out on the fallback would be
needed; that was not tried.

### A prebuilt extension without a web library (`module/prebuilt/`)

`addons/sentry` on `main`: `godot_extension(library = select({os:android, os:ios,
os:linux, os:macos}, no_match_error = "Sentry for Godot is wired for Android, iOS, Linux
and macOS"))` over filegroups, `cc_import`s and Apple imports. No target in it needs a C++
toolchain on the web, so the fallback toolchain does not apply. Three shapes of the same
vendor extension, each under a `godot_addon`, with the prototype ruleset and
`--platforms=@autoload_rules_godot//godot/platforms:web_wasm32`:

| Library `select` on the web | `bazel build //prebuilt:addon_<shape> --nobuild` | In `//prebuilt/...` |
| --- | --- | --- |
| no branch (Sentry's shape) | `configurable attribute "library" in //prebuilt:vendor_no_match doesn't match this configuration` | fails the wildcard |
| `"//conditions:default": None` (the ruleset's current meaning: no library for that platform) | builds; the add-on is compatible and its application gets no library | built: dropped without a word, fails at runtime |
| `"//conditions:default": ":unsupported"`, a filegroup with `target_compatible_with = ["@platforms//:incompatible"]` | `Target //prebuilt:addon_sentinel is incompatible and cannot be built, but was explicitly requested.` with chain `addon_sentinel → vendor_sentinel → unsupported` | skipped |

What the rules need to derive, from this experiment:

- A rule cannot declare itself incompatible from its implementation. Incompatibility
  comes only from `target_compatible_with` or from an incompatible dependency. A
  `godot_extension` macro cannot read a `select`'s keys either. So the
  ruleset cannot derive "no web library" from the existing `library` select. It has two
  options:
  1. **A ruleset-provided sentinel**, such as `@autoload_rules_godot//godot/extension:unsupported`
     (proved above). Add-ons put it in the `select` default instead of `no_match_error` or
     `None`. Every pack and application above becomes incompatible on the platforms
     without a library. This needs no rule change, only a convention, and Sentry would
     replace its `no_match_error`.
  2. **A declared library per operating system**, for example a dict from operating
     system to library. The macro derives both the `select` and `target_compatible_with`
     from its keys, and a missing `web` key is incompatible by construction. This is not
     tried; it changes the public API.
- The ruleset's current `None` semantics, an extension without a library for an
  application's operating system ships nothing (fixture
  `extensions_without_matching_libraries`), contradict #88's "incompatible, not
  failing" for the web. They also cover silent drops on Android and iOS today. Whether
  `None` stays "drop" or becomes "incompatible" is a decision for all platforms, not only
  the web.
- The sentinel's dependency runs in the extension's configuration after
  `reset_transition` (`//prebuilt:unsupported (6e5bb1)` versus `b4478b` above), and the
  skip still propagated to the add-on. The tool views that the editor loads are built for
  the execution platform and stay compatible. The complete chain up to `godot_pack` and
  `godot_app` was not built: no web application target was declared here.

**Unverified:** rules_dart's toolchain with the same filegroup fallback (the research
claims it; not rerun). `aspect` wildcards in the real `examples/` with a fallback
registered. Bazel 10.

## Not run, and why

- `rules_browsers`' chrome-headless-shell: the installed Chrome 158 sufficed for the
  questions. #88 decides that the ruleset pins its browser.
- Release templates, `-c opt`/LTO builds, Windows execution: outside the questions, and
  each adds a full matrix.
- A hermetic PIC `crtbegin.o` for threads: the threaded link ran outside Bazel. The two
  options are an `embuilder`-free build action that compiles `crtbegin.c` from the SDK,
  and an object shipped with the ruleset's profile. Neither is built.
- The ruleset's own web packaging of extensions (`gdextensionLibs`, descriptor `web.wasm32`
  entries, choosing the dlink template): Godot's editor did the export. Prototype
  decision 1 (option D) and decision 7 cover that work.
