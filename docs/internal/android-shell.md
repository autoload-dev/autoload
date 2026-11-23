# Android shell and Godot's Android export

`godot_app` builds Android applications with rules_android instead of Godot's Gradle
template. This page records how its shell follows the Gradle export of Godot's Android
exporter, which differences remain and why, and how to review a new Godot version.

## Scope and evidence

Research snapshot: 2026-11-05. The comparison covers `platform/android` of Godot 4.7.2-stable,
the pinned 4.7 maintenance snapshot (4.7.3-rc, identical in every reviewed file) and
4.8-beta1: the Gradle template app (`java/app`), `GodotActivity.kt` of the Android shell
library and the exporter (`export/export_plugin.cpp`, `export/gradle_export_util.cpp`).
[android_shell_review_test.py](../../rules_godot/godot/private/engine/tests/android_shell_review_test.py) holds the
reviewed files with their digests.

An Android 16 emulator (API 36, arm64, 1080x2400) ran three 4.7.2 probe applications. With
`screen/immersive_mode` on, Godot's default, the system bars were hidden at launch and after
returning from Picture in Picture, and `DisplayServer.get_display_safe_area()` covered the
screen. With it off, the bars stayed visible and the window excluded them. With
`screen/edge_to_edge` as well, the window covered the screen and the safe area excluded the
63-pixel status and navigation bars. Leaving the application with
`DisplayServer.pip_mode_set_auto_enter_on_background(true)` entered Picture in Picture. No
physical device or Store submission was involved.

## How the shell follows Godot

The application runs Godot's own Java code where Godot's export compiles code, and writes
the files Godot's exporter generates:

| Godot's Gradle export | rules_godot |
| --- | --- |
| Template activity `com.godot.game.GodotApp` | The same source of the pack's minor, unchanged, in [`godot/private/engine/android/`](../../rules_godot/godot/private/engine/android); the engine profile's `template_activity` selects it |
| Gradle's generated `com.godot.game.BuildConfig` | [BuildConfig.java](../../rules_godot/godot/private/engine/android/BuildConfig.java) with the field the 4.7 template activity reads, `FLAVOR = "standard"` |
| `assets/_cl_` from `get_command_line_flags` | `assets/_cl_` in Godot's encoding from `command_line_file` in [shell_android.py](../../rules_godot/tools/platforms/shell_android.py); flags come from the profile's `command_line` table |
| Template manifest merged with `_write_tmp_manifest`, `_get_application_tag` and `_get_activity_tag` | The complete main manifest from [AndroidManifest.xml.tpl](../../rules_godot/tools/platforms/templates/AndroidManifest.xml.tpl): the non-exported `GodotApp` and its exported `GodotAppLauncher` alias with the launcher categories, permissions with Godot's `maxSdkVersion` limits, Vulkan features and metadata |
| `res/values/themes.xml` from `_fix_themes_xml` | [themes.xml.tpl](../../rules_godot/tools/platforms/templates/themes.xml.tpl) with the same attributes, including `gradle_build/custom_theme_attributes` |
| Namespace `com.godot.game` | `custom_package` and manifest package `com.godot.game`; `applicationId` comes from `godot_app.application_id` |
| One-click deploy writes its arguments into `assets/_cl_` | Builds without `-c opt` add [LaunchArgumentsPlugin.java](../../rules_godot/godot/platforms/private/android/LaunchArgumentsPlugin.java) and its `org.godotengine.plugin.v2` registration, which pass the Godot arguments of `bazel run` from a file the launcher writes with `run-as` into the application's private files; `GodotActivity` drops its own `command_line_params` extra for the exported launcher alias, and any application could send an extra |
| App dependencies `androidx.fragment`, `androidx.core:core-splashscreen`, `androidx.documentfile` | The Android shell library's dependencies, the splash screen and `androidx.activity` for `EdgeToEdge`, from the consumer's shared `maven` graph |

Godot's exporter decides the values: the probe reports options and settings, and the
[engine profile](../../rules_godot/godot/private/engine/profiles.bzl) holds the exporter's remaining
tables, such as the activity's `config_changes` per minor.

## Remaining differences

