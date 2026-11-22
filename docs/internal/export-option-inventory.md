# Export option inventory and internal Android splash dependency

## Scope and evidence

Research snapshot: 2026-11-02. The experiment used the official standard macOS Godot
`4.7.2.stable.official.ed1daf0bf` editor with a minimal project and a temporary export
plugin. It exported a disposable PCK separately with the Linux, macOS, Android and iOS
exporters. All four commands completed and wrote the inventory. No Android SDK, native
compilation, device, signing or Store validation was involved.

[export-options-4.7.2.json](export-options-4.7.2.json) enumerates 701 platform/key pairs
with their runtime Godot types and their reviewed disposition. It is the dated per-key
record, not runtime policy: the rules act on the engine profile's rejected-keys table in
[profiles.bzl](../../rules_godot/godot/private/engine/profiles.bzl) and on the live probe's
registration and types. A row records an option, not a public attribute. The file stores
no option values, credentials or copied default schema. Its owner IDs resolve to the
evidence and limitations below.

| Exporter | Consumed by rules_godot | Delegated to Godot | Bazel-owned | Unsupported | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Linux | 0 | 2 | 5 | 8 | 15 |
| macOS | 177 | 0 | 34 | 26 | 237 |
| Android | 183 | 0 | 18 | 5 | 206 |
| iOS | 218 | 0 | 17 | 8 | 243 |

`consumed` means a concrete host metadata/image consumer was identified. It does not certify every value, native runtime effect or Apple
submission. `delegated` identifies a concrete PCK-export mechanism. `bazel-owned` identifies the authoritative native owner of the supported equivalent.
It is not a blanket rejection rule: the native-value contract permits equal redundant
non-Gradle scalar values, supported standalone-pack metadata and the empty-identifier
macOS fallback. Other replaced controls are rejected as authored inputs. It does not promise every upstream workflow. `unsupported` means no
support promise: reject explicit selected-destination requests with an owner or
limitation diagnostic, without rejecting Godot's automatically populated defaults.

The bounded inventory covers clean built-in exporters in this exact editor. It excludes
third-party export plugins, discovered Android/iOS native plugin descriptors, .NET-specific
export plugins, Windows/Web and other destinations. It does not enumerate all runtime
ProjectSettings. Another supported editor minor or build requires a new inventory comparison.
The configured 4.8-beta1 comparison below records the observed minor-version differences.

## Reflection is not a complete exporter inventory

`EditorExportPreset.get_property_list()` applies exporter visibility predicates. Advanced
mode and the union of an actual preset and `create_preset()` still omit conditionally hidden
options. The existing [probe](../../rules_godot/tools/action/shell.gd) uses that union, so this is
also an implementation correction, not just a documentation issue.

The experiment collected visible names/types from both presets, then supplemented them with
literal `PropertyInfo(Variant::TYPE, "key")` names from the matching exporter source and
base classes. It retained a source candidate only if the fresh runtime preset reported
`has(key)`, and obtained its type using `typeof(preset.get(key))`. Values were never
serialized. Source review covered dynamic built-in families: Android permissions and ABIs;
Apple privacy-data/reason tables; and iOS icon names/appearances. Those families were visible
in the clean fixture. Dynamic plugin-discovery branches were empty by construction.

This added 34 otherwise hidden keys: six Linux SSH fields; 25 macOS signing, entitlement,
notarization and SSH fields; two Android Gradle input fields; and iOS
`capabilities/performance_a12`. The JSON observation column distinguishes reflected keys
from source candidates confirmed by the runtime. A source-only candidate never establishes
availability or a default.

The probe receives the selected version's hidden names and explicitly authored
export-option names in addition to reflection. The engine profile keeps only
what rules act on: the rejected (Bazel-owned or unsupported) keys with their owners, and the
hidden keys host tools read. Its rejected keys include every hidden key but one, so the
probe still reports all 34; this JSON remains the reviewed per-key record. Read registered hidden options
with `preset.has()`/`preset.get()`; keep values and defaults authoritative in the selected
Godot executable. Store maintained exporter names/support dispositions beside the version
profile or an adjacent generated inventory, not hard-coded default values in host tools.

