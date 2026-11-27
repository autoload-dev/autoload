# Add-ons

Each directory here is a Bazel module of its own, `addons/<module>` named
`autoload_<module>`, which applications consume like any other module. A module has its own
`MODULE.bazel`, README, version and release tags `autoload_<module>-v<version>`.

Create modules and add-ons with the generator, never by copying another module:

```sh
bazel run //tools/addons:new -- <module>                   # a module with one add-on, <module>
bazel run //tools/addons:new -- <module> --addon <addon>   # one more add-on in a module
```

It writes [tools/addons/template](../tools/addons/template), which builds and tests in both
host jobs from the start, and a new module's registry templates in `.bcr/addons/<module>/`.
From then on the module owns those files, but for its shared files, the settings every module
keeps as the generator writes them, such as `.bazelrc`, `.gitattributes` and the registry
templates (shared-module-files-as-generated,
[conventions.md](../docs/internal/conventions.md)): `aspect generate` writes them again for
every module. Improve the template, not one module, when a pattern should hold for all of them.
A new add-on gets its own module, unless it must be versioned with others, such as products
that share one SDK.

# Module layout

The conventions check enforces it (the add-on module rules of
[conventions.md](../docs/internal/conventions.md)):

- `MODULE.bazel`, `README.md`, `REPO.bazel`, `BUILD.bazel`, `.gitignore`, `.gitattributes`,
  `.bazelversion`.
- `.bazelrc` imports [module.bazelrc](module.bazelrc) and adds only its BuildBuddy tag.
  Settings for all modules go in that file.
- Package metadata, which SBOM and license tools read from an application's build: the
  shared `REPO.bazel` gives every target of the module the `package_metadata` of its shared
  root `BUILD.bazel`, the module's PURL and license. The build file of a third-party archive in
  `third_party/` declares the archive's own: a PURL built with `purl.builder()`, whose version
  follows the archive's URL, and the license of the project with its text from the archive,
  not the licenses of the components a release bundles. `e2e/addons/sqlite/sbom/` checks that
  an SBOM of a pack names a module and the registry module it builds in.
- `.bcr/addons/<module>/`, outside the module: the templates publish-to-bcr reads for a
  release, `metadata.template.json`, `source.template.json` and `presubmit.yml`, the
  registry's checks of a release. They are shared files: change them in the template.
- `bcr/smoke/`, the registry test module the presubmit runs: a consumer of the module's add-ons
  that registers the official engine, as applications do (registry-test-module-in-bcr). Keep it using
  the module's public targets. In this repository it uses the rules beside it through
  `addons/bcr.bazelrc`, as CI's macOS job runs it on every run;
  `python3 -m tools.ci.release_archive addons/<module>` runs it from the module's release
  archive, as the registry does.
- [`examples/addons/<module>/`](../examples/AGENTS.md) in the repository's root module, outside
  the module: its example application, the directory itself or one per scenario in
  subdirectories, each with the targets `edit`, `pack` and, when it builds an application
  with Android and iOS releases, `app`. A module whose add-ons ship in no application, such
  as gdunit, has examples without `app`. The root module consumes the
  module like an external application, through a `local_path_override` in
  `addons.MODULE.bazel`, and the rules of this repository the same way, so an add-on always
  builds against the rules it is changed with. `aspect generate` and the generator write the
  segment from `addons/` (`tools/addons/declarations.py`), together with `addons.bzl`, the
  modules' repositories, whose `module_files` the setup checks' tests read, and
  `root.targets`, the root module's target patterns, which the development verbs pass to
  Bazel. The root ignores `addons/`, so no Bazel target can derive or diff-check the files:
  Bazel itself rejects a stale segment, `tools/setup/checkout.py` a list that misses a
  module, and `//tools/addons:root_targets_test` target patterns that differ from the list.
