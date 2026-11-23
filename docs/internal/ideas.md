# Ideas and to-dos

Candidate work that is not yet planned. Each entry says what it is, what is true today and
what is still open. Line references are to `main` as of 2026-11-04.

## Build speed

### Exports rerun on shared extension sources

- `GodotPack` and `GodotShellAssets` take extension editor libraries, not runtime
  ones, so a runtime-only edit reruns neither export.
- Still rerun: edits to sources the extension editor library shares, because the export's
  editor loads it.
- Still an input: extension runtime libraries of extensions without an extension editor
  library (`godot_extension` without `editor_extension`, `godot_cc_extension(build_editor_library = False)`;
  `godot/extension/defs.bzl:102-110`).
- Open: can an export skip extensions no exported resource, editor plugin or export plugin
  uses? What does a native-only edit cost per export platform?

### Reuse imports across export platforms and `bazel test`

- `GodotImport` runs in the platform-slice configuration (`_pack_export.deps`,
  `godot/private/project.bzl:1884`), while `godot_test` stays top-level (FAST-05).
- Identical actions in different output directories get different cache keys. Path mapping,
  which avoids that, is enabled only for Android `DexBuilder`/`Desugar`.
- Applications that differ only in their application context already share imports
  (`godot/private/config/transitions.bzl:48-50`).
- Open: do imports actually rerun (execution log)? Which import inputs legitimately depend on
  the export platform, e.g. feature tags? Extension editor libraries are already built for the
  execution platform.

### Measure remaining invalidation

- Measure no-op, script, asset, native and suite edits on current `main` with
  `tools/verify_incrementality.py` before choosing an optimization (FAST-04–10, TST-08).
- Known: a script edit reruns only `GodotPack`; an autoload or editor-plugin edit
  also reruns `GodotShellAssets`, which is necessary.
- Gap: imports exclude extensions disabled for import (`project.bzl:888-904`), but
  `tools/verify_incrementality.py` has no probe for it.

## CI

### Avoid cache-mount holders instead of killing them

- `.github/actions/setup/stop-bazel/post.js:125-166` kills every holder of the sticky-disk
  mount with `sudo fuser -k`.
- Idea: keep the repository contents cache off the mount and bound nested Bazel servers with
  `--max_idle_secs`.
- Nested servers start in `tools/validate_patch_application.py`,
  `tools/validate_extension_compatibility.py`, `tests/analysis/app_platforms/isolation_test.py`
  and `tests/analysis/engine_configuration/repositories_test.py`.
- Open: which processes hold the mount in practice; extraction cost of moving the cache.

### Analysis size of the desktop tests

- The ruleset's desktop set, the work `test:bazel`, configures 1.54 million targets on macOS (0.96 million on Linux).
  1.11 million are `toolchain` targets: every configuration evaluates all 1,295 registered
  toolchains, 696 of them Go toolchains (12 Go SDKs for 58 platforms each, from rules_go and
  rules_android).
- The toolchain targets are cheap: 700 more per configuration cost 1 s of 12 s on an M5 Max.
  The time goes to about 1,000 configurations, most of them from the 126 tests in
  `//godot/platforms/...` (1.0 million configured targets, 158 of 185 CPU seconds).
- A fresh CI job also extracts 13 GB of repositories, 6.4 GB of them export templates.
- Since `godot/private/config/native.bzl` decides the native options and an application
  configures its native code once per platform slice, the desktop set configures 1.31 million
  targets in 890 configurations (845 target, 45 exec) on macOS.
