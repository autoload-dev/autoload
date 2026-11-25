# Platform Paths

A small Godot application displays five storage locations supplied by operating-system APIs.
The reusable extension exposes the same typed API on macOS, Linux, iOS and Android:

```gdscript
var paths := PlatformPaths.new()
var result: PlatformPathResult = paths.resolve(PlatformPaths.DOCUMENTS)
if result.status == PlatformPathResult.OK:
    print(result.path)
else:
    print(result.message)
```

## Run the example

1. From the repository root, start the demo:

   ```sh
   bazel run //examples/addons/platform_paths:run
   ```

   The window shows your operating system and five rows with category, purpose, scope and
   an operating-system path or a readable reason why it is unavailable. Rows wrap and scroll for long paths.
2. Open the project, edit a label, and save:

   ```sh
   bazel run //examples/addons/platform_paths:edit
   ```

   A content-only change preserves unchanged native compilation and bindings.
3. Update the checkout metadata and run the example's checks:

   ```sh
   bazel run //examples/addons/platform_paths:update
   bazel run //e2e/addons/platform_paths:update
   bazel test //e2e/addons/platform_paths/results @autoload_platform_paths//platform_paths/native/backends/linux/tests //e2e/addons/platform_paths:update.test
   bazel test //e2e/addons/platform_paths/locations //examples/addons/platform_paths/tests:exported //examples/addons/platform_paths:update.test //e2e/addons/platform_paths:update.test
   ```

   The independent native policy test lives in `native/backends/linux/tests/`. The separate
   test project in `e2e/addons/platform_paths/` owns the suites of the result objects and the
   application identity in `results/`, and the suites and fixtures of real operating-system
   locations in `locations/`; the demo's `tests/` owns the exported-demo check.
   The location checks resolve actual
   locations. Linux tests supply their own XDG configuration;
   unavailable user directories in your ordinary environment remain visible as unavailable.
   The `exported` test runs the demo PCK through its ordinary startup.

4. Export the production content as a PCK:

   ```sh
   bazel build //examples/addons/platform_paths:pack
   ```

   The output is `bazel-bin/examples/addons/platform_paths/pack.pck`.
   It packages the demo's production content without test suites or their frameworks.
   The PCK does not include the Godot engine; use the application targets below to
   package content together with its runtime.
5. Build a desktop application:

   ```sh
   bazel build //examples/addons/platform_paths:app
   ```

   On macOS, sign the application ad hoc:

   ```sh
   bazel build //examples/addons/platform_paths:app --@autoload_rules_godot//godot:macos_signing=adhoc
   ```

   Launch the output reported by Bazel to see the same five rows. macOS signing is local ad hoc signing.
   Add `--@autoload_rules_godot//godot:variant=debug` to build the debug variant: the pack exports
   as debug and the desktop and iOS templates follow. The app's Android shell library, the
   pinned Maven AAR, is release-only, so its Android build requires the release variant.

Bazel runs use isolated runtime directories. Their paths can differ from those of an
installed application. A successful lookup describes a location; it does not guarantee
that the directory exists or is writable. Temporary and cache data is disposable, and
both categories may resolve to the same directory. The demo does not write sample files,
request broad storage access, use the network or save paths between launches.

## Reuse the add-on

`//platform_paths` is an add-on of only its extension. List it in the `deps` of the
`godot_resources` whose scripts use it, or in your `godot_project`'s `deps` when no content
uses it. That target carries the selected backend, Foundation linkage and internal Android
plugin metadata/Java dependencies. Your project uses only the common extension API;
it does not copy the scene, test framework or platform library lists.

On desktop, configure your own stable identity in `project.godot`:

```ini
[platform_paths]
application_id="org.example.myapp"
```

Use lowercase letters/digits separated by single dots or hyphens, starting with a letter.
This scopes macOS/Linux support and cache directories to your application rather than the
Godot editor executable. Invalid identity affects only those two lookups. Mobile uses the
running application's actual container/context.

`PlatformPathResult` is an immutable RefCounted snapshot with getter-only `category`,
`status`, `path`, `message` and `scope` properties. Keep it through normal Godot references.
Statuses are `OK`, `UNAVAILABLE`, `INTEGRATION_UNAVAILABLE` and `ERROR`; scopes are `NONE`,
`APPLICATION`, `USER_DOMAIN` and `TEMPORARY`. Failed results have an empty path and a reason.
New calls resolve current state without changing earlier results. Call on Godot's main
thread after engine initialization.

## Operating-system facilities and scope

| Category | macOS | iOS | Android | Linux |
|---|---|---|---|---|
| Temporary | NSTemporaryDirectory | NSTemporaryDirectory | Context.getCacheDir | Absolute TMPDIR or /tmp |
| Application Support | Foundation Application Support + project ID | Container Application Support | Context.getFilesDir | XDG_DATA_HOME or HOME/.local/share + project ID |
| Application Cache | Foundation Caches + project ID | Container Caches | Context.getCacheDir | XDG_CACHE_HOME or HOME/.cache + project ID |
| Documents | Foundation user-domain Documents | Container Documents | Context.getDir("documents", MODE_PRIVATE) | XDG_DOCUMENTS_DIR in user-dirs.dirs |
| Downloads | Foundation user-domain Downloads | Container Downloads | Context.getExternalFilesDir(DIRECTORY_DOWNLOADS) | XDG_DOWNLOAD_DIR in user-dirs.dirs |

Apple uses a shared Objective-C++ Foundation backend. Linux reads the process environment and
XDG configuration on every call, without a shell or helper executable; missing user-dir
configuration is unavailable, while malformed relevant configuration is an error. Absolute
XDG overrides take precedence; relative overrides use the documented HOME-based defaults.
A configured HOME value is preserved. Android uses a small internal Godot Android plugin,
called by the extension's C++ code. Godot registers it automatically from v2 metadata.
macOS/iOS call the operating system's APIs directly, without Godot iOS plugin hooks.

Documents and Downloads on mobile are application locations. Resolving them grants no
access to shared public folders. Desktop user-domain locations remain subject to operating
system sandbox restrictions. Android external Downloads can be unavailable independently
of the other categories.

## Mobile builds

Follow [platform setup](../../rules_godot/docs/public/platforms.md) for the Android SDK/NDK, Java 21 and Xcode.
From the repository root:

```sh
bazel build //examples/addons/platform_paths:app --config=android
bazel build //examples/addons/platform_paths:app --config=android --config=aab
bazel build //examples/addons/platform_paths:app --config=simulator
```

`--config=simulator` builds for the arm64 Simulator of Apple silicon Macs;
`--config=official` builds for the x86_64 Simulator of the official templates.

Replace `--config=android` with `--config=multi_abi` to request the Android distribution
CPUs; [export platforms](../../rules_godot/docs/public/platforms.md#export-platforms) explain
CPU selection.