For a declared export plugin, repeat the disposable export with that plugin loaded, diff the
result against the clean inventory, and include the plugin's declared option names even if
its visibility hook hides them. Classify its PCK effects separately from any native packaging
effects. Preserve supported custom plugin options; absence from the core inventory is not
grounds for blanket rejection. Plugin identity/version and dependency membership belong in
that inventory's provenance. If a plugin supplies dynamically hidden names, its declaration
or explicit authored-name list is necessary; reflection alone cannot prove completeness.

Reproduction outline:

1. Create a disposable project with only the inventory export plugin enabled. Generate one
   preset named `Inventory`, the selected `platform`, and `export_filter="all_resources"`.
   Do not write `script_export_mode` or any export options.
2. Extract literal property names from the version-pinned sources below. In `_export_begin`,
   enable `_export_preset_advanced_mode`; collect property lists from the active/fresh presets;
   supplement registered source candidates; record names and `typeof` values only. In
   `_export_file`, call `skip()` so project contents are not relevant to the inventory.
3. Run `"$GODOT" --headless --path "$PROBE_PROJECT" --export-pack Inventory "$OUTPUT_PCK"`
   once per destination. Inspect logs for script errors as well as process status; an export
   can return success despite an export-plugin script error. Require the inventory artifact.
4. Review source registration loops and conditional branches, compare keyed rows with the
   current inventory, and explicitly assign every newly registered built-in key a disposition.
   Do not infer support from registration or from a successful disposable export.

Upstream source owners, pinned to `4.7.2-stable`:

