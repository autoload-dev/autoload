# Sharing source-built engine work across recipes

A source recipe (`godot_engines.source_build`) compiles each engine source in its own
repository. Since the per-source include closures, a recipe that changes reruns only the
compiles whose inputs changed. Two *different* recipes still share no compile, even when
the work is equivalent. This page records why, which designs could change that, what a
prototype measured, and the recommended path.

Snapshot: 2026-11-24, Bazel 9.3.0, BuildBuddy remote execution
(`--config=buildbuddy --config=android`). The engine under test is the beta recipe
`godot_beta_source_build_android` from `rules_godot/MODULE.bazel`: Godot 4.8-beta1, Android
arm64 `template_release`, 731 engine compiles. Each action count below also includes 56
exec-configuration compiles of tools such as zlib, which every recipe shares already.

## Why two recipes share nothing

A remote or disk cache key covers an action's command line, its environment, and the
path and digest of every input and output. A recipe repository's name is part of three
kinds of paths:

| Path | Example |
|---|---|
| Source and header inputs | `external/+godot_engines+<recipe>/core/object/object.cpp` |
| Generated inputs, and their `-I` directories | `bazel-out/<cfg>/bin/external/+godot_engines+<recipe>/core/version_generated.gen.h` |
| Object outputs | `bazel-out/<cfg>/bin/external/+godot_engines+<recipe>/_objs/<target>/object.o` |

`--experimental_output_paths=strip` removes only the configuration segment, and only
for actions that support path mapping; C++ compiles do not. So the cache treats each
recipe's actions as unrelated work.

The canonical name of a recipe repository is
`<extension module>+godot_engines+<name>`. The module extension chooses only `<name>`. The
prefix is Bazel's:

- `+godot_engines+…` while `rules_godot` is the root module, as for the ruleset's own tests;
- `autoload_rules_godot++godot_engines+…` in every module that depends on it, such as
  `examples/` or a consumer project.

Even identical recipes therefore never share between the ruleset's own module and its
consumers. Consumer modules, however, all share the second prefix, so two consumer
projects whose engine work is equivalent could share through a common remote cache.

A recipe that keeps its name keeps its paths. Changing that recipe's options, modules or
build profile is therefore already incremental. The narrowing changes of
autoload-dev/autoload#81, #82 and #83 serve exactly that case.

## How much is equivalent

`bazel aquery` of temporary variant recipes measured the potential. Each variant is a
copy of the beta recipe with one difference. A comparison script replaced the recipe
repository name in every path. It keyed each compile by its normalized command line and
its normalized input paths. For a generated input it used the content digest, after the
generators had been built.

| Variant of the beta recipe | Engine compiles | Equal on #81 | Equal with #82 and #83 | What still differs |
|---|---:|---:|---:|---|
| Identical copy under another name | 731 | 731 | 731 | nothing |
| Build profile (four 2D classes disabled) | 731 | 427 | 722 | `disabled_classes.gen.h` in 8 registering sources, revision hash |
| Extra module `webp` | 860 | 712 | 712 | 129 new sources, `modules_enabled.gen.h` in 18 sources |
| `disable_physics_2d = "no"` | 777 | 0 | 672 | `-DPHYSICS_2D_DISABLED` in 58 sources, 46 new sources |
| Without the engine-name patch | 731 | 420 | 703 | `version_generated.gen.h` in 28 sources |
| Without the `bazel_probe` custom module | 730 | 0 | 0 | `-I _custom_modules` on every compile |

The last row shows a lever that the earlier changes did not cover. SCons adds every
custom module directory to every compile's include path. So adding or removing a
custom module changes all 730 command lines, even within one recipe. A source needs an
include directory only if some file of its include closure lies below it. If rendering
keeps only those directories, 711 of the 730 compiles stay equal. The 19 that remain are
`modules_enabled.gen.h` and the module registration.

Across platforms, CPUs or build targets, practically nothing is equivalent: the
toolchain, the target flags and `TOOLS_ENABLED`/`DEBUG_ENABLED` differ on every compile.

## Options

