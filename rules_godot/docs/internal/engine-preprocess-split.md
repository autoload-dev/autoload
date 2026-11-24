# Preprocess/compile split for source-built engines (prototype)

Branch `prototype/engine-preprocess-split` (worktree engine-preprocess-split-821d0f), 3 small commits on main 57f005faf,
not for merge. Rule: `rules_godot/godot/engine/private/preprocessed.bzl` (`godot_preprocessed_object`, ~140 lines);
render switch `_MODE` in `tools/engine/render.py` ("split" = every C/C++ source, "shadow" = sampled twins `<lib>__split`).
Recipe: `@godot_beta_source_build_android_android_arm64_template_release` (731 sources, 170 C), BuildBuddy RBE.

## 1. Toolchain fit
- `cc_library` rejects `.ii` ("source file ... is misplaced here"); rules_cc knows `.i/.ii` only as `--save_temps` outputs.
- A small Starlark rule works: `cc_common.create_compile_variables` + `get_memory_inefficient_command_line` for
  `c++-compile`/`c-compile`; action 1 = same line + `-E` (with includes, `-D`, header closure), action 2 = flags minus
  `-D/-U`, input = `.ii` + toolchain only. CcInfo via `create_linking_context_from_compilation_outputs(alwayslink)`.
- Gotchas found: copts need cc_library's shell tokenization (`cc_helper.tokenize`, mbedtls `-D...=\"x.h\"`);
  include dirs need `order = "preorder"`; `--copt/--cxxopt` are not applied yet (fragment copts); no `.d` files.

## 2. Diagnostics, objects, determinism (56 sampled units: 46 C++, 10 C)
- Upstream flags (`-Wall`, no `-Werror`): 0 warnings from source, 0 from `.ii`.
- Stress (`-Wextra -Wunreachable-code -Wshadow-all -Wcomma -Wextra-semi`): 5607 warning sites identical, split adds
  38 `-Wunreachable-code` (macro-expansion info lost, e.g. ERR_FAIL_* macros), none missing. With `-Werror` and such
  flags a split build can fail where the one-action build passes.
- Objects: code/data/symbols/relocations identical in 56/56 pairs; only DWARF differs (52/56): columns and some lines
  inside macro expansions (`.debug_line`, `DW_AT_call_column`).
- Determinism: two independent remote runs (`bazel clean`, `--noremote_accept_cached`): `.ii` 56/56 and split objects
  56/56 byte-identical. Line markers are execroot-relative (`-no-canonical-prefixes`), but contain the repo name and
  `bazel-out/<config>/bin` paths.

## 3. Size and time (same 56 units, remote, executionWallTime)
| | C++ median | C median | all units |
|---|---|---|---|
| `.ii` size | 3.42 MB | 0.70 MB | 160.6 MB for 56 (≈2.1 GB per recipe) |
| zlib-6 compressed | 0.33 MB | 0.05 MB | 15.4 MB (≈0.2 GB per recipe) |
| preprocess exec | 0.08 s | 0.03 s | 4.4 s |
| compile from source | 0.59 s | 0.06 s | 37.0 s |
| compile from `.ii` | 0.57 s | 0.06 s | 37.7 s |
- Preprocess ≈ 16 % of a compile (median); total exec +19 %.
- Client-observed total time per remote action (queue, input staging, upload) dominates: median 1.9 s preprocess,
  2.3 s compile. Preprocessing is cheap in CPU, not in per-action overhead.