- [Preset visibility and values](https://github.com/godotengine/godot/blob/4.7.2-stable/editor/export/editor_export_preset.cpp),
  [preset creation](https://github.com/godotengine/godot/blob/4.7.2-stable/editor/export/editor_export_platform.cpp).
- [Linux](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/linuxbsd/export/export_plugin.cpp)
  and its [PC base](https://github.com/godotengine/godot/blob/4.7.2-stable/editor/export/editor_export_platform_pc.cpp).
- [Android](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/android/export/export_plugin.cpp).
- [macOS](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/macos/export/export_plugin.cpp).
- [iOS](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/ios/export/export_plugin.cpp)
  and its [Apple embedded base](https://github.com/godotengine/godot/blob/4.7.2-stable/editor/export/editor_export_platform_apple_embedded.cpp).

## Default preset fields

In all four clean exports, both the loaded preset with omitted `script_export_mode` and a
newly created preset returned `get_script_export_mode() == 2`. The current ruleset explicitly
writes mode 0, so removing that old default is an observable intentional change. An omitted
field must stay omitted and inherit the selected Godot version's default; do not replace the
old hard-coded 0 with a new hard-coded 2. Keep explicit overrides for supported modes.

The inventory contains exporter options only. `script_export_mode` is a preset field and
must remain in the separate `preset_settings` namespace; `custom_features`, the other
preset field, comes from the build settings `godot_project.custom_features` names. The
[preset loader](https://github.com/godotengine/godot/blob/4.7.2-stable/editor/export/editor_export.cpp)
and actual export experiment own omitted-field behavior, not an option-family heuristic.

## Consumer and native-owner index (2026-11-02 record)

This index explains the JSON's owner IDs as reviewed on the snapshot date. Current
configuration ownership is documented in the public
[configuration guide](../../rules_godot/docs/public/configuration.md). All `consumed` rows have
execution-time consumers. Some asset decisions also inspect
explicit pack option declarations during analysis; declared resource membership is still
required. This inventory does not solve early native configuration by reading an action
output during analysis.

| Owner ID | Evidence and intended effect |
| --- | --- |
| `android-host` | [shell_android.py](../../rules_godot/tools/platforms/shell_android.py) and finite [profile](../../rules_godot/godot/private/engine/profiles.bzl): manifest, command line, theme, version and permission generation. `splash_screen/*` behavior additionally needs the internally provisioned AndroidX dependency below. |
| `apple-host` | [shell_apple.py](../../rules_godot/tools/platforms/shell_apple.py) and finite profile: plist/localization/privacy metadata and launch background. Includes all exact observed privacy members matched to that profile, not future `privacy/*` keys. |
| `host-assets` | [shell_assets.bzl](../../rules_godot/godot/private/shell_assets.bzl) and [probe](../../rules_godot/tools/action/shell.gd): declared image selection/rendering. iOS dark and tinted icons have existing consumers; all 51 observed iOS icon keys are included. |
| `icon-composer` | [desktop backend](../../rules_godot/godot/platforms/private/desktop.bzl): existing conditional native Icon Composer route, with its host/tool requirements. |
| `godot-pck` | The PC exporter's `get_preset_features()` maps the two texture-format controls to actual import/export features used for the PCK. |
| `engine` | Declared app/engine inputs and selected templates own runtime binaries. No filesystem-valued custom-template option. |
| `destination` | Bazel OS/CPU/environment scenario and slice transitions; selected Godot architecture options are internal derived values. Supported CPU sets remain the app contract's sets. |
| `output-layout` | Bazel target/output identity and deterministic app/PCK layout; no public embed-PCK or console-wrapper option. |
| `identity` | The single analysis-time native identity adapter and its consistency projection; no competing authored package/bundle identifier. |
| `android-sdk` | Native Android min/target SDK configuration; NDK and compile SDK remain separate. Godot's Gradle-named keys are rejected as authored input. |
| `android-format` | Bazel APK/AAB format configuration, with existing format limitations. |
| `android-compression` | One internal extraction/compression policy consistent with native package assembly; no public renamed Gradle switch. |
| `android-signing` | Native rules and declared debug keystore/defaults. AAB remains unsigned by this app workflow. |
| `ios-signing` | Native Apple signing configuration and declared profile/entitlement artifacts. Godot lookup strings and entitlement-option generation are not implemented alternatives. |
| `ios-deployment` | Typed analysis-time minimum-OS/device-family adapters; project/preset values cannot configure earlier native graph construction. |
| `macos-signing` | Retained separate signing helper and declared entitlement file/options, not wholesale Godot-export signing parity. |

Unsupported owner IDs make the current boundary explicit:

| Owner ID | Reason / future prerequisite |
| --- | --- |
| `gradle` | No Gradle project execution or source-template workflow. |
| `xr` | Existing Android host rejects nonzero XR mode. The normal default mode remains valid. |
| `shader-baking` | No established hermetic headless shader-baker execution/renderer contract in this feature. Merely forwarding its feature tag does not establish packaged shader support. |
| `remote-deployment` | No SSH deployment workflow. |
| `xcode-export` | No Godot-generated Xcode project, export-method workflow or copied Xcode-build metadata. Native Bazel toolchains own native compilation. |
| `notarization` | No notarization workflow. |
| `macos-export-signing` | Godot's installer signing, rcodesign certificate/password and provisioning-profile workflow are not implemented by the retained signing helper. |
| `angle-export` | No Godot-export-driven ANGLE runtime discovery/copying. A future runtime dependency contract must be explicit. |
| `ios-launch-scale` | Current generated launch metadata consumes image/color options, but not `storyboard/image_scale_mode`. |
| `ios-camera-module` | No native host build consumer for `modules/camera`. Runtime engine capabilities require the declared engine contract. |
| `ios-signature` | Unlike macOS, the iOS host does not consume `application/signature`. |

There are no unmatched/unassessed built-in rows in this bounded snapshot. Future unknown
keys remain unassessed until reviewed; this classification must not become a generic
assertion of support for a prefix or for every Godot version.

## Internally provisioned AndroidX splash dependency

Decision: contribute `androidx.core:core-splashscreen:1.0.1` from the ruleset's non-development
`rules_jvm_external` extension use to the shared `maven` installation. This is the version
already used by [examples](../../rules_godot/examples/MODULE.bazel) and the
[regression module](../../rules_godot/tests/MODULE.bazel). Add a
checked-in ruleset lock generated from the complete selected contribution graph, including
this dependency and its resolved transitive closure; keep splashscreen the only new direct
app-library declaration. Use
Google Maven and Maven Central repositories, and `use_starlark_android_rules = True`.
Import the generated repository in the ruleset and use its internally mapped
`@maven//:androidx_core_core_splashscreen` label only on the Android backend dependency path.
Remove the per-app splash label and redundant consumer artifact declarations.

Use one shared Maven version-mediation graph. A separately named private installation was
rejected because the engine/add-on dependencies can already bring AndroidX core classes;
resolving another copy/version privately risks duplicate classes rather than predictable
root-module mediation. Do not force the version against root overrides. The checked lock
is the default resolved graph; the consumer's root lock and version decisions take standard
precedence. This is dependency setup, not another app option.

With an existing root `maven.install`, regenerate its lock and include `autoload_rules_godot` in
`known_contributing_modules` when that allowlist is used. Both checked-in consumer modules
allowed only `protobuf` and received that update. Root locks override dependency
locks. If several dependency modules supply locks without a root owner, the extension
requires the root to choose a single installation lock; document this standard integration
case rather than silently creating a second AndroidX graph. Keep the existing separate
`rules_android_maven` tooling installation distinct from app library dependency mediation.

Sources: pinned rules_jvm_external 6.10
[module-extension implementation](https://github.com/bazel-contrib/rules_jvm_external/blob/6.10/private/extensions/maven.bzl)
(`install` tag documentation, contribution filtering, root lock precedence),
[pinned-artifact repositories](https://github.com/bazel-contrib/rules_jvm_external/blob/6.10/private/extensions/download_pinned_deps.bzl),
and [Bazel extension lifecycle](https://bazel.build/external/extension).

Preserve laziness: resolving module/repository metadata is distinct from fetching/analyzing
the Android library and SDK closure. Do not load generated Maven targets into a shared
non-Android dependency path. The destination-selected backend carries the library edge.
Acceptance exercises (a) an external consumer with no explicit splash artifact or app
label, (b) a root Maven lock/allowlist that includes the contribution, and (c) a host-only
build with Android SDK absent and no Android AAR fetch/analysis.

## Configured 4.8-beta1 comparison

The independent mobile consumer's `--config=beta` editor reported
`4.8-beta1 (official)`. Disposable probe exports for all four supported destinations
retained every 4.7.2 key with the same runtime type. Excluding the fixture's declared
`context/marker` plugin option, the registered totals were Linux 16, macOS 238,
Android 207 and iOS 243.

| Destination | Added key | Live type | Disposition and effect |
| --- | --- | --- | --- |
| Linux, macOS | `debug/export_debug_symbols` | int | Bazel-owned: native compiler/symbol settings and the app's symbol output group own native symbol delivery; explicit Godot requests are rejected. |
| Android | `gradle_build/minification` | bool | Unsupported: rules_android packages the app without a Gradle build; explicit requests are rejected. |

No removed keys or changed types were observed. The profile carries these explicit
minor-version deltas instead of aliasing the entire 4.7 policy. Retained native host
metadata/image tables remain shared where this comparison established no option-contract
difference. Availability, actual types and defaults remain authoritative in the live probe;
this comparison neither broadens the supported version range nor promises untested native
effects. Hidden previously inventoried keys were checked with `has/get`; newly registered
names were obtained from both live preset property lists. Dynamically hidden new plugin
names still need an explicit declaration/authored-name candidate as described above.

Reproduce from `rules_godot/` by building
`//godot/platforms/private/tests/app_platform_selection:linux_export_options_match_facts_observations_facts`
and its `macos_`, `android_` and `ios_` counterparts with
`--//godot:engine=beta`. Inspect each facts JSON by `editor_version`
and destination features; compare only option names/types, never persist defaults or
credential-bearing values.