| Area | Godot's Gradle export | rules_godot | Decision |
| --- | --- | --- | --- |
| Project files | Copied into `assets/`, for an App Bundle into the install-time asset pack `assetPackInstallTime` | One uncompressed `assets/main.pck` in the base module, mounted with `--main-pack res://main.pck` | Kept: the pack is Bazel's export unit. Gap: the base module carries the pack, so Google Play's base module size limit applies to the whole project |
| Localized application name | `res/values-<locale>/godot_project_name_string.xml` from `application/config/name_localized` or the project's translations | `android:label` from `package/name` or `application/config/name` only | Gap |
| Export plugins | `EditorExportPlugin` manifest contents, Android plugin AARs and Maven dependencies through Gradle | `android_library`, `aar_import` and Maven targets as platform libraries; rules_android merges their manifests | Kept: Bazel targets own platform libraries ([platforms guide](../../rules_godot/docs/public/platforms.md#android)) |
| Manifest merge directives | `tools:node` and `tools:replace` overlay the template manifest | The main manifest is complete; library manifests merge below it | Kept: the merged result is the same |
| Duplicate native libraries | `pickFirst` keeps Godot's `libc++_shared.so` | No `pickFirst`; distinct extension libraries of one name fail the build | Gap for libraries that ship their own `libc++_shared.so`; not observed |
| Native library packaging | `gradle_build/compress_native_libraries` sets `useLegacyPackaging` | `.so` files stay uncompressed with `extractNativeLibs="false"`; an explicit option is rejected | Kept (`android-compression` owner) |
| Signing | Keystore options sign the Gradle build's outputs | `godot_app.android_debug_key`; AABs stay unsigned | Kept (`android-signing` owner) |
| Debug symbols | `debugSymbolLevel 'NONE'`; symbols stay in the Gradle build | `<name>.debug_symbols` | Kept: Play Console takes the ZIP |
| Packaging excludes | `META-INF/LICENSE`, `META-INF/NOTICE` excluded; hidden asset files kept by `ignoreAssetsPattern` | rules_android's defaults | Kept: the APK's assets are `main.pck` and `_cl_` only |
| Remote debugging and deploy | One-click deploy adds `INTERNET` and debug flags to `_cl_` | No deploy workflow | Kept |
| .NET | `mono` flavor loads the .NET cryptography library; 4.8 declares `GodotApplication` for it | `standard` flavor; no application class | Kept: no .NET support |
| XR and minification | `xr_features/xr_mode`, 4.8's `gradle_build/minification` | Rejected options | Kept (`xr`, `gradle` owners) |
| Dependency versions | Gradle picks the highest requested version | The consumer's `rules_jvm_external` resolver mediates the shared graph | Kept: one graph per consumer ([platforms guide](../../rules_godot/docs/public/platforms.md#android)) |

## Review a Godot version

`pinned_godot_sources_match_the_reviewed_android_shell_test` runs over every Godot source
the repository pins. A pin of a new minor, or one whose reviewed files changed, fails it
with the version and the changed paths. Then:

1. Diff each changed file against the reviewed version of Godot.
2. Template activity: copy it unchanged to `godot/private/engine/android/godot_<minor>/`
   and set the profile's `template_activity`: the copy, the upstream path and whether it
   reads `BuildConfig.java`, which gets the fields it reads.
3. Template manifest and `_get_activity_tag`, `_get_application_tag`, `_write_tmp_manifest`:
   update `AndroidManifest.xml.tpl` and the profile's manifest tables, such as
   `config_changes`, `launcher_categories` and `max_sdk_permissions`.
4. `_fix_themes_xml`: update `themes()`; `get_command_line_flags`: the profile's
   `command_line` table; `GodotActivity.kt`: how `_cl_`, launch intents and Picture in
   Picture behave.
5. `build.gradle` and `config.gradle`: SDK defaults, packaging and dependency versions,
   which `MODULE.bazel`'s `maven` artifacts pin.
6. Update the differences above and add the reviewed digests to the minor's table in
   `android_shell_review_test.py`.
7. For activity or window changes, check immersive mode, edge to edge, the safe area and
   Picture in Picture on an emulator.

Export options themselves follow the [export option inventory](export-option-inventory.md).

## Why the shell runs Godot's template activity

Running Godot's activity unchanged keeps behavior such as immersive mode, edge to edge and
Picture in Picture identical to Godot's export without a hand-written copy; a version update
replaces one file. The alternatives cost more for the same result: extracting the template
from Godot's export templates needs their whole archive even for Android-only consumers, and
source-built engines have none; generating the activity from patched upstream sources breaks
on unrelated edits; diffing generated manifests against a real Gradle export needs a Gradle
and Android SDK run per version. The digest check costs one review per new pin and catches
exporter changes that the probe's export options do not show.