## 4. End to end (Android beta recipe, libgodot_android.so)
| scenario | main | split |
|---|---|---|
| cold full build | 731 compiles | 1462 remote (731+731), 50.7 s, critical path 15.9 s |
| `disable_3d` yes→no after clean, warm cache | 863 compiles, 0 hits (measured in #83 session) | 863 preprocess + **277** compiles, 586 hits, 43.9 s |
| (for comparison #83 static pruning) | | 301 compiles, 562 hits |
| `viewport.h`: edit inside inactive `#ifndef _3D_DISABLED`, same line | 53 compiles + link | 53 preprocess, **0** compiles, no link, 4.2 s |
| `object.h`: comment edit on an existing line | 484 compiles + link | 484 preprocess, **0** compiles, no link, 12.7 s |
| `node.h`: real code edit (control) | 146 compiles | 146 preprocess, 132 compiles (14 units only reach it via the over-approximated closure) |
- Executor CPU for the flip: split 75 s preprocess + 273 s compile = 348 s vs main ≈ 542 s (−36 %).
  Cold build: +81 s preprocess on 445 s compile (+18 %), and twice the remote actions.
- Main numbers for the header edits are the actions whose inputs contain the header (aquery), which all miss by construction.
- Caveat: this recipe compiles without `-O`; with optimization compiles get more expensive and the split pays off more.
- Measurement edits (MODULE.bazel, header edits in the external tree) were reverted; nothing committed.

## 5. Open problems
- Objective-C++/iOS: needs an objc variant (`.mii`, `-x objective-c++-cpp-output`, ARC/objc features, Xcode
  toolchain runs locally); `#import` of SDK frameworks gives very large `.mii`; `-fmodules` would emit module imports and
  re-couple the compile to the SDK. Not prototyped.
- Swift bridging header: compiled by swiftc's clang importer with `-Xcc -D`; not splittable, stays as is.
- Precompiled headers / C++ modules: incompatible with `-E` (everything is expanded); Godot's Android/iOS SCons build
  uses none, Bazel's cc rules support none.
- `-g3` (Godot `dev_build`): `.debug_macro` needs the macros; `-dD` keeps them but puts every `-D` into each `.ii`, so a
  flip recompiles everything again (correctly, since the objects differ).
- Diagnostics: extra macro-sensitive warnings (see 2); debug info columns differ inside macros.
- Every flip still reruns all preprocess actions (cheap CPU, ~1.9 s remote overhead each); `.ii` CAS volume ≈ 0.2 GB
  compressed per distinct configuration; each compile fetches its `.ii`.
- rules_cc internals: `cc_helper.tokenize`, command-line construction, `--copt` handling; must follow rules_cc changes.

## Recommendation: pursue, adjusted
Correct by construction and better than #83 on the flip (277 vs 301 compiles) and on header edits that do not change the
preprocessed text (0 compiles), with identical code. Costs: 2× actions, +18 % CPU and more scheduling on cold builds,
extra warnings under strict flags. Adjust: make it opt-in per recipe (C/C++ on remote-executed platforms first), keep
iOS/objc and `-g3` recipes on one action, and keep #83's poison guard only if both coexist (with the split, #83's pruning
only saves cheap preprocess reruns).

## What a stage-3 evaluation still has to measure
- An optimized recipe (`-O2`/`-O3`, e.g. a release template with `optimize=speed`): compile cost per unit, the
  preprocess share and the flip saving were measured only on an unoptimized recipe.
- The flip on main measured in the same session and setup (wall clock and executor CPU), instead of the #83 numbers.
- Sharing inside the planned shared tree: `.ii` line markers carry the recipe repository and `bazel-out` paths, so
  cross-recipe hits need the shared tree (or path normalization) before they can be measured.
- iOS/ObjC++: a `.mii` variant, local Xcode execution, `#import` sizes and the Swift bridging header.
- Analysis cost: two actions per source double the action graph; analysis time and memory of a full recipe
  (`--profile`, `bazel info used-heap-size-after-gc`) were not measured.
- Remote overhead under load: per-action queue and input staging (~1.9 s) with several recipes building at once,
  CAS growth for `.ii` (~0.2 GB compressed per configuration) and the fetch cost on compile executors.
- `--copt`/`--cxxopt` handling, `.d` files and `-Werror` recipes, which the prototype rule does not cover.

The measurement scripts (execution-log analysis, ELF section diff, warning comparison) lived in the session scratchpad
and are not kept; the method is: `bazel clean`, build with `--execution_log_json_file`, compare spawns by mnemonic
(`CppPreprocess`/`CppCompile`), output digests and `executionWallTime`/`totalTime`.
