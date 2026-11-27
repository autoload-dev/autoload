# Verification recipes and fixtures

Use the section needed for the task at hand; this page is not a checklist to execute in full.
The [verification policy](verification.md) determines when evidence is needed, and
[verification hosts](verification-platforms.md) determines the representative scope.

- New environment or missing SDKs: [toolchains](#toolchains).
- API source changes: [API documentation](#api-documentation).
- New or moved Starlark modules: [generated BUILD declarations](#generated-build-declarations).
- Platform Paths operating-system integration:
  [runtime acceptance](#platform-paths-runtime-acceptance).
- Offloading work and tests to BuildBuddy: [remote execution](#remote-execution-with-buildbuddy).
- Selecting an engine in a ruleset test: [engines in ruleset tests](#engines-in-ruleset-tests).
- Finding an existing ruleset regression: [fixture catalogue](#regression-fixtures).

## Toolchains

A checkout needs only Bazelisk (`bazel`) and the Aspect CLI (`aspect`). Bazelisk runs the Bazel
of [.bazelversion](../../.bazelversion), the launcher the Aspect CLI of
[.aspect/version.axl](../../.aspect/version.axl). Prebuilt tools (jactionlint, rumdl, the CodeScene
CLI, Node, Android's sdkmanager) are pinned in [multitool.lock.json](../../multitool.lock.json)
and come through Bazel; Python tools run with Bazel's rules_python interpreter, the linters'
packages from [tools/lint/requirements.txt](../../tools/lint/requirements.txt); Java for the
Android SDK tools is Bazel's remote JDK 21 unless `JAVA_HOME` is set. The Android SDK pins
(API levels, build tools, NDK) are in [tools/android/sdk.json](../../tools/android/sdk.json).
`aspect help` lists the tasks. Prefix direct commands that need the repository environment
with `aspect exec --`: it sets the Android variables
([.aspect/config.axl](../../.aspect/config.axl)) and puts Bazel's Python on the path as
`python3`. Bazel actions continue to use their declared toolchains. Native C/C++
compilers remain host prerequisites; source-engine and iOS checks need macOS and Xcode.

For a complete development environment in a fresh clone, run:

```sh
./bootstrap.sh
```

It places the pinned Bazelisk and Aspect launcher in `~/.local/bin` (or `BIN_DIR`), verified
by their releases' checksums, and names what is missing from the host or PATH. It then runs
`aspect bootstrap`, which installs the pre-commit and pre-push hooks and the missing Android
SDK/NDK components, and ends with `aspect doctor`, which names what the setup still lacks;
run it again whenever the setup seems off. Bootstrap reuses SDK components outside the
checkout across worktrees; set `ANDROID_HOME` or `ANDROID_NDK_HOME` before setup for a
nonstandard installation;
`--android=false` and `--hooks=false` skip a part, and `--tools-only` installs just the two
tools, as CI does. A new worktree needs none of it again; how worktrees reuse Bazel's state
is in [agent setup](agent-setup.md#worktrees).
Bootstrap is safe to repeat but is not a required step before each check.

For work that does not need Android, `aspect bootstrap --android=false` installs just the
hooks. Android tasks prepare their own prerequisites through `android:setup`;
`aspect work android:setup` prepares only the Android environment. Java, SDK manager, Node and
workflow-lint tools are installed when their owning tasks require them. `//tools/android:requirements_test`
checks provisioning declarations without installing SDK components.

Before its checks, the pre-push hook verifies that the working tree matches the pushed
commit. CI uses the same tasks through the shared
[setup action](../../.github/actions/setup/action.yml), which installs the pinned Bazelisk and
Aspect launcher and configures Bazel's repository cache. Android
workflow jobs reuse cached missing SDK components; host-only ones do not install Java or
Android SDKs. CI logs Xcode/SDK versions on its macOS jobs; compare with `xcodebuild -version` locally when CI runner
equivalence matters. GitHub's runner images can change.

CI does not collect or upload Bazel diagnostic artifacts. For a specific local
investigation, enable the needed logs on that invocation:

```sh
bazel test //path/to:target --execution_log_compact_file=/tmp/execution_log.binpb.zst --remote_grpc_log=/tmp/bazel-remote-grpc.log --profile=/tmp/bazel-profile.json.gz
```

The compact execution log records actions, their inputs, outputs and cache results.
The gRPC log records calls to a remote cache or executor. Open the JSON trace profile in
[Perfetto](https://ui.perfetto.dev) or summarize it with `bazel analyze-profile` to inspect
the critical path and action timings. Keep these files only for the investigation.

## API documentation

For API source changes, build the registry's documentation metadata in `rules_godot/`:
`bazel build //:bcr_docs`, which the fast test `//godot/tests:bcr_docs_test` also builds.
Buildifier's docstring warnings in the lint check cover module and function docstrings; the
documentation of rules, attributes and provider fields needs review. See
[API documentation maintenance](../../rules_godot/docs/internal/api-reference.md) for the metadata.

## Generated BUILD declarations

[Gazelle](../../tools/gazelle/BUILD.bazel) generates the ruleset's `bzl_library` targets,
one per Starlark module outside its `tests` packages, named after the file. Their
directives, including where an external load's library lives, are in the ruleset's root
[BUILD file](../../rules_godot/BUILD.bazel). Its Godot language declares the Godot projects,
resources and GdUnit tests of `examples/` and `e2e/` ([Gazelle for Godot](gazelle.md)). After
adding, moving or removing a Starlark module of the ruleset or a file of a Godot project,
regenerate them from the repository root:

```sh
bazel run //tools/gazelle:update
```

`bazel run //tools/gazelle:check` prints the difference and fails where a BUILD file is
stale. Gazelle reads every directory, so the check is no Bazel test: `aspect check`, which
the pre-push hook runs, and the Linux job run it beside the conventions tool.

## The file lint

The file lint ([tools/lint/files.py](../../tools/lint/files.py)) runs the linters of files
that have no Bazel targets of their own: gdlint on GDScript (`.gdlintrc`), rumdl on Markdown
(`.rumdl.toml`), shellcheck on shell scripts and the
[convention rules that judge each file on its own](conventions.md#run-and-maintain-the-checks).
It selects their files by name from `git ls-files`, in the whole repository, the add-on and
registry test modules included, and runs each tool once over its files, all at the same
time:

```sh
bazel run //tools/lint:files                      # the files changed since the merge base with origin/main
bazel run //tools/lint:files -- --scope=all       # every file Git lists, as the Linux job runs it
bazel run //tools/lint:files -- path/to/file.md   # the files given, as the pre-commit hook runs it
```

`aspect check`, and with it the pre-push hook, lints the changed files, but rumdl checks every
Markdown file in each run: its rules MD057 and MD051 resolve the local links and their
fragments, which a change of another file can break. A finding fails the
run with the tool's own diagnostics, one per line as `<path>:<line>: <message>`; a tool that
cannot check exits with another code than 1, which fails the run too. With `--fix` it runs
the formatters that rules_lint's `format_multirun` has no place for instead: `rumdl fmt` on
Markdown and clang-format on Objective-C. `aspect format` runs them through
[tools/format](../../tools/format/BUILD.bazel), beside Ruff, Buildifier, clang-format on C
and C++ ([.clang-format](../../.clang-format), with Godot's style for the Dart extension;
[.gitattributes](../../.gitattributes) leaves Godot's engine modules out, whose lock files pin
their files) and shfmt on shell scripts
([.editorconfig](../../.editorconfig)).

gdformat, GDScript's formatter, is left out: it rewrites the repository's scripts in a style
of its own, such as `class Name:` with `extends` on the next line and method chains broken
into `. method(` lines, so a third of them would change for the worse. google-java-format is
left out too: its `--aosp` style fits most of the 17 Java files, but it would need a Maven
artifact, a `java_binary` with the JVM's `--add-exports` flags and a JDK in every formatter
run, and the engine's own Android files, which keep Godot's tabs, excluded.

To add a linter, add its executable under a variable to `FILE_TOOLS` in
[files.bzl](../../tools/lint/files.bzl), and a `Tool` with that variable to `TOOLS` in
`files.py` with the files it takes and its arguments. Any program that takes paths, prints
findings as above and exits 1 on them fits; a new convention rule that judges each file on its
own needs no change here, only its registration in
[per_file.py](../../tools/conventions/per_file.py).

The tools are millisecond scans of a few hundred files: the whole tree takes about six
seconds, so Bazel's per-package caching would buy little. It did cost a Gazelle language,
a generated filegroup per package and kind, and aspects built on rules_lint's private
helpers. [alint](https://alint.org) was tried as the host instead (0.23): its `command`
rule starts one process per file, one file after the other, and took 497 seconds for the
same tools over the whole tree, folding each file's findings into a single line. Its native
rules, which start no process, suit checks of the repository's shape.

## Profiles

A Bazel server keeps the analysis of one configuration: a command that changes the build
options, such as `--config=android`, discards the analysis of the previous one. So that
desktop and mobile work keep theirs, [tools/bazel](../../tools/bazel) runs each profile in an
output base and server of its own. `AUTOLOAD_BAZEL_PROFILE` names the profile; without it,
Bazel uses the workspace's own output base, the `default` profile. The named work sets the
profile of the source-engine work, `source-engine` ([tools/ci/work.py](../../tools/ci/work.py)),
so the pre-push hook and the desktop work stay warm in `default`. The mobile release builds and smoke tests need no
profile: their applications carry their configuration (`godot_configured_app`,
[examples/releases.bzl](../../examples/releases.bzl)):

```sh
AUTOLOAD_BAZEL_PROFILE=source-engine aspect exec -- bazel test //examples/petri/...
```

A profile's output base lies beside the default one, named by the MD5 of it and the profile,
so `aspect output-bases` and `aspect gc` treat it like any other. Its server exits after
`AUTOLOAD_BAZEL_PROFILE_IDLE_SECONDS`, 15 minutes by default. Actions do not run twice:
the remote or disk cache that `~/.bazelrc` sets, such as the macos-ci host's Bazel cache
server, and path mapping share their results across profiles. Profiles belong to the root module: the ruleset and the add-on modules keep their
own server, also for the commands that root-module work starts there.

## Remote execution with BuildBuddy

Every module imports [buildbuddy.bazelrc](../../buildbuddy.bazelrc). Its configs need a
BuildBuddy API key, which stays outside the repository: a credential helper for
`*.buildbuddy.io` in `~/.bazelrc` that answers Bazel's `get` request with an
`x-buildbuddy-api-key` header, for example from the macOS keychain.

```sh
bazel build --config=buildbuddy //...         # this host's target platform, Linux work remote
bazel test --config=buildbuddy-linux //...    # target Linux, so tests run remotely too
```

`--config=buildbuddy` keeps the host as target platform: actions that only this host can
run, such as Xcode compiles and signing, stay local, and tests run on an execution platform
that matches the target platform. `--config=buildbuddy-linux` targets Linux for every
command, so build, run and test share one configuration; Apple-only tests are then skipped
as incompatible. Each invocation reports the repository, commit, branch and tree status as
build metadata through `buildbuddy_status.sh`, with a tag naming the module.

### When remote execution pays off

BuildBuddy is a regular way to build and test here, not a fallback. Consider it for every
run that does real work, and choose by what the run needs:

- **Parallelism:** executors run as many actions and tests at once as `--jobs` in
  `buildbuddy.bazelrc` allows, beyond this host's cores, so many uncached compiles or a
  larger suite can finish sooner.
- **A free host:** remote work keeps this host usable during builds or suites that would
  otherwise occupy it for minutes.
- **Linux targets:** from a Mac, tests that need a Linux target run only with
  `--config=buildbuddy-linux`; Android builds run on the executors (see below).
- **Shared results:** the remote cache serves every worktree and later remote run, and each
  invocation gets a BuildBuddy page with its timing profile.

Against that stands a fixed cost per invocation. Each remote round trip adds seconds for
scheduling, input upload and result download, more when BuildBuddy cannot reuse a warm
runner, and switching between a local and a remote config discards Bazel's analysis cache.
Cache hits cost about the same either way, so a run of a few short uncached actions can
finish locally first. `--config=buildbuddy` keeps actions only this host can run, such as
Xcode compiles, local, so Apple-heavy work gains less.

When unsure, try it and compare: Bazel's summary line shows how many actions ran `remote`
and the critical path, and the invocation page shows where the time went.

To use Bazel flags for one task, set `AUTOLOAD_BAZEL_FLAGS` to whitespace-separated
flags. [tools/bazel](../../tools/bazel), which Bazelisk runs in place of Bazel in every
module, adds them to every command that reads build options, including those of `aspect`
tasks and of the build tools under `tools/`; the command's own flags win. A Bazel binary
started without Bazelisk ignores the variable.

```sh
AUTOLOAD_BAZEL_FLAGS=--config=buildbuddy aspect tests --tier=all
AUTOLOAD_BAZEL_FLAGS=--config=buildbuddy-linux aspect exec -- bazel test //...
```

Some work needs this host as execution platform even under a remote config, such as the
formatters that `bazel run` starts here. Adding `--config=host-execution` from
[shared.bazelrc](../../shared.bazelrc) after the remote config names this host again; the
remote cache still applies.

Android builds of `examples/` and `tests/` run their actions on BuildBuddy's
executors: the root module registers the toolchains of
[`godot_android_toolchains`](../../rules_godot/docs/public/platforms.md#remote-execution-of-android-builds), which
add the pinned Linux SDK and NDK for Linux executors. Its pins in
[android_toolchains.bzl](../../rules_godot/godot/platforms/private/android_toolchains.bzl) follow the
Android versions of [sdk.json](../../tools/android/sdk.json), which `//tools/android:requirements_test` checks.

For settings on every invocation, such as `common --config=buildbuddy`, create
`user.bazelrc` at the repository root. Every module imports it, and git ignores it.

CI's host jobs write `ci.bazelrc` at the repository root, which the root module and the ruleset
import, to set `--config=ci` (shared.bazelrc) on every command: a stale `MODULE.bazel.lock`
then fails the command instead of being rewritten. Locally, Bazel updates the file, and
`aspect generate` regenerates it; `--config=ci` reproduces CI's check, at the price of a
reload of every package when the mode changes.

## Platform Paths runtime acceptance

Use this recipe when changing Platform Paths' Android or iOS operating-system integration,
or when explicitly accepting its mobile runtime behavior. A BUILD-only move or documentation
edit does not require repeating it. Build commands and SDK setup remain in the
[example README](../../addons/platform_paths/README.md#mobile-builds).

On Android, install and launch on a matching ARM64 device/emulator. Check all five path
categories, their scopes, absence of an unnecessary storage permission prompt, legitimate
Temporary/Cache equality and behavior after relaunch. If Downloads is unavailable, use
available app-specific external storage to check successful resolution.

On iOS, use a simulator/device matching the platform slice of the selected runtime and check
the five container locations. Use existing signing attributes if a provisioned device is the
chosen environment. Both operating systems should show useful category-specific reasons for unavailable/failed lookups
while preserving unaffected rows. Build/package inspection complements these runtime checks;
no mobile automation framework or Store deployment is required.

## Engines in ruleset tests

A ruleset test selects its engine and toolchains as a consumer would. The contract
docstring of [toolchains.bzl](../../rules_godot/godot/private/tests/toolchains.bzl) owns the details.

| The test needs | It uses |
| --- | --- |
| The default engine `@godot` or the Android SDK and NDK | Nothing: MODULE.bazel registers them and their toolchains. |
| Another complete development engine, such as the beta engine | The engine's name: the `engine` attribute of `configured_outputs` or `engine_test`. |
| A few slots of its own, a source-built hub, or registration order as its subject | `--extra_toolchains`: `own_toolchains` in an analysis test, the `extra_toolchains` attribute of `configured_outputs` in a build-output test. |

## Regression fixtures

The projects below are controlled inputs for rules_godot regressions, separate from each
example's own tests. For area responsibilities, see the [test-area map](../../e2e/rules_godot/AGENTS.md).
They are the consumer scenarios in `e2e/rules_godot/` of the root module: run their labels from the
repository root, and the ruleset's own labels (`//godot/...`, `//tools/...`) from `rules_godot/`.

Use these project cases to find a concrete behavior:

| Case | Behavior and useful test labels |
|---|---|
| `editor_view` | Editor writeback, sidecars and disabled extensions, from `rules_godot/`: `//godot/private/tests/editor_view` |
| `script_run` | Direct script execution, imports and command-line arguments: `//script_run` |
| `adapter_test` | A fake test adapter's cases, filtering, sharding and exit code, from `rules_godot/`: `//godot/private/tests/adapter`; GdUnit's pass/fail/empty/skipped runs, filtering, sharding and JUnit, including a failed assertion's details, are autoload_gdunit's end-to-end tests: `bazel test //e2e/addons/gdunit/...` from the repository root |
| `content_validation` | Per-unit validation: parse and type errors, failing base scripts, dependents against their dependencies' interfaces, undeclared global classes, warning settings and the add-on exemption, no project code, autoloads and the class cache, from `rules_godot/`: `//godot/private/tests/validation` |
| `import_context_runs` | Composed settings and autoloads applied at runtime, an import input's own kept private: `//godot/private/tests/import_context_runs`; sidecars, import units, path and collision failures and metadata policies are analysis tests in `//godot/private/tests` |
| `gltf_external_buffer` | External glTF buffer available during import but absent from the pack, from `rules_godot/`: `//godot/private/tests/gltf_import` |
| `import_export_plugins` | Import plugins, that no export runs an add-on's export plugin, the configuration of each purpose and the icons and splash images Godot's exporters render: `//godot/private/tests/import_export_plugins` |
| `resource_graph_resolution` | Real graph action over generated source declarations, from `rules_godot/`: `//godot/private/tests/resource_graph` |
| `extension_staging` | The extensions a pack carries and lists, and actual extension library loading: `//godot/extension/tests/staging` |
| `export_settings` | Godot's exported Android/iOS facts, bridge files, exporter facts, release settings and shell files, from `rules_godot/`: `//godot/platforms/private/tests/export_settings` and `//tools/platforms/tests:godot_shell_test` |

The export-settings cases intentionally include incomplete engine inputs to inspect
generated metadata. They are not runnable game examples. The desktop smoke scenarios
below boot a real packaged application. Multiple assertions share each useful
project context; the directory layout does not require a project per assertion or a
BUILD file per source directory.

Focused tests such as `godot_staging_test`, `execution_test`, `editor_view_test` and `versions_test`
live in a `tests/` subpackage of the package they test, such as `tools/tests/`. `//godot/private/engine/tests:pinned_godot_sources_match_the_reviewed_android_shell_test` checks the pinned
Godot sources against the [reviewed Android shell](../../rules_godot/docs/internal/android-shell.md#review-a-godot-version). They are not additional checked-in Godot
projects. Pack-membership assertions live in `//godot/private/tests/pack_membership`.

### Extension loading and engine compatibility

```sh
bazel build //godot/extension/tests/fixtures/c_abi:hello
bazel test //godot/extension/tests/...
```

`//godot/extension/tests/compatibility` runs a
godot-cpp extension in the stable and the beta engine and checks that the engine is no input
of the extension's native actions.

### A project's own add-on

The Linux smoke scenario keeps an add-on of its own beside its content, as a consumer
does: `main/addons/native_counter/` wraps a godot-cpp extension class in GDScript, the pack
includes it and a GdUnit suite in the project's `tests/` uses it. The add-on modules cover
add-ons that several projects share. On a Linux host:

```sh
bazel test //e2e/rules_godot/smoke/linux:project_addon_counts_test
```

autoload_gdunit's run tests also launch an intentionally failing suite and require the JUnit
report to keep the assertion's details, expected 5 versus actual 4:

```sh
bazel test //e2e/addons/gdunit/...
```

The mobile smoke paths `smoke/android` and `smoke/ios` package their own copy of the add-on.
From `tests/`, run
`aspect exec -- bazel test --test_tag_filters=android //e2e/rules_godot/...`, or `ios` for iOS.

### Source-built engine applications

From `rules_godot/`, on macOS ARM64 with Xcode selected:

```sh
bazel test //tools/engine/tests/...
cd tests
bazel test //e2e/rules_godot/patched_engine/tests:app_runs_patched_engine_test --extra_toolchains=//e2e/rules_godot/patched_engine/engines/stable:all
bazel test //e2e/rules_godot/patched_engine/tests:app_runs_patched_engine_test --extra_toolchains=//e2e/rules_godot/patched_engine/engines/beta:all
bazel test //e2e/rules_godot/patched_engine/tests:app_runs_patched_engine_test //e2e/rules_godot/patched_engine/tests:source_built_editor_test --extra_toolchains=//e2e/rules_godot/patched_engine/engines/source:all
bazel aquery 'mnemonic("CppCompile|ObjcCompile|GodotGenerate", @patched_macos_arm64_template_release//:godot)'
```

The patch changes the engine banner. The `BazelProbe` module registers a class
whose `answer()` returns 42; the exported app prints that answer and the engine name and
fails unless both match. `app_runs_patched_engine_test` boots the app with the runtime of
the registration set that `--extra_toolchains` names and asserts both lines. The stable
engines come from a pinned commit snapshot of Godot's 4.7 branch (4.7.3-rc), not a release
archive; with `engines/source`, `app_runs_patched_engine_test` and
`source_built_editor_test` check the module and patch in the reduced runtime and in the
separately built, fuller editor.

The ruleset's tests tagged `source_engine` build Android and iOS applications with
source-built engines, among them the patched beta engine and the source-built ARM64
Simulator runtime. They are also `manual`, so `//...` does not analyze their source recipes.
From `rules_godot/`, with the Android SDK and NDK installed:

```sh
bazel query 'attr(tags, "\bsource_engine\b", tests(//godot/...))' | xargs bazel test
```

`aspect work source-engine:full` runs this command, the `patched_engine` tests above and
Petri's suite; `aspect work source-engine` runs a quicker subset
([which cases, and where CI runs them](verification-platforms.md#source-engine-workflow)).


### Packaged desktop application

The desktop smoke scenarios `smoke/linux` and `smoke/macos` each own a project with a C ABI
and a godot-cpp extension and an imported SVG texture, and are compatible with their own
host only:

```sh
bazel test //e2e/rules_godot/smoke/linux/... //e2e/rules_godot/smoke/macos/...
```

`app_boots_with_extensions_test` inspects the desktop archive and boots the exported
application, requiring both extensions to load and register their Godot class and the
imported texture to load from the pack. On macOS, `app_is_adhoc_signed_test` verifies the
archived bundle's ad hoc signature, of the application `godot_configured_app` signs ad hoc.
CI's host jobs run them.

### Mobile artifact checks

The ruleset's Android and iOS build-output tests live in the `tests` packages beside the
code they test, such as `//godot/platforms/private/tests/library_composition`,
`//godot/platforms/private/tests/app_platform_selection` and
`//godot/platforms/private/tests/engine_probe`. Each builds its fixture application through a
test-only transition that selects the platform, CPUs, format, variant or release settings it
needs, so they run without `--config` in CI's host jobs, which
provision the Android SDK and NDK. Android tests are skipped where rules_android finds no
SDK; iOS tests need macOS with Xcode. Release tests compare Android Build IDs and DWARF and
iOS executable/dSYM UUIDs. The platform-library cases check delivered classes, resources,
permissions, symbols and Info.plist fragments. The prebuilt beta engine's tests inspect their
declared application, engine and tool inputs; `official_beta_ios_link_links_selected_engine_test`
checks an unsigned device executable, which is not a signed device IPA.

The scenarios' mobile smoke tests are tagged `android` or `ios`: the fast tier leaves them
out, and each CI job runs its host's (`ci-linux`, `ci-macos` in shared.bazelrc). Their
applications carry their configuration (`godot_configured_app`); the tag selects them:

```sh
aspect exec -- bazel test --test_tag_filters=android //e2e/rules_godot/...
bazel test --test_tag_filters=ios //e2e/rules_godot/...
```

| Tag | Application | Checks |
| --- | --- | --- |
| `android` | an arm64 App Bundle | the Android smoke bundle: engine, extension library and pack |
| `ios` | x86_64 Simulator applications of the official templates | the iOS smoke apps' embedded extension framework and statically linked extension entry |

CI's host jobs run these tests. To record artifact-level evidence
of the smoke applications, build them, then inspect them:

```sh
aspect exec -- bazel build //e2e/rules_godot/smoke/android:app --config=android
bazel build //e2e/rules_godot/smoke/ios:static_app --config=official
aspect work inspect:mobile
```

The inspector resolves each artifact with its own Bazel configuration through
`cquery`; the module's `bazel-bin` symlink only names the most recent configuration.

### Cache reuse and invalidation

Analysis tests assert which inputs and arguments each action declares: a relevant edit is an
input of the action that must rerun, an unrelated one is not, and a configuration that must
not matter leaves actions unchanged. They are the `*_inputs_tests.bzl` and
`configuration_invariance_tests.bzl` suites of `godot/private/tests`,
`godot/platforms/private/tests`, `godot/extension/tests` and `godot/engine/private/tests`,
and run with the ruleset's other tests.
`//godot/private/tests:import_and_pack_outputs_are_reproducible_test` imports and exports a
project twice and compares the bytes. For the actions one change actually ran, compare the
execution logs of two invocations as the [verification
architecture](verification-architecture.md#verifications-without-precedent) describes.
