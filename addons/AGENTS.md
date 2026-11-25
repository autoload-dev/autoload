# Add-ons

Each directory here is a Bazel module of its own, `addons/<module>` named
`autoload_<module>`, which applications consume like any other module. A module has its own
`MODULE.bazel`, README, version and release tags `<module>-v<version>`.

Create modules and add-ons with the generator, never by copying another module:

```sh
bazel run //tools/addons:new -- <module>                   # a module with one add-on, <module>
bazel run //tools/addons:new -- <module> --addon <addon>   # one more add-on in a module
```

It writes [tools/addons/template](../tools/addons/template), which builds in every lane from
the start, and a new module's registry templates in `.bcr/addons/<module>/`. From then on
the module owns those files: nothing regenerates them. Improve the template, not one module,
when a pattern should hold for all of them. A new add-on gets its own module, unless it must
be versioned with others, such as products that share one SDK.

# Module layout

The conventions check enforces it (RG015, [conventions.md](../docs/internal/conventions.md)):

- `MODULE.bazel`, `README.md`, `REPO.bazel`, `BUILD.bazel`, `.gitignore`, `.gitattributes`, `.bazelversion`.
- `.bazelrc` imports [module.bazelrc](module.bazelrc) and adds only its BuildBuddy tag.
  Settings for all modules go in that file.
- `addon.pkl` amends the schema [tools/addons/Addon.pkl](../tools/addons/Addon.pkl), which
  documents what a module declares: the lanes that verify it, the desktop systems of its desktop lane
  and its test operations, such as `lanes = List("desktop")` and `desktops = List("macos")`. A module
  without the `android` and `ios` lanes builds no application: its examples have no `app`. The lanes' work, the lanes and the conventions read it;
  nothing outside the module lists the module.
- `.bcr/addons/<module>/`, outside the module: the templates publish-to-bcr reads for a
  release, `metadata.template.json`, `source.template.json` and `presubmit.yml`, the
  registry's checks of a release. Edit them there like any other file of the module.
- [`examples/addons/<module>/`](../examples/AGENTS.md) in the repository's root module, outside
  the module: its example application, the directory itself or one per scenario in
  subdirectories, each with the targets `edit`,
  `pack` and, for a module that builds applications, `app`. The root module consumes the
  module like an external application, through a `local_path_override` in
  `addons.MODULE.bazel`, which `aspect generate` and the generator write from `addons/`
  (`tools/addons/declarations.py`), and the rules of this repository the same way, so an add-on always builds against
  the rules it is changed with.
- Every add-on lives in a directory of its own, `<module>/<addon>/`, never in the module's
  root; the root holds only the module's files, `third_party/` with the build files of
  pinned archives, `tests/` and packages several add-ons share, such as Firebase's `config/`.
- Each add-on `<module>/<addon>/` is a `godot_addon` whose `godot_cc_extension` selects one
  backend per platform below `native/`, which holds the platform-independent API:
  `native/backends/android` (C++ over JNI to a Godot Android plugin in Java, carried in
  `platform_deps`), `native/backends/apple` (Objective-C++ against the Apple SDK) and
  `native/backends/unsupported` for the editor and desktop platforms. Editor builds never
  fetch an SDK.
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

# Lanes

The same commands verify every module, from the repository root over its
`examples/addons/<module>/` (`tools/addons/lanes.py`), as the lanes' work
(`tools/ci/work.py`), which provisions the Android SDK first. A lane runs every module that
names it with one Bazel command, `<lane>:addons`; one module alone runs as
`<lane>:addon:<module>`:

```sh
aspect work desktop:addon:<module>      # module tests and example targets but apps
aspect work android:addon:<module>   # each example project's app for Android
aspect work ios:addon:<module>       # each example project's app for the iOS Simulator
aspect work desktop:addons              # every module's desktop lane at once
```

`android` and `ios` also run the example projects' tests tagged with the lane's name, such as
an `ios_app_test` of the app (`e2e/rules_godot/AGENTS.md`, "Artifact test rules"); the tag
`manual` keeps them out of `desktop`.

`desktop` runs `bazel test` over `@autoload_<module>//...`, all of
`examples/addons/<module>/` and `e2e/addons/<module>/`, so no test needs registration. Where a
test lives follows what it checks:

- Native unit tests beside the code they test, such as `<addon>/native/backends/linux/tests/`.
- White-box tests of the module's own machinery, such as `gdunit_test` or a third-party
  build, in the module's `tests/`. They use only the module's dependencies, which therefore
  include what the tests need, such as rules_python; the release archive leaves `tests/` out.
- End-to-end tests that use an add-on as an application does, such as GdUnit suites of its
  GDScript API, in `e2e/addons/<module>/`, where the root module declares what they use. CI runs every module's
[lanes](../docs/internal/verification-platforms.md#lanes-and-execution);
`aspect work <lane>:addon-template` checks the template the same way
(`tools/addons/selftest.py`).

For iOS device runs, add `--define=ios_signing=local` with a profile in
`examples/addons/<module>/signing/`, install with `xcrun devicectl` and check the log for crashes.