| Option | Expected sharing between recipes | Analysis and repository cost | Pins and lock files | Apple and Android | Complexity | Fit with Bazel and Godot |
|---|---|---|---|---|---|---|
| **1. Recipe- and module-independent names.** Name recipe repositories by row, not by tag name. | Only between modules, never within one: two recipes of one row cannot share a name. The extension-module prefix stays. | none | unchanged | unchanged | low | Poor. Names become implicit, and two recipes of one row would collide. |
| **2. Content-addressed recipe repositories.** Name a recipe by the digest of all its inputs. | Only identical recipes (731 of 731). Any edit renames the repository, which **loses today's incremental edits** (for example, 722 of 731 for a profile change). | none | unchanged | unchanged | low | Poor. Net negative. |
| **3. One shared source-tree repository** per archive, patches and custom modules, from which recipes compile. | 0. Object outputs and generated headers stay in the recipe repository, so every key still differs. | Saves one extraction per recipe. | unchanged | unchanged | medium | Neutral. Useful only as part of 5. |
| **4. Generators deduplicated by spec digest** into shared paths. | Generator actions only, which are cheap. Compiles still differ by output path. | small | unchanged | unchanged | medium | Neutral. Useful only as part of 5. |
| **5. Shared tree repository with digest-named targets** (prototyped). Generators, header sets and objects live in a tree repository shared by every recipe of one source, patch list and row. Each target name is a digest of what its action reads, so equivalent work is one target. Recipe repositories keep only links and revision-dependent work. | Everything the content measurement found, plus include-directory pruning: 92 to 100 % of the compiles both engines have, for profile, module, custom-module and option variants. Variants of one row in one module are also built only once per build. | Loading the tree loads every recipe of its row (fetch and configure). Each recipe also writes about 2 MB of `shared.bzl`. Measured analysis with a fresh server: 2.9 s and 19,742 configured targets, against 2.65 s and 19,635. | Unchanged. Rendering only, so no graph or pin changes. | `objc_library` objects move like `cc_library` ones. The Swift module (one action) and Android packaging stay in the recipe. | high | Good. It is Bazel's own answer: equivalent actions are one target. Godot's SCons graph is untouched. |
| **6. Custom compile rule with `cc_common.compile`.** | 0 on its own: outputs still lie below the declaring package. It only matters for 5, to declare many objects with fewer targets. | Lower per-target overhead. | unchanged | Objective-C needs its own path. | high | Low. It reimplements `cc_library`. |
| **7. Path-independent action keys** (path mapping, REAPI normalization, a ccache-like executor cache). | Not reachable. Bazel maps only the configuration segment, REAPI keys contain the paths, and an executor-side compiler cache is not hermetic. | none | unchanged | unchanged | n/a | Poor. |
| **8. Narrow per-source inputs further** (#81, #82, #83, include-directory pruning, the shared build-name file). | Within a recipe: an edit reruns only what it changes. Between recipes: it multiplies the benefit of 5. | small | unchanged | unchanged | low each | Good. |

## Prototype

Branch `claude/engine-shared-tree-prototype` (three commits on top of #82) implements
option 5, plus include-directory pruning for shared objects:

- `godot_engines` groups the `godot_engine_build` declarations of one source label,
  patch list, patch strip and row. For each group it declares a `godot_engine_tree`
  repository, which extracts and patches the source, adds the union of the recipes'
  custom modules, keeps each build profile under `_build_profiles/<sha256>.gdbuild`, and
  applies the build-profile scoping of #82.
- With `GODOT_TREE_REPOSITORY` set, rendering (`tools/engine/shared_objects.py`) writes
  `shared.bzl`:
  - Generators are named by the digest of their specification and of the identity of each
    input. Their outputs lie below `_gen/<digest>/`, with logical outputs for the generator
    code.
  - The build-name file lies below `_build_names/<build_name>/`. Unlike the hash, it
    depends on the build name only.
  - Header sets are named by their files and dependencies.
  - Objects are named by the source plus a digest of rule, source path, options, include
    directories, defines and header sets. Each object keeps only the include directories
    that hold a file of its closure, and adds `_gen/<digest>` variants of them for its
    generated files.
- The tree's BUILD file loads every recipe's `shared.bzl` and declares the union by name
  (`godot/engine/private/shared_objects.bzl`). The recipe's engine library links the
  tree's objects. Only `version_hash.gen.cpp`, which reads the revision hash, compiles in
  the recipe.

The Android engine built remotely in full. Every compile saw only its declared inputs,
including the relocated generated headers. The measurements below built a variant after
`bazel clean`, with the base recipe and the variants of the rows above it in the remote
cache.

| Variant built after the base recipe | main (#82) | Prototype | Prototype with #83 |
|---|---:|---:|---:|
| Identical copy | not measured | **1** remote, 769 hits | not measured |
| Build profile | 704 remote, 64 hits | **10** remote, 760 hits | **10** remote, 760 hits |
| Without the custom module | 704 remote, 63 hits | **19** remote, 750 hits | **20** remote, 749 hits |
| Extra module `webp` | not measured | **148** remote, 751 hits | **149** remote, 750 hits |
| `disable_physics_2d = "no"` | not measured | 777 remote, 39 hits | **106** remote, 710 hits |
| Without the patch (another tree) | not measured | 766 remote, 4 hits | not measured |

The counts are Bazel's process summary, so the remote counts include the link and
revision actions.

- **main:** the 704 remote actions and 27 of the hits make up the variant's 731 engine
  compiles. Those 27 include the version header; a first prototype run, which kept
  them in the recipe, had cached them at the recipe's own path. The other hits are tool
  compiles and generators.
- **`webp`:** 129 of its remote actions compile sources the base engine lacks.
- **`disable_physics_2d`:** 46 of its remote actions compile sources the base engine
  lacks.
- **Base engine:** a full remote build through the tree took 35 s.
- **Analysis with a fresh server:** 2.65 s and 19,635 configured targets on main, against
  2.87 s and 19,742 with the prototype, whose tree loaded six recipes.

What the prototype leaves open:

- **Tree identity.** The tree name hashes the source label string and the patch labels.
  To share across consumer modules, it has to digest the archive's sha256, the patch
  contents and the custom module contents. Starlark has no cryptographic hash, so the
  extension would have to run one through `module_ctx.execute`. Two recipes that name
  different directories for the same custom module would also collide in the union.
- **Fetch coupling.** Building one recipe loads, and therefore configures, every recipe of
  its row. Pinned recipes make this cheap. A module typically has one recipe per row.
- **Interface.** Rendering reads the tree from an environment variable, so `configure.py`
  and every pin stay unchanged. A real implementation would pass it as a rendering
  argument, which also keeps pins.
- **Patches.** A recipe with other patches gets another tree and shares nothing (766
  remote instead of the 28 that differ by content). Patched files as content-addressed
  overlays, like generated files, could close this.
- **Coverage.** Only Android was built. iOS (Objective-C objects in the tree, Swift in the
  recipe), desktop editors and the lock-file workflow were not exercised.

## Recommendation

1. **Narrow first.** This is bounded, and it helps today's same-recipe iteration as much
   as any later sharing. Merge #83, then let rendering keep only the include directories
   a source's closure uses. That turns a custom-module change from 730 recompiles into 19
   on main as well, with no change to repositories or pins.
2. **Share between recipes only with a shared tree repository (option 5),** as its own
   planned change, when several recipes of one row actually coexist: a module's test and
   production engines, A/B engine variants, or consumer projects on one remote cache.
   Build it with content-addressed tree names, a rendering argument instead of the
   environment, and tests for iOS and pinned recipes. Expect 92 to 100 % of the compiles two
   engines have in common to hit the cache, for module, profile, custom-module and
   option variants of one row.
3. **Do not pursue** row- or content-addressed recipe names, a shared tree or shared
   generators alone, a custom compile rule, or path-independent keys. They share nothing,
   or they cost the incremental edits that work today.

## Reproducing the measurements

- Add temporary copies of `godot_beta_source_build_android` to `rules_godot/MODULE.bazel`,
  each with one difference, and `use_repo` their `_android_arm64_template_release`
  repositories. Remove the `engine` attribute, so that no copy joins the beta engine.
- **Potential:** for each recipe, run `bazel aquery --output=jsonproto
  'deps(@<recipe>_android_arm64_template_release//:libgodot_android.so)'`, and build its
  `kind('source_generator|source_revision', @<recipe>//:all)` targets with
  `--remote_download_all`. Then compare the compiles:
  - replace `(...+)+godot_engines+<name>` in every path;
  - key each compile by argv, environment, and the (path, digest) of each input;
  - use the content digest of each generated input.
- **Cache hits:** build one recipe, `bazel clean`, build the next. Read `N remote` and
  `N disk cache hit` from Bazel's process summary.

Keep such recipes out of commits. Changing `tools/engine/configure.py`, even a comment,
stales every pin.
