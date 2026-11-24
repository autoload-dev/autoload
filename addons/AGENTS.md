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

The conventions check enforces it (RG015, [the catalogue](../rules_godot/docs/public/conventions.md)):

- `MODULE.bazel`, `README.md`, `REPO.bazel`, `BUILD.bazel`, `.gitignore`, `.gitattributes`, `.bazelversion`.
- `.bazelrc` imports [module.bazelrc](module.bazelrc) and `examples/.bazelrc` imports
  [examples.bazelrc](examples.bazelrc); each adds only its BuildBuddy tag. Settings for all
  modules go in those two files.
- `addon.pkl` amends the schema [tools/addons/Addon.pkl](../tools/addons/Addon.pkl), which
  documents what a module declares: the lanes that verify it, the desktop systems of its desktop lane
  and its test operations, such as `lanes = List("desktop")` and `desktops = List("macos")`. A module
  without the `android` and `ios` lanes builds no application: its examples have no `app`,
  no Android SDK and no Maven graph. The lanes' work, the lanes and the conventions read it;
  nothing outside the module lists the module.
- `.bcr/addons/<module>/`, outside the module: the templates publish-to-bcr reads for a
  release, `metadata.template.json`, `source.template.json` and `presubmit.yml`, the
  registry's checks of a release. Edit them there like any other file of the module.
- `examples/`: an independent root module with the module's example applications in
  `projects/<name>/`, each with the targets `edit`, `pack` and, for a module that builds
  applications, `app`. It consumes the module
  like an external application (`local_path_override` to `..`) and the rules of this
  repository (`local_path_override` to `../../../rules_godot`), so an add-on always builds
  against the rules it is changed with.
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
- Android dependencies come from Maven: a module's `maven.install` merges into the
  examples' `@maven`, which lists the module in `known_contributing_modules`. After changing
  artifacts, repin from the module's `examples/` with `REPIN=1 bazel run @maven//:pin`.
- Never commit or print secrets, signing material or real service configurations; local
  provisioning profiles stay in the gitignored `<module>/examples/signing/`.

# Lanes

The same commands verify every module, from its `examples/` (`tools/addons/lanes.py`), as
the lanes' work (`tools/ci/work.py`), which provisions the Android SDK first:

```sh
aspect work desktop:addon:<module>      # module tests and example targets but apps
aspect work android:addon:<module>   # each example project's app for Android
aspect work ios:addon:<module>       # each example project's app for the iOS Simulator
```

`android` and `ios` also run the example projects' tests tagged with the lane's name, such as
an `ios_app_test` of the app (`rules_godot/tests/AGENTS.md`, "Artifact test rules"); the tag
`manual` keeps them out of `desktop`.

`desktop` runs `bazel test` over `@autoload_<module>//...` and all of `examples/`, so tests in
the module or its examples need no registration. Tests that need more than the module's own
dependencies, such as Python, live in `examples/tests/`, where the examples' module declares
what they use; the release archive leaves them out with the examples. CI runs every module's
lanes on every run; `aspect work <lane>:addon-template` checks the template the same way.

For iOS device runs, add `--define=ios_signing=local` with a profile in
`examples/signing/`, install with `xcrun devicectl` and check the log for crashes.
