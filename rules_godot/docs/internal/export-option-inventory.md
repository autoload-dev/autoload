# Export option inventory

## Scope and evidence

Research snapshot: 2026-11-02. The experiment used the official standard macOS Godot
`4.7.2.stable.official.ed1daf0bf` editor with a minimal project and a temporary export
plugin. It exported a disposable PCK separately with the Linux, macOS, Android and iOS
exporters. All four commands completed and wrote the inventory. No Android SDK, native
compilation, device, signing or Store validation was involved.

[export-options-4.7.2.json](export-options-4.7.2.json) enumerates 701 platform/key pairs
with their runtime Godot types and their reviewed disposition. It is the dated per-key
record, not runtime policy: the rules act on the engine profile's rejected-keys table in
[profiles.bzl](../../godot/private/engine/profiles.bzl) and on the live probe's
registration and types. A row records an option, not a public attribute. The file stores
no option values, credentials or copied default schema. Its owner IDs are the ones of
`option_owners` and `rejected_export_options` in the profile, plus the consumers listed
under [owner IDs](#owner-ids).

| Exporter | Consumed by rules_godot | Delegated to Godot | Bazel-owned | Unsupported | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Linux | 0 | 2 | 5 | 8 | 15 |
| macOS | 175 | 0 | 36 | 26 | 237 |
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
options. The [probe](../../tools/editor_action/plugin/shell.gd) therefore also asks by name for the
hidden options the engine profile lists (`hidden_export_options`) and for every option name
a pack authors.

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

The engine profile keeps only what rules act on: the rejected (Bazel-owned or unsupported)
keys with their owners, and the hidden keys host tools read. Its rejected keys include every
hidden key but one, so the probe still reports all 34; this JSON remains the reviewed
per-key record. Read registered hidden options with `preset.has()`/`preset.get()`; values
and defaults stay authoritative in the selected Godot executable, not in host tools.

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
newly created preset returned `get_script_export_mode() == 2`. An omitted field stays
omitted and inherits the selected Godot version's default.

The inventory contains exporter options only. `script_export_mode` is a preset field in the
separate `preset_settings` namespace; `custom_features`, the other preset field, comes from
the build settings `godot_project.custom_features` names. The
[preset loader](https://github.com/godotengine/godot/blob/4.7.2-stable/editor/export/editor_export.cpp)
and the export experiment own omitted-field behavior, not an option-family heuristic.

## Owner IDs

Which Bazel input owns a `bazel-owned` option is the `option_owners` table of the
[engine profile](../../godot/private/engine/profiles.bzl), and the
[configuration guide](../public/configuration.md#values-that-belong-to-bazel) lists the
values that belong to Bazel. All `consumed` rows have execution-time consumers; some asset
decisions also inspect explicit pack option declarations during analysis, and declared
resource membership is still required. The consumer IDs:

| Owner ID | Consumer and effect |
| --- | --- |
| `android-host` | [shell_android.py](../../tools/platforms/shell_android.py) and the finite profile: manifest, command line, theme, version and permission generation. `splash_screen/*` behavior additionally needs the AndroidX splash screen dependency of the shared Maven installation. |
| `apple-host` | [shell_apple.py](../../tools/platforms/shell_apple.py) and the finite profile: plist, localization and privacy metadata and launch background. Includes all exact observed privacy members matched to that profile. |
| `host-assets` | [shell_assets.bzl](../../godot/private/shell_assets.bzl) and the [probe](../../tools/editor_action/plugin/shell.gd): declared image selection and rendering. iOS dark and tinted icons have consumers; all 51 observed iOS icon keys are included. |
| `icon-composer` | [desktop backend](../../godot/platforms/private/desktop.bzl): the conditional native Icon Composer route, with its host and tool requirements. |
| `godot-pck` | The PC exporter's `get_preset_features()` maps the two texture-format controls to import and export features used for the PCK (`delegated`). |

The unsupported owner IDs and why each has no workflow:

| Owner ID | Reason |
| --- | --- |
| `gradle` | No Gradle project execution or source-template workflow. |
| `xr` | The Android host rejects nonzero XR mode. The normal default mode remains valid. |
| `shader-baking` | No hermetic headless shader-baker execution or renderer contract. Forwarding its feature tag does not establish packaged shader support. |
| `remote-deployment` | No SSH deployment workflow. |
| `xcode-export` | No Godot-generated Xcode project, export-method workflow or copied Xcode-build metadata. Native Bazel toolchains own native compilation. |
| `notarization` | No notarization workflow. |
| `macos-export-signing` | Godot's installer signing, rcodesign certificate and password and provisioning-profile workflow are not implemented by the signing helper. |
| `angle-export` | No Godot-export-driven ANGLE runtime discovery or copying. |
| `ios-launch-scale` | The generated launch metadata consumes image and color options, but not `storyboard/image_scale_mode`. |
| `ios-camera-module` | No native host build consumer for `modules/camera`. Runtime engine capabilities follow the declared engine. |
| `ios-signature` | Unlike macOS, the iOS host does not consume `application/signature`. |

Every built-in row of this snapshot has a disposition. A key a later Godot version
registers stays unassessed until it is reviewed; the classification does not claim support
for a prefix or for every Godot version.

## Configured 4.8-beta1 comparison

The independent mobile consumer's `--config=beta` editor reported
`4.8-beta1 (official)`. Disposable probe exports for all four supported destinations
retained every 4.7.2 key with the same runtime type. Excluding the fixture's declared
`context/marker` plugin option, the registered totals were Linux 16, macOS 238,
Android 207 and iOS 243.

| Export platform | Added key | Live type | Disposition and effect |
| --- | --- | --- | --- |
| Linux, macOS | `debug/export_debug_symbols` | int | Bazel-owned (`native-debug-symbols`): native compiler/symbol settings and the app's symbol output group own native symbol delivery; explicit Godot requests are rejected. |
| Android | `gradle_build/minification` | bool | Unsupported: rules_android packages the app without a Gradle build; explicit requests are rejected. |

No removed keys or changed types were observed. The profile carries these explicit
minor-version deltas instead of aliasing the entire 4.7 policy. Retained native host
metadata/image tables remain shared where this comparison established no option-contract
difference. Availability, actual types and defaults remain authoritative in the live probe;
this comparison neither broadens the supported version range nor promises untested native
effects. Hidden previously inventoried keys were checked with `has/get`; newly registered
names were obtained from both live preset property lists.