- Every add-on lives in a directory of its own, `<module>/<addon>/`, never in the module's
  root; the root holds only the module's files,
  [`third_party/`](../docs/internal/glossary.md#modules-and-tests), `tests/`, `bcr/` and
  packages that other packages load by label, such as Firebase's `config/`, which its
  examples load as `@autoload_firebase//config`.
- Each add-on `<module>/<addon>/` is a `godot_addon` whose `godot_cc_extension` selects one
  backend per platform below `native/`, which holds the platform-independent API:
  `native/backends/android` (C++ over JNI to a Godot Android plugin in Java, carried in
  `platform_deps`), `native/backends/apple` (Objective-C++ against the Apple SDK) and
  `native/backends/unsupported` for the editor and desktop platforms. Editor builds never
  fetch an SDK.
- A Java plugin compiles against Godot's classes through
  `@autoload_rules_godot//godot/platforms:android_plugin_api`, the shell library of the engine
  the application ships, so a module registers no engine of its own.
- Header libraries set `include_prefix = "<module>"` and `strip_include_prefix = "/"`, so
  includes read `<module>/<addon>/native/...`.
- Every extension target has a name unique across all add-ons and applications: on iOS the
  target name becomes the framework or library name, and those share one directory. The
  generator names it `<module>_<addon>`, or `<module>_extension` for an add-on named like
  its module.
- Android dependencies come from Maven: a module's `maven.install` merges into the root
  module's `@maven`, pinned in `third_party/maven/`, which lists the module in
  `known_contributing_modules`. After changing
  artifacts, repin from the repository root with `REPIN=1 bazel run @maven//:pin`.
- Never commit or print secrets, signing material or real service configurations; local
  provisioning profiles stay in the gitignored `examples/addons/<module>/signing/`.

# Tests and CI

The same tests verify every module, from the repository root: CI's host jobs
(`aspect ci <host>`) run `bazel test --config=ci-<host>` over `//...` and every
`@autoload_<module>//...`, which covers each module's own tests, its
`examples/addons/<module>/` and `e2e/addons/<module>/`, so no test needs registration. They
provision the Android SDK first. To run one module alone:

```sh
bazel test --config=all -- @autoload_<module>//... //examples/addons/<module>/... //e2e/addons/<module>/...  # leave out e2e/ if the module has none
bazel test --test_tag_filters=android //examples/addons/<module>/...   # the Android release builds
bazel test --test_tag_filters=ios //examples/addons/<module>/...       # the iOS Simulator release builds
```

Where `e2e/addons/<module>/` is a project itself, as for every module but gdunit, its
`edit` opens it in the editor and its `update` writes its UIDs and node IDs into the
checkout:

```sh
bazel run //e2e/addons/<module>:edit
bazel run //e2e/addons/<module>:update
```

The module's README names only the example's commands
(no-end-to-end-tests-in-public-documentation, [conventions.md](../docs/internal/conventions.md)).

Each example project with an `app` declares its release builds, `android_release`
and `ios_release` ([examples/releases.bzl](../examples/releases.bzl)), which carry their
configuration; their `<name>.build_test` is tagged `android` or `ios`, so only the Linux or the
macOS job runs it. A test of a mobile application, such as an `ios_app_test` of `ios_release`
(`e2e/rules_godot/AGENTS.md`, "Artifact test rules"), carries its tag too. Where a
test lives follows how it runs, by the
[add-on module tests](../docs/internal/verification-architecture.md#add-on-module-tests).
For a module, that means:

- Unit tests sit beside their unit, such as `<addon>/native/backends/linux/tests/`, or in
  `tests/<unit>/` for a module-wide unit such as a third-party build. CI builds the
  module from the root module, where its development dependencies are not active, so they
  use only the module's regular dependencies.
- End-to-end tests share one test project, `e2e/addons/<module>/` itself, with the add-ons
  it depends on, such as Firestore with Firebase Core. A scenario or configuration variant
  that needs other settings gets a project of its own in a subdirectory. Suites go into
  packages named after their topic, such as `e2e/addons/sqlite/database/`; conditions such
  as a host or a device are tags, not directories.
- Demo tests live in `examples/addons/<module>/tests/`, never in the project's root package.

The root module lints the modules' Python too, in `bazel build --config=lint`, so every `py_binary`,
`py_library` and `py_test` of a module carries the tag `lint-genfiles`, or the lint fails. Findings name
the files as `external/autoload_<module>+/...`; Ruff's fixes apply only through
`aspect lint --fix` in the module's own directory. The modules' GDScript, Markdown and shell
scripts need no targets for their lint: the
[file lint](../docs/internal/verification-recipes.md#the-file-lint) at the repository root
covers them.

Every project is named like its directory (project-named-after-directory), so
`//examples/addons/<module>` and `//e2e/addons/<module>` name the projects. CI runs every
module's tests in its
[host jobs](../docs/internal/verification-platforms.md#host-jobs-and-execution);
`aspect work addon-template` checks the template the same way (`tools/addons/selftest.py`).

For iOS device runs, add `--define=ios_signing=local` with a profile in
`examples/addons/<module>/signing/`, install with `xcrun devicectl` and check the log for crashes.
