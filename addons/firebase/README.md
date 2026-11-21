# autoload_firebase

Firebase add-ons of autoload-dev for Godot as the Bazel module `autoload_firebase`, built
with [rules_godot](https://github.com/autoload-dev/rules_godot). Applications depend on the
module and list the add-ons they use; the add-ons bring the Firebase SDKs.

Prototype status: Firebase Core, Google Analytics for Firebase and Cloud Firestore on Android
and iOS.

| Add-on | Target | GDScript API |
| --- | --- | --- |
| Firebase Core | `@autoload_firebase//core` | autoload `Firebase`, class `FirebaseCore` |
| Analytics | `@autoload_firebase//analytics` | class `FirebaseAnalytics` |
| Cloud Firestore | `@autoload_firebase//firestore` | classes `FirebaseFirestore`, `FirestoreTask` |

## Use in an application

`MODULE.bazel` (see the [add-ons README](../README.md) for depending on a commit until the
module is on BCR):

```starlark
bazel_dep(name = "autoload_firebase", version = "0.1.0")
bazel_dep(name = "rules_jvm_external", version = "7.2")  # or later

maven = use_extension("@rules_jvm_external//:extensions.bzl", "maven")
maven.install(
    name = "maven",
    # The add-ons add their Android libraries to the application's Maven graph.
    known_contributing_modules = ["autoload_firebase", "autoload_rules_godot", "protobuf"],
    lock_file = "//:maven_install.json",
    # rules_godot checks the graph against Godot's minimums, which need Gradle's resolution.
    resolver = "gradle",
    ...
)
```

`BUILD.bazel`:

```starlark
load("@autoload_firebase//config:defs.bzl", "firebase_config")

firebase_config(
    name = "firebase",
    application_id = "com.example.game",
    google_services_json = "google-services.json",
    google_service_info_plist = "GoogleService-Info.plist",
)

godot_resources(
    name = "main",
    srcs = [...],
    deps = ["@autoload_firebase//analytics"],
)

godot_app(
    name = "app",
    application_id = "com.example.game",
    pack = ":pack",
    # rules_godot rejects any non-empty platform_resources on desktop platforms.
    platform_resources = select({
        "@platforms//os:android": [":firebase"],
        "@platforms//os:ios": [":firebase"],
        "//conditions:default": [],
    }),
)
```

```gdscript
FirebaseAnalytics.log_event("level_start", {"level": 3})

# Firestore operations return a FirestoreTask; await its `completed` signal, then read
# `error` (empty on success) and `result`.
var task := FirebaseFirestore.set_document("players/alice", {"level": 3}, true)  # merge
await task.completed
task = FirebaseFirestore.get_document("players/alice")
await task.completed
print(task.result)  # {"level": 3, ...}, or null when the document does not exist
task = FirebaseFirestore.query("players", [["level", ">=", 2]], "level", true, 10)
await task.completed
for document in task.result:  # [{"id": ..., "path": ..., "data": {...}}, ...]
    print(document.id)
```

## Design

- Every add-on is a `godot_addon` whose C++ extension has one backend per platform: Android
  calls a Godot Android plugin (Java) that the extension carries in `platform_deps`, iOS calls
  the Firebase Apple SDK from Objective-C++, and the editor and desktop platforms take a
  backend that reports Firebase as unsupported. Editor builds never fetch an SDK.
- Analytics and Firestore need Core (`deps`), so its autoload initializes the default app
  first.
- Firestore is asynchronous: every operation returns a `FirestoreTask` whose `completed`
  signal is deferred, so it fires after the caller awaits it, even for a task that failed at
  once (a malformed path, an unsupported platform). Firestore values map to Godot as
  maps to dictionaries, lists to arrays, timestamps to seconds since the epoch, references
  to paths, geo points to dictionaries with latitude and longitude, and blobs to byte
  arrays; the same mapping applies on Android and iOS.
- Android dependencies come from Maven: the module's `maven.install(name = "maven")` merges
  into the root module's `@maven`, which pins the merged graph.
- iOS dependencies come from Firebase's binary distribution, `Firebase.zip`, as static
  XCFrameworks (`third_party/firebase_ios.BUILD.bazel`), not from SwiftPM.
- On iOS the Firebase SDK is one dynamic framework per product, as CocoaPods builds it with
  `use_frameworks! :linkage => :dynamic` (`ios/`): `FirebaseCore.framework` holds the core
  libraries (FirebaseCore, FirebaseCoreInternal, FirebaseInstallations, GoogleUtilities,
  FBLPromises, nanopb) and the application's one FIRApp; `FirebaseAnalytics.framework`
  holds the rest of Analytics and links `FirebaseCore`; `FirebaseFirestore.framework` holds
  Firestore with gRPC, BoringSSL and LevelDB, and its code compiles against the headers of
  FirebaseFirestoreInternal, which it holds too (`header_libraries`). Firebase publishes no dynamic
  frameworks, so `ios/` links them from the static XCFrameworks and copies their headers,
  modules and privacy bundles into them.
  The add-ons' extensions are rules_godot's default dynamic frameworks, each with its own
  godot-cpp: an Apple backend links its product's framework, and the extension lists the
  framework's `.bundle` import in `platform_deps`, through which the application embeds
  and signs it with the frameworks it links. Linked statically into each extension
  instead, every extension would hold its own copy of the SDK: duplicate Objective-C
  classes, and add-ons would not see the app Firebase Core configured.
- `firebase_config` (`config/`) replaces the google-services Gradle plugin: it turns
  google-services.json into Android string resources for the client of the application ID
  and checks GoogleService-Info.plist against the bundle identifier. The application passes
  it as `platform_resources` of its `godot_app`, not as `platform_deps`.
- The add-ons share one Firebase SDK and FIRApp, so they are one module with one version.
- C++ headers are included as `firebase/<add-on>/native/...` (`include_prefix`), so they
  never clash with headers of the application or of other modules.

## Development

`bazel test //...` in this directory runs the `firebase_config` tests. The Firestore part of
the example talks to the Firebase project of the placeholder configuration unless the project
setting `examples/firestore_emulator` names a Firestore emulator as `host:port`, such as
`10.0.2.2:8080` from the Android emulator. The application in
[`examples/`](examples) builds the add-ons for every platform. Both use the rules of this
repository, not a release.

## Open questions

- **Simulator runs.** The x86_64 Simulator build of the prebuilt 4.7 engine no longer runs on
  the iOS 27 Simulator. On a device, the example configures the default app once and starts
  Analytics; Firebase products register with FirebaseCore when their framework loads,
  which Godot does for all extensions before the `Firebase` autoload configures the app.
- **Embedding the frameworks an extension links.** rules_godot embeds only the frameworks of
  an extension's library and platform_deps, so each Firebase extension lists its product's
  `.bundle` import besides linking the framework. rules_godot could collect the frameworks
  of the extension's linked deps instead. It also builds each Firebase framework in several
  configurations of one application, once per path that reaches it.
- **SwiftPM instead of Firebase.zip.** rules_swift_package_manager 1.26.0's `swift_deps`
  honors `from_package` in non-root modules: with a Package.swift naming firebase-ios-sdk in
  this module, `examples` resolved and compiled `@swiftpkg_firebase_ios_sdk` without a
  Swift package setup of its own. Untested: two modules declaring the same package.
