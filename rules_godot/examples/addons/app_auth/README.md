# AppAuth

A Godot add-on that logs a player in with OpenID Connect through [AppAuth](https://appauth.io):
AppAuth for Android from the module's Maven graph, AppAuth for iOS and macOS from its Swift
package, and one GDScript API on every operating system. The demo application logs in against
Duende's public demo identity provider and shows who signed in.

```gdscript
var login: AppAuthLogin = AppAuth.login(
    "https://demo.duendesoftware.com",
    "interactive.public",
    PackedStringArray(["openid", "profile", "email", "offline_access"]),
)
var result: AppAuthResult = await login.finished
if result.status == AppAuthResult.OK:
    print(result.claims.get("name", ""))
else:
    print(result.message)
```

The example answers one question: how does an add-on declare a real SDK that comes from a
package manager, with its transitive libraries, resources and manifest entries, so that every
application shipping a pack that contains the add-on links and packages it without repeating it?

| Part | Role |
|---|---|
| `//addons/app_auth` | The extension, an add-on by itself, that the resources using it list in `deps`: `AppAuth`, `AppAuthLogin`, `AppAuthResult` |
| `native/` | Configuration validation, ID-token claims, the backend interface the operating systems implement |
| `native/backends/android/` | A Godot Android plugin with AppAuth for Android; the extension's Android platform library |
| `native/backends/apple/` | Objective-C++ with AppAuth for iOS and macOS, linked into the extension library |
| `native/backends/unsupported/` | Linux and the editor: the add-on loads and every login ends with `UNSUPPORTED` |
| `demo/` | The application with the login button and the result screen |
| `tests/` | The GdUnit contract suite |

The pattern fits an SDK published as an Android library on Maven, as a Swift package, or both,
that a game reaches through one script API. It does not fit SDKs that ship dynamic Apple
XCFrameworks or JNI libraries inside AARs, which this example does not exercise, and it stops
at login: tokens stay in memory, and storage, refresh and logout are the game's business.

## Supported operating systems

| Operating system | Login |
|---|---|
| Android | Yes |
| iOS Simulator | Yes |
| macOS | Yes |
| Linux | No: every login ends with `UNSUPPORTED` |

On Linux, `bazel build //addons/app_auth/demo:app` from `rules_godot/examples/` builds the
bundle and archive without fetching any AppAuth artifact.

## Run the demo

1. Start the demo from source:

   ```sh
   cd rules_godot/examples
   bazel run //addons/app_auth/demo:run
   ```

   On macOS the window shows the default redirect URI and a **Log in** button. On Linux the
   button is disabled and the window says that login is unavailable on this operating system.
2. Build and install the application for a device, and log in with the demo user named on
   [Duende's demo page](https://demo.duendesoftware.com):
   - Android, on a connected device or running emulator:

     ```sh
     bazel build //addons/app_auth/demo:app --config=android
     adb install -r bazel-bin/addons/app_auth/demo/app.android_apk/app/app.apk
     ```

   - iOS Simulator, on a booted Simulator:

     ```sh
     bazel build //addons/app_auth/demo:app --config=simulator
     xcrun simctl install booted bazel-bin/addons/app_auth/demo/app.ios/app.app
     xcrun simctl launch booted org.example.appauth
     ```

   - macOS:

     ```sh
     bazel build //addons/app_auth/demo:app --platforms=@autoload_rules_godot//godot/platforms:macos_arm64 --@autoload_rules_godot//godot:macos_signing=adhoc
     open bazel-bin/addons/app_auth/demo/app.macos_signed/app.app
     ```

   Tap **Log in**. The login page opens in the system browser on Android and in the system
   authentication sheet on iOS and macOS. After signing in, the result screen shows the user's
   name, or the subject identifier when the ID token has no `name` claim, as with Duende's demo
   user, the granted scopes, the access token's expiry and the first eight characters of the
   access token; the demo never shows or logs a whole token.
3. Check the other outcomes the same way. Each is a manual check, because it needs a login the
   provider holds open; the desktop tests never start one:

   | Action | Shown |
   |---|---|
   | Close the browser tab or cancel the sheet | **Cancelled** |
   | Tap **Log in** again while a login is open | **Busy**: the first login continues |
   | Log in with the network disabled | **Network error** |

4. Run the add-on's checks: the native unit tests, the GdUnit contract suite and the
   exported demo, none of which uses the network:

   ```sh
   bazel test --build_tests_only //addons/app_auth/...
   ```


## Use the add-on

Declare `//addons/app_auth` in the `deps` of your `godot_project` or `godot_resources`. Every
`godot_app` of that project links and packages AppAuth for its operating system; the application
lists no AppAuth or AndroidX library itself.

On Android, give AppAuth's redirect activity its scheme on the application, as the demo does
with one constant for the application ID and the scheme:

```starlark
godot_app(
    name = "app",
    android_manifest_values = {"appAuthRedirectScheme": "org.example.appauth"},
    application_id = "org.example.appauth",
    pack = ":pack",
)
```

`android_manifest_values` fills the `${appAuthRedirectScheme}` placeholder of AppAuth's
manifest and of the add-on's plugin manifest; the
[platform guide](../../../docs/public/platforms.md#add-on-platform-libraries) describes the
attribute. Without the value, the Android build fails in the manifest merge naming the
placeholder.

The default redirect URI is `<scheme>:/oauth2redirect`: on Android the scheme is the manifest
value, on iOS and macOS the bundle identifier. A bundle identifier with uppercase letters or
other characters outside RFC 3986's scheme syntax ends the login with `INVALID_CONFIGURATION`.
Pass `redirect_uri` to `login` when your provider registers a different one or the default
scheme is invalid. The authentication session on iOS and macOS returns the redirect to the app
in-process, so the scheme needs no URL type in the Info.plist.

| Class | Member | Contract |
|---|---|---|
| `AppAuth` | `static login(issuer: String, client_id: String, scopes: PackedStringArray, redirect_uri: String = "") -> AppAuthLogin` | Never null; never blocks. Validates the configuration first, then rejects a login while another is pending, then starts the backend |
| `AppAuth` | `static default_redirect_uri() -> String` | `<scheme>:/oauth2redirect`, or empty where login is unsupported or the scheme is unknown |
| `AppAuth` | `static is_supported() -> bool` | `true` on Android, iOS and macOS |
| `AppAuthLogin` | signal `finished(result: AppAuthResult)` | Emitted exactly once, on a later frame, so you can connect or `await` after `login` returns |
| `AppAuthLogin` | `is_pending() -> bool` | `true` until `finished` is emitted |
| `AppAuthResult` | `status`, `message` | Always; `message` is empty for `OK` and a readable reason otherwise |
| `AppAuthResult` | `provider_error` | The provider's `error` code for `PROVIDER_ERROR` |
| `AppAuthResult` | `access_token`, `id_token`, `claims`, `scopes`, `expires_at`, `has_refresh_token` | For `OK`: the tokens, the ID token's claims, the granted scopes (the requested ones if the provider omits them), the expiry as Unix seconds (`0` if none) and whether a refresh token was issued; the refresh token itself is not exposed |

| Status | Meaning |
|---|---|
| `OK` | Tokens received |
| `CANCELLED` | The user closed the login page or sheet |
| `INVALID_CONFIGURATION` | A field is invalid; the message names it; the provider was not contacted |
| `BUSY` | Another login of this process is pending; that login continues |
| `NETWORK_ERROR` | Discovery, authorization or the token request could not reach the provider |
| `PROVIDER_ERROR` | The provider returned an OAuth error |
| `UNSUPPORTED` | No login backend on this operating system |
| `ERROR` | Any other failure, including a malformed backend result |

The identity provider's endpoints come from the issuer's OpenID Connect discovery document; the
authorization code flow uses PKCE. The provider must offer a public client, since the
application holds no secret.

## Where the SDK is declared

Changing the AppAuth version on one operating system means changing one declaration and
refreshing one lock file:

| SDK | Declaration | Lock file and refresh |
|---|---|---|
| AppAuth for Android 0.11.1 | `net.openid:appauth` in the `maven.install` artifacts of `examples/MODULE.bazel` | `examples/maven_install.json`: `REPIN=1 bazel run @maven//:pin` |
| AppAuth for iOS and macOS 3.0.0 | `examples/Package.swift` | `examples/Package.resolved`: `swift package resolve` |

`examples/MODULE.bazel.lock` records the hash of `Package.resolved` (its `FILE:@@//Package.resolved`
entry), and the next Bazel command after `swift package resolve` rewrites it, so a Swift refresh
commits both files. The Maven lock has no such entry.

## Limits

- Custom redirect schemes on Android are not exclusive: another installed app can claim the
  same scheme. The demo derives its scheme from its application ID.
- No DPoP: Duende's `native.dpop` client cannot be used; the demo uses `interactive.public`.
- Tokens are not stored, refreshed or revoked; there is no logout.
- AppAuth's privacy manifest resource bundles reach iOS applications but not macOS
  applications, which take no Apple resources from extensions or platform libraries.
- The editor itself has no login: its extension library uses the unsupported backend, so a
  login started from an editor plugin or tool script ends with `UNSUPPORTED`. A source run
  (`bazel run //addons/app_auth/demo:run`) logs in on macOS.

## Work on the add-on

```sh
cd rules_godot/examples
bazel run //addons/app_auth/demo:edit     # open the demo in the editor
bazel run //addons/app_auth/tests:edit    # open the test project
bazel run //addons/app_auth/demo:update   # write UIDs and node IDs into the checkout
bazel run //addons/app_auth/tests:update
bazel test //addons/app_auth/native/tests # only validation and ID-token decoding
bazel test //addons/app_auth/tests/unit   # only the GdUnit contract suite
```

The parts table at the top maps the repository. The
[extension guide](../../../docs/public/gdextension.md#platform-libraries) and the
[platform guide](../../../docs/public/platforms.md#add-on-platform-libraries) own the rules for
platform libraries; [project layout](../../../docs/public/project-layout.md) owns where demo and
test projects live.
