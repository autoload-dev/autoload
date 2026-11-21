# autoload_sentry

[Sentry for Godot](https://github.com/getsentry/sentry-godot) as the Bazel module
`autoload_sentry`, built with [rules_godot](https://github.com/autoload-dev/rules_godot): crash
and error reporting for Godot applications on macOS, Linux, Android and iOS.

| Add-on | Target | GDScript API |
| --- | --- | --- |
| Sentry | `@autoload_sentry//:sentry` | class `SentrySDK`, project settings `sentry/*` |

## Use in an application

`MODULE.bazel` (see the [add-ons README](../README.md) for depending on a commit until the
module is on BCR):

```starlark
bazel_dep(name = "autoload_sentry", version = "0.1.0")

maven = use_extension("@rules_jvm_external//:extensions.bzl", "maven")
maven.install(
    name = "maven",
    # The add-on adds the Sentry Android SDK to the application's Maven graph.
    known_contributing_modules = ["autoload_rules_godot", "autoload_sentry", "protobuf"],
    lock_file = "//:maven_install.json",
    ...
)
```

`BUILD.bazel`:

```starlark
godot_resources(
    name = "main",
    srcs = [...],
    deps = ["@autoload_sentry//:sentry"],
)
```

Configure Sentry with the `sentry/*` settings in `project.godot`, such as `options/dsn`:

```gdscript
SentrySDK.capture_message("Hello from Godot")
```

## Design

- The add-on is Sentry for Godot's prebuilt release (`third_party/sentry_godot.BUILD.bazel`),
  not a build from source. Its descriptor is replaced by a `godot_extension` that selects the
  release libraries for release builds and the debug libraries otherwise, as Sentry's own
  descriptor does.
- What Sentry's editor export plugin adds to a Gradle build is declared instead: the Godot
  plugin AAR and `io.sentry:sentry-android` in `platform_deps` on Android, and on iOS the
  `SentryObjC` framework, embedded beside the extension's framework without linking.
- The release's repository holds only filegroups and imports; the `godot_addon` in this
  module places its user-feedback UI.
- On Linux, native crash reports need Sentry's `crashpad_handler` beside the library, which
  the add-on does not place yet. Windows and the web are not wired yet, though the release
  has their libraries.

## Development

The application in [`examples/`](examples) builds the add-on for every platform against the
rules of this repository:

```sh
cd examples
bazel run //projects/demo:run -- --headless --quit-after 300
bazel build --config=android //projects/demo:app
bazel build --config=ios_sim //projects/demo:app
```
