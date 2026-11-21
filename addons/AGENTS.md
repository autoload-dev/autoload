# Add-ons

Each directory here is a Bazel module of its own (`firebase/` is `autoload_firebase`), which
applications consume like any other module; the [README](README.md) lists them. A module
has its own `MODULE.bazel`, README, version and release tags `<module>-v<version>`.

- A module's labels are module-relative, such as `//core` and `@autoload_firebase//analytics`.
- `<module>/examples/` is an independent root module with the module's example applications
  in `projects/<name>/`.
  It consumes the module like an external application (`local_path_override` to `..`) and the
  rules of this repository (`local_path_override` to `../../..`), so an add-on always builds
  against the rules it is changed with. The module's own `.bazelrc` does the same for builds
  in the module directory.
- A new add-on gets its own module directory with its own `MODULE.bazel`, README and
  `examples/`, unless it must be versioned with an existing group, as a new Firebase product
  goes into `firebase/`. Add it to the README's table.
- Never commit or print secrets, signing material or real Firebase configurations: the
  examples' Firebase files are placeholders, and local provisioning profiles stay in the
  gitignored `<module>/examples/signing/`.

# Add-on layout

- An add-on is a `godot_addon` whose `godot_cc_extension` selects one backend per platform:
  `backends/android` (C++ over JNI to a Godot Android plugin in Java, carried in
  `platform_deps`), `backends/apple` (Objective-C++ against the Apple SDK) and
  `backends/unsupported` for the editor and desktop platforms. Editor builds never fetch an SDK.
- Header libraries of `autoload_firebase` set `include_prefix = "firebase"` and
  `strip_include_prefix = "/"`, so includes read `firebase/<add-on>/native/...`.
- Give every extension target a name unique across all add-ons and applications: on iOS the
  target name becomes the framework or library name, and those share one directory.
- Extensions keep rules_godot's default dynamic framework on iOS, with their own godot-cpp.
  Firebase's Apple SDK is one dynamic framework per product (`firebase/ios`): a Firebase
  backend links its product's framework and its extension lists the framework's `.bundle`
  import in `platform_deps`, so the application holds one SDK and one FIRApp
  (`firebase/README.md`, "Design"). A new product gets its own `firebase_framework` with
  `frameworks = [":core"]`.
- Android dependencies come from Maven: each module's `maven.install` merges into the root
  module's `@maven`, which lists the module in `known_contributing_modules`. After changing
  artifacts, repin from the module's `examples/` with `REPIN=1 bazel run @maven//:pin`.

# Checks

From a module's `examples/`, after changes that can affect them, for example in
`firebase/examples/`:

```sh
bazel build //projects/analytics:edit //projects/analytics:pack   # editor and desktop
bazel build --config=android //projects/analytics:app
bazel build --config=ios_sim //projects/analytics:app
bazel build --config=ios //projects/analytics:app   # needs signing/firebase.mobileprovision
                                                    # and --define=ios_signing=local
```

In the module directory: `bazel test //...`, e.g. `cd firebase && bazel test //...` (the
`firebase_config` tests).

The CodeScene tools review C++, Objective-C++, Java and Python. They reject Bazel files,
GDScript and Markdown; say so instead of reporting a pass.