- Remaining: the content configuration and the project context still analyze the native
  edges of extensions and add-ons (an extension's `library` and `implementation_deps`, an
  add-on's `platform_deps`), although only platform slices build them: one native
  configuration per application on iOS and Android that nothing packages, and on macOS
  where the build's minimum differs from the application's.
- A fix needs the export and the project context to describe an extension's libraries
  without analyzing them, for example from names the extension declares, or native edges
  that reach nothing outside platform slices.
- Open: which fixtures could assert at rule level instead of on whole applications.

## Tests and conventions

### Regression project layout

- Applies to the regression module `rules_godot_tests` at `tests/`.
- Agreed layout: a project root holds `project.godot`, `BUILD.bazel`, `main/` and `tests/`;
  platform library sources in `android/`, `ios/`; engine modules in `engine/modules/<name>/`
  (one directory per module) and engine patches as files in `engine/patches/`;
  native code used only by tests in `tests/`; a `tests/` directory is always a package.
- Today 5 project `tests/` directories are not packages and 15 `godot_test` targets sit in
  project roots.
- Add three rules: `tests/` is a package, test targets live in test packages, project roots
  hold only the agreed entries.
- Open: where `engines/<set>/` registration-set packages fit.

### Target visibility rule

- No rule checks visibility. Of 117 example/test `BUILD` files, 17 have a public default and
  77 have none.
- The API contracts already check the visibility of public companion targets
  (`tools/docs/output_contracts.py`).
- Open: are public example entry targets intentional? Check broad package defaults, broad
  target visibility, or both? Cross-module consumers must stay allowed.

### Remaining convention predicates

- Drafts not yet rules: N4–N6, P1–P3, I3–I5, L5–L12 in
  `docs/internal/conventions-rules-draft.md`.
- Open: how to elect a package's primary entry (N4/N5); P3's scope for reusable fixtures.

## Examples

### Ruleset regressions for SDK cases the AppAuth example does not exercise

- The AppAuth add-on (`examples/addons/app_auth`) shows Maven and Swift Package Manager
  resolution, transitive AndroidX libraries, library resources, manifest entries and a
  manifest placeholder. It has no dynamic Apple framework and no JNI library inside an AAR.
- Cover those as ruleset regressions under `tests/`, not as another example: an Android
  application whose `aar_import` carries `jni/<abi>/*.so` (the libraries must reach
  `lib/<abi>/` beside the engine library). An iOS application embedding and signing a platform
  library from `apple_dynamic_xcframework_import` is covered by
  `//godot/platforms/private/tests/library_composition:ios_dynamic_framework_app_embeds_framework_test`.
- Open: which existing regression project each case extends, such as
  `tests/projects/mobile_transitive_libraries`.

### Sentry reference case

- Pin a Sentry version and choose features and operating systems before claiming support
  (ADD-04). Generic extension support is not vendor acceptance.

## Engines

### Several engines in one module

- Games often change their engine: a module or patch that only this game needs. The project
  layout keeps those under the project's `engine/` for that reason, and such a project should
  build and test with its engine the way Lichtpost does with the prebuilt one, without
  per-invocation flags or toolchain registrations in the consumer's `.bazelrc`.
- Registration order of engine hubs is global per module; `--extra_toolchains` reorders
  them per invocation. Petri's source-built engine is selected that way, with `build:petri`
  in `examples/.bazelrc`, plus a `bool_flag` whose only job is to let `target_compatible_with`
  skip Petri's checks and tests without the config (`examples/projects/petri/BUILD.bazel`).
- The documented alternative, a component per slot whose payload is a `select()` on a
  build setting ([engine guide](../../rules_godot/docs/public/engine.md#choose-between-prepared-recipes)),
  needs one declaration per host slot and the same flag.
- Candidate first step: `target_settings` on the hub's toolchains, as the components
  already use for the variant (`godot/engine/private/components.bzl`, `toolchain(...,
  target_settings = [variant])`). `godot_runtime_component`, `godot_editor_component` and
  the `source_build` tag would take a `target_settings` list and pass it to every
  generated `toolchain()`; a hub registered ahead of the prebuilt one then matches only
  while its config setting holds, and falls through otherwise. One flag selects the engine
  and marks the targets compatible, `--config=petri` shrinks to that flag, and
  `--extra_toolchains` leaves `examples/.bazelrc`. To verify first: `target_settings` on
  editor toolchains is evaluated in the consuming target's configuration, where the flag
  lives, not on the execution platform.
- Open: how applications of one module choose different engines without per-invocation
  flags or per-slot boilerplate, e.g. an application attribute that transitions that build
  setting, or a macro that generates the per-slot `select()` components from a hub.

### Configurable deployment targets of engine recipes

- A macOS or iOS source recipe compiles for the deployment target Godot's SCons platform
  sets (11.0 on macOS arm64, 14.0 on iOS), recorded as `minimum_os` and enforced by a
  transition on the recipe's native graph; an application's minimum is only its bundle's
  and its extension libraries'.
- Open: a `godot_engine_build`/`source_build` attribute that raises a recipe's deployment
  target above Godot's floor, per operating system, for engines that drop old systems on
  purpose; how it reaches the recipe's transition and the runtime's provenance.

### Readable targets for engine sources and modules

- `godot_engine_build` and `godot_engines.source_build` take `source = "@godot_sources//:source.json"`
  and `custom_modules = {"//path/to/module:config.py": "name"}`: a repository rule configures
  the recipe at fetch time and can read source files only, so the descriptor file and each
  module's `config.py` stand in for the repository and the module directory.
- Open: a module-level target or package label as the handle (a marker target that names
  the directory, a filegroup contract), and whether the module name can come from it; the
  descriptor could stay internal behind a repository-name attribute that resolves to it.

## Android shell

Gaps to Godot's Gradle export, recorded in
[the Android shell reference](../../rules_godot/docs/internal/android-shell.md#remaining-differences).

### Project files in an install-time asset pack

- Godot's export puts an App Bundle's project files into the install-time asset pack
  `assetPackInstallTime`; `godot_app` puts `assets/main.pck` into the base module
  (`godot/platforms/private/android.bzl`, `assets` of the bootstrap), so Google Play's base
  module size limit applies to the whole project.
- rules_android's `android_feature_module` has `is_asset_pack`.
- Open: does it give install-time delivery and keep the PCK uncompressed; does Godot find
  `main.pck` in an asset pack through `--main-pack res://main.pck`; does the APK keep it in
  `assets/`?

### Localized Android application name

- Godot's export writes `res/values-<locale>/godot_project_name_string.xml` from
  `application/config/name_localized` or the project's translations, for the locales of its
  template's `values-*` directories; `godot_app` writes one `android:label`.
- The probe already reports `name_translations`, which the Apple shell uses
  (`tools/platforms/shell_apple.py`).
- Open: which locales to write; a resource directory beside `themes.xml` per locale.

### Godot's libc++_shared.so among platform libraries

- Godot's `build.gradle` keeps its own `lib/<abi>/libc++_shared.so` with `pickFirst` when a
  dependency ships one too; rules_android has no equivalent, and extension libraries of one
  name fail the build.
- Open: does a supported engine or library ship `libc++_shared.so`; what rules_android does
  with duplicates from AARs; whether to pick Godot's or fail with both sources.

## Capability gaps

- **Additional packs with extension libraries:** `godot_app` ships only its start pack;
  `required_packs` does not ship packs, `additional_packs` exists only for source runs. Define
  how an additional pack's project delivers its extension libraries (PCK-08, ADD-07).
- **Mobile test automation:** no install, launch or on-device GdUnit tooling (RUN-06, TST-07);
  Android/iOS runtime checks are manual.
- **Editor resource lifecycle:** the metadata run writes missing UIDs into
  `ext_resource` entries, so references can follow a move by UID. Open: import paths
  and `BUILD` declarations after creating, renaming or deleting files linked through
  `resource_paths`.
- **Configuration reuse:** the test adapter composes its own project
  (`godot/private/adapter.bzl:89-90`); reduce duplicated configuration across editor, checks,
  tests and export (RES-06, RES-07).
- **Automatic BUILD maintenance:** beyond `tools/godot_build_files.py`; Gazelle is one option.
- **Resource diagnostics:** binary `.scn`/`.res` formats; change-impact explanations (FAST-10).
- **Generated extension glue:** generated registration/backend code (GEN-01/02/04); Platform
  Paths is the hand-written baseline.
- **More support dimensions:** Windows and Web applications, Windows execution platforms,
  C#/.NET, AAB upload signing, further engine/renderer/CPU combinations. Each needs a concrete
  scenario.

## Add-on golden path

### Gaps for add-ons that consume a platform SDK

Found while planning and implementing the AppAuth example add-on
(`examples/addons/app_auth`). `godot_app.android_manifest_values` closed the missing
manifest placeholders; the rest is open.

- **No macOS platform libraries:** desktop `godot_app` rejects `platform_deps` and
  `platform_resources` (`godot/platforms/private/desktop.bzl:147-148`) and never reads the
  project's `platform_libraries`, so an extension's macOS `platform_deps` are dropped without a
  diagnostic. An Apple SDK therefore enters iOS through `platform_deps` (code and resources)
  and macOS through the extension's C++ `deps` (code only); SDK resource bundles, such as
  AppAuth's privacy manifest, never reach a macOS bundle. Open: reject or support macOS
  platform libraries; how resource bundles reach desktop bundles.
- **Swift packages:** the public guides show Swift bridges and XCFramework imports, not how to
  consume a Swift package. The AppAuth example uses `rules_swift_package_manager`; consumers
  must find out themselves that `.mm` sources need `@import` with `-fmodules -fcxx-modules`,
  that frameworks SwiftPM autolinks (AppAuth's `Security`) must be declared, and that
  `swift package` leaves a `.build/` scratch directory beside `Package.swift`. Open: which of
  this belongs in the [extension guide](../../rules_godot/docs/public/gdextension.md#platform-libraries).
- **Go toolchain of transitive rulesets:** `rules_swift_package_manager` raises Gazelle to a
  version whose tools need Go 1.24.12 or newer, while rules_android's `deploy_info` has Gazelle
  build them with rules_android's Go 1.22.4, the first registered SDK. The examples module pins
  `rules_go` and a root `go_sdk.download` (`examples/MODULE.bazel`). Open: whether the
  [platform guide](../../rules_godot/docs/public/platforms.md#add-on-platform-libraries) should name this
  for consumers that combine Android with Swift packages.
- **Android plugin bridge:** an extension reaching Java needs a `GodotPlugin`, manifest
  meta-data, a C++ call through `Variant::callp` on the Engine singleton, plugin signals for
  asynchronous results, keep rules and `@godot//android:plugin_api`
  (`examples/addons/platform_paths/native/backends/android/`). The platform guide's template covers
  only the declarations. Generated backends are a separate entry (GEN-01/02/04 under
  capability gaps).
- **Per-operating-system declarations:** an extension with backends repeats one `select()`
  per attribute: `target_compatible_with`, `deps`, `platform_deps`
  (`examples/addons/platform_paths/BUILD.bazel`). Open: whether a declaration per operating
  system would be clearer than parallel selects.
- **Bindings per module:** within a module, `godot_cpp_bindings.enabled_classes` is one list
  for every extension; an add-on cannot declare the classes it needs, and adding one rebuilds
  the bindings for all.
- **Add-ons from another module:** an add-on published as its own Bazel module declares every
  repository its targets name ([module ownership](../../rules_godot/docs/public/project-layout.md#module-ownership)).
  Maven works: `maven.install` tags merge across modules; the consumer lists the module in
  `known_contributing_modules` and owns the pin. The engine hub (`@godot//android:plugin_api`)
  couples the add-on to the consumer's engine request. Each module generates its own
  `godot_cpp_bindings`: harmless for shared libraries and for the default iOS frameworks;
  extensions with `ios_linkage = "static"` from two modules share the executable, where
  different `enabled_classes` fail with duplicate symbols. `rules_swift_package_manager`
  supports only the root module, so an Apple backend cannot see the consumer's Swift packages.
  Open: bindings shared across modules; how an add-on reaches the consumer's Swift packages
  (for example a `label_flag`); how an add-on names the consumer's engine hub.
- **Info.plist fragments only on resources:** `infoplists` exists on `godot_resources`, not on
  extensions, so an extension-only add-on that needs Info.plist entries adds a resources
  target for them.
- On-device checks of SDK flows depend on mobile test automation (capability gaps).

## Documentation to-dos

- `rules_godot/docs/internal/capabilities.md` is a 2026-11-01 snapshot from before features 003–007;
  EDT-06 is stale.
- `docs/internal/conventions-rules-draft.md` maps only N1–N3 to rules; L1–L4 are
  RG009/RG011/RG010/RG008, I1 is partly RG012 and I2 partly RG007.
