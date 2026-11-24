# Sharing source-built engine work across recipes

A source recipe (`godot_engines.source_build`) compiles each engine source in its own
repository. A recipe that changes reruns only the compiles whose inputs changed
([cache behavior](../public/engine.md#cache-behavior-and-limits)). Two *different*
recipes still share no compile, even when the work is equivalent. This page records why,
which designs could change that, what a prototype measured, and the conclusions.

Snapshot: 2026-11-24, Bazel 9.3.0, BuildBuddy remote execution
(`--config=buildbuddy --config=android`). The engine under test is the beta recipe
`godot_beta_source_build_android` from `rules_godot/MODULE.bazel`: Godot 4.8-beta1, Android
arm64 `template_release`, 731 engine compiles. Engine compile counts leave out 56
exec-configuration compiles of tools such as zlib, which every recipe shares already;
Bazel's process summaries include them.

Changes that narrow each compile's inputs, as the tables below name them:

- the per-source include closures (autoload-dev/autoload#81, merged);
- the scoped build profile (#82, merged);
- the per-source feature macros (#83): a scan for `*_ENABLED` and `*_DISABLED` names,
  measured here but set aside for a compiler-based define analysis;
- include-directory pruning (#85, merged after the snapshot).

## Why two recipes share nothing

A remote or disk cache key covers an action's command line, its environment, and the
path and digest of every input and output. A recipe repository's name is part of three
kinds of paths:

| Path | Example |
|---|---|
| Source and header inputs | `external/+godot_engines+<recipe>/core/object/object.cpp` |
| Generated inputs, and their `-I` directories | `bazel-out/<cfg>/bin/external/+godot_engines+<recipe>/core/version_generated.gen.h` |
| Object outputs | `bazel-out/<cfg>/bin/external/+godot_engines+<recipe>/_objs/<target>/object.o` |

Path mapping (`--experimental_output_paths=strip`) removes at most the configuration
segment, never the repository name. The cache treats each recipe's actions as unrelated
work.

The canonical name of a recipe repository is `<extension module>+godot_engines+<name>`,
and the module extension chooses only `<name>`. The prefix is `+godot_engines+` while
`rules_godot` is the root module, as for its own tests. In every module that depends on it,
such as `examples/` or a consumer project, the prefix is `autoload_rules_godot++godot_engines+`.
Identical recipes therefore never share between the ruleset's own module and its
consumers. Consumer modules, however, all have the same prefix, so two consumer projects
whose engine work is equivalent could share through a common remote cache.

A recipe that keeps its name keeps its paths, so changing its options, modules or build
profile is already incremental. The narrowing changes serve exactly that case.

## How much is equivalent

`bazel aquery` of temporary variant recipes measured the potential. Each variant is a
copy of the beta recipe with one difference. A comparison script replaced the recipe
repository name in every path. It keyed each compile by its normalized command line and
its normalized input paths. For a generated input it used the content digest, after the
generators had been built.

| Variant of the beta recipe | Engine compiles | Equal with include closures | Also with scoped profile and feature macros | What still differs |
|---|---:|---:|---:|---|
| Identical copy under another name | 731 | 731 | 731 | nothing |
| Build profile (four 2D classes disabled) | 731 | 427 | 722 | `disabled_classes.gen.h` in 8 registering sources, revision hash |
| Extra module `webp` | 860 | 712 | 712 | 129 new sources, `modules_enabled.gen.h` in 18 sources |
| `disable_physics_2d = "no"` | 777 | 0 | 672 | `-DPHYSICS_2D_DISABLED` in 58 sources, 46 new sources |
| Without the engine-name patch | 731 | 420 | 703 | `version_generated.gen.h` in 28 sources |
| Without the `bazel_probe` custom module | 730 | 0 | 0 | `-I _custom_modules` on every compile |

The last row shows a lever that the narrowing changes do not cover. SCons adds the
custom module directory to every compile's include path, so adding or removing a custom
module changes all 730 command lines, even within one recipe. A source needs an include
directory only if some file of its include closure lies below it. If rendering keeps only
those directories, the prototype below reruns only about 19 actions: the sources that
include `modules_enabled.gen.h`, the module registration, and the link.

Across platforms or CPUs, practically nothing is equivalent: the toolchain and the
target flags differ on every compile. Across build targets of one recipe, a part is. The
same comparison, with the feature macros and include-directory pruning applied, gave:

| Build targets compared | Engine compiles | Equal | What differs |
|---|---:|---:|---|
| Android `template_release` and `template_debug` (beta recipe) | 731 | 188 | `-DDEBUG_ENABLED` in 542 sources |
| macOS `template_release` and `template_debug` (4.7.3 snapshot, Compatibility renderer) | 1045 | 286 | `-DDEBUG_ENABLED` |
| macOS `template_debug` and `editor` (same recipe) | 1045 and 1456 | 0 | `-DNO_EDITOR_SPLASH` and `-DGDSCRIPT_NO_LSP` on every compile, `-DTOOLS_ENABLED` in 749 sources, 411 editor-only sources |

The equal compiles are mostly third-party code and Godot sources whose closure never
reads `DEBUG_ENABLED`. `TOOLS_ENABLED` and `DEBUG_ENABLED` change core headers, so the
rest is genuinely different work. Between editor and templates, `NO_EDITOR_SPLASH` and
`GDSCRIPT_NO_LSP` alone hide the 296 compiles that do not reach `TOOLS_ENABLED`.
Both are Godot feature macros that the name-based scan of #83 misses, because their names
do not end in `_ENABLED` or `_DISABLED`; an analysis that asks the compiler which macros a
source reads sees them. Sharing across build targets also needs a shared tree that spans a
recipe's build targets: the prototype groups by row.

A Godot upgrade within one recipe keeps every path, so the cache reuses whatever kept its
content and closure. Switching `godot_source_build_android` from 4.7.2-stable to the 4.7.3
snapshot (87 upstream commits, 120 files) on current `main` (closures, scoped profile and
include-directory pruning, no feature macros) gave, after `bazel clean`:

| Recipe change | Engine compiles | Hits | Remote | Why the remote ones reran |
|---|---:|---:|---:|---|
| Godot 4.7.2-stable to the 4.7.3 snapshot | 682 | 105 | 577 | 23 changed sources, 553 changed included headers, 1 changed version header |

The hits are 93 third-party sources and 12 Godot sources. Two core headers that almost
every Godot source includes changed: `core/templates/hashfuncs.h` (one added
specialization, in 551 closures) and `core/templates/safe_refcount.h` (`constexpr`
constructors, in 549). A patch release that touches such a header recompiles nearly all
of Godot; per-source narrowing cannot avoid that, because the header is really read.

## Options

| Option | Expected sharing between recipes | Analysis and repository cost | Pins and lock files | Apple and Android | Complexity | Fit with Bazel and Godot |
|---|---|---|---|---|---|---|
| **1. Recipe- and module-independent names.** Name recipe repositories by row, not by tag name. | Only between modules, never within one: two recipes of one row cannot share a name. The extension-module prefix stays. | none | unchanged | unchanged | low | Poor. Names become implicit, and two recipes of one row would collide. |
| **2. Content-addressed recipe repositories.** Name a recipe by the digest of all its inputs. | Only identical recipes (731 of 731). Any edit renames the repository, which **loses today's incremental edits** (for example, 722 of 731 for a profile change). | none | unchanged | unchanged | low | Poor. Net negative. |
| **3. One shared source-tree repository** per archive, patches and custom modules, from which recipes compile. | 0. Object outputs and generated headers stay in the recipe repository, so every key still differs. | Saves one extraction per recipe. | unchanged | unchanged | medium | Neutral. Useful only as part of 5. |
| **4. Generators deduplicated by spec digest** into shared paths. | Generator actions only, which are cheap. Compiles still differ by output path. | small | unchanged | unchanged | medium | Neutral. Useful only as part of 5. |
| **5. Shared tree repository with digest-named targets** (prototyped). Generators, header sets and objects live in a tree repository shared by every recipe of one source, patch list and row. Each target name is a digest of what its action reads, so equivalent work is one target. Recipe repositories keep only links and revision-dependent work. | Everything the content measurement found, plus include-directory pruning: 92 to 100 % of the compiles both engines have, for profile, module, custom-module and option variants. Variants of one row in one module are also built only once per build. | Loading the tree loads every recipe of its row (fetch and configure). Each recipe also writes about 2 MB of `shared.bzl`. Analysis: see the prototype. | Unchanged. Rendering only, so no graph or pin changes. | `objc_library` objects move like `cc_library` ones. The Swift module (one action) and Android packaging stay in the recipe. | high | Good. It is Bazel's own answer: equivalent actions are one target. Godot's SCons graph is untouched. |
| **6. Custom compile rule with `cc_common.compile`.** | 0 on its own: outputs still lie below the declaring package. It only matters for 5, to declare many objects with fewer targets. | Lower per-target overhead. | unchanged | Objective-C needs its own path. | high | Low. It reimplements `cc_library`. |
| **7. Path-independent action keys** (path mapping, REAPI normalization, a ccache-like executor cache). | Not reachable. Bazel maps only the configuration segment, REAPI keys contain the paths, and an executor-side compiler cache is not hermetic. | none | unchanged | unchanged | n/a | Poor. |
| **8. Narrow per-source inputs further** (the changes above, a define analysis, a shared build-name file). | Within a recipe: an edit reruns only what it changes. Between recipes: it multiplies the benefit of 5. | small | unchanged | unchanged | low each | Good. |

## Prototype

A prototype of option 5 (branch `claude/engine-shared-tree-prototype`, not merged) works
as follows:

- `godot_engines` groups the `godot_engine_build` declarations of one source label,
  patch list, patch strip and row. For each group it declares a `godot_engine_tree`
  repository, which:
  - extracts and patches the source;
  - adds the union of the recipes' custom modules;
  - keeps each build profile under `_build_profiles/<sha256>.gdbuild`;
  - applies the build-profile scoping.
- Rendering (`tools/engine/shared_objects.py`) writes a `shared.bzl` that describes the
  recipe's work in the tree:
  - **Generators** are named by the digest of their specification and of the identity
    of each input. Their outputs lie below `_gen/<digest>/`.
  - **The build-name file** lies below `_build_names/<build_name>/`. Unlike the revision
    hash, it depends on the build name only.
  - **Header sets** are named by their files and dependencies.
  - **Objects** are named by the source and a digest of rule, source path, options, include
    directories, defines and header sets. Each object keeps only the include directories
    that hold a file of its closure, plus their `_gen/<digest>` counterparts for its
    generated files.
- The tree's BUILD file loads every recipe's `shared.bzl` and declares the union by name
  (`godot/engine/private/shared_objects.bzl`). The recipe's engine library links the
  tree's objects. Only `version_hash.gen.cpp`, which reads the revision hash, compiles in
  the recipe.

On Android, the engine built remotely in full, and every compile saw only its declared
inputs, including the relocated generated headers. Each measurement built a variant after
`bazel clean`, with the base recipe and the variants of the rows above it in the remote
cache:

| Variant built after the base recipe | Current recipes | Prototype | Prototype with feature macros |
|---|---:|---:|---:|
| Identical copy | not measured | **1** remote, 769 hits | not measured |
| Build profile | 704 remote, 64 hits | **10** remote, 760 hits | **10** remote, 760 hits |
| Without the custom module | 704 remote, 63 hits | **19** remote, 750 hits | **20** remote, 749 hits |
| Extra module `webp` | not measured | **148** remote, 751 hits | **149** remote, 750 hits |
| `disable_physics_2d = "no"` | not measured | 777 remote, 39 hits | **106** remote, 710 hits |
| Without the patch (another tree) | not measured | 766 remote, 4 hits | not measured |

The counts are from Bazel's process summary.

- The remote counts include the link and revision actions, and the sources the base
  engine lacks (129 for `webp`, 46 for `disable_physics_2d`).
- With the current recipes, 27 of the hits are compiles that include the version header.
  An earlier run had cached them at the recipe's own path. The other hits are tool
  compiles and generators.
- A full remote build of the base engine through the tree took 35 s.
- Analysis with a fresh server took 2.65 s and configured 19,635 targets with the current
  recipes, against 2.87 s and 19,742 targets with the prototype, whose tree loaded six
  recipes.

What the prototype leaves open:

- **Tree identity.** The tree name hashes the source label string and the patch labels.
  To share across consumer modules, it has to digest the archive's sha256, the patch
  contents and the custom module contents. Starlark has no cryptographic hash, so the
  extension would have to run one through `module_ctx.execute`. Two recipes that name
  different directories for the same custom module would also collide in the union.
- **Fetch coupling.** Building one recipe loads, and therefore configures, every recipe of
  its row. Pinned recipes make this cheap, and a module typically has one recipe per row.
- **Interface.** Rendering reads the tree from an environment variable, so `configure.py`
  and every pin stay unchanged. A rendering argument would keep the pins too.
- **Patches.** A recipe with other patches gets another tree and shares nothing. Patched
  files as content-addressed overlays, like generated files, could close this.
- **Coverage.** Only Android was built. iOS (Objective-C objects in the tree, Swift in the
  recipe), desktop editors and the lock-file workflow were not exercised.

## Conclusions

- **Narrowing pays first.** Include-directory pruning (#85, merged) turns a custom-module
  change from 730 recompiles into about 19 actions within a recipe, without any change to
  repositories or pins. The remaining narrowing lever is the defines: instead of #83's
  name-based scan, a compiler-based analysis (`clang -E -Wunused-macros`) is being
  prototyped that gives each source a forced-include header with only the defines it
  uses, so compiles stay `cc_library` actions. Splitting each compile into a preprocess
  and a compile action is parked.
- **Only a shared tree repository (option 5) shares between recipes.** It pays off where
  several recipes of one row coexist: a module's test and production engines, A/B engine
  variants, or consumer projects on one remote cache. A complete version needs:
  - content-addressed tree names;
  - a rendering argument instead of the environment variable;
  - coverage of iOS and pinned recipes.
- **Options 1, 2, 3, 4, 6 and 7 share nothing,** or they cost the incremental edits that
  work today.

## Reproducing the measurements

1. Add temporary copies of `godot_beta_source_build_android` to `rules_godot/MODULE.bazel`,
   each with one difference, and `use_repo` their `_android_arm64_template_release`
   repositories:
   - Remove the `engine` attribute, so that no copy joins the beta engine.
   - Keep such recipes out of commits.
   - Leave `tools/engine/configure.py` unchanged: any change to it, even a comment,
     stales every pin.
2. **Potential.** Run `bazel aquery --output=jsonproto 'deps(...)'` once per recipe, over
   its `:libgodot_android.so`. Then, in one `bazel build --remote_download_all`, build every
   recipe's `kind('source_generator|source_revision', @<recipe>//:all)` targets. Compare
   the compiles:
   - replace `(...+)+godot_engines+<name>` in every path;
   - key each compile by argv, environment, and the (path, digest) of each input;
   - take a generated input's digest from its file in the execution root's `bazel-out`.
3. **Cache hits.** Build the base recipe, then each variant after `bazel clean`, and read
   `N remote` and `N disk cache hit` from Bazel's process summary. For engine compiles
   alone, count the `CppCompile` entries of `--execution_log_json_file` by `cacheHit`. See
   [remote execution with BuildBuddy](../../../docs/internal/verification-recipes.md#remote-execution-with-buildbuddy).
