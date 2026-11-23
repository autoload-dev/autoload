# Export-plugin hook inventory

## Scope and evidence

Research snapshot: 2026-11-08. The inventory was read from the Godot sources the repository
pins: `4.7.2-stable`, `4.8-beta1` and the 4.7.3 release-candidate snapshot. It covers every
virtual method of `EditorExportPlugin` (`GDVIRTUAL` in `editor/export/editor_export_plugin.h`),
every bound method through which a plugin adds files, libraries or native settings to an
export (`add_*` and `skip` in `editor_export_plugin.cpp`), and the two legacy plugin
descriptor kinds. Line numbers refer to `4.7.2-stable` unless a row names 4.8.

The engine profile's `export_hooks` table in
[profiles.bzl](../../rules_godot/godot/private/engine/profiles.bzl) holds these rows per Godot minor;
this document is their reviewed and cited form. The test `//godot/private/engine/tests:pinned_godot_sources_declare_the_reviewed_export_hooks_test`
fails when a pinned source declares a hook the profile does not list, or lists one it no
longer declares; such a pin needs a new review of the rows below.

## What the pack export runs

No build runs an `EditorExportPlugin` of an add-on's editor part: an add-on
declares what its plugin does as the counterparts below, and a project transforms files a
customization hook would change in a `genrule`. Export plugins an extension registers
natively still run in pack exports, which load every extension. The facts below say what
such a plugin can affect.

rules_godot builds a pack with Godot's pack export (`EditorExportPlatform::export_pack`,
`editor/export/editor_export_platform.cpp:2464`) and packages the application itself. The
pack export:

- runs `_export_begin`, `_export_file`, the customization hooks, `_get_export_features` and
  `_export_end` of every plugin, without consulting `_supports_platform` (`:806-817`,
  `:1457-1472`, `:1544-1549`, `:1778-1780`);
- discards what `add_shared_object` returns: `save_pack` receives no shared-object sink
  (`:2466`, `:1930-1936`);
- does not call `can_export` (`editor/editor_node.cpp:1377-1391`), so export-option warnings
  never run.

Everything else a plugin contributes is read only by a platform's full export: the Android
Gradle build, the Xcode project of the iOS export, or the macOS bundle. A Bazel build has
none of these, so what such a hook returns needs a Bazel declaration instead.

## Dispositions

| Disposition | Meaning | Review |
| --- | --- | --- |
| `pack` | Godot applies the effect inside the pack export. | None needed. |
| `counterpart` | A Bazel declaration carries the contribution; the row names its kind. | The add-on states that it declares the counterpart, or that the application does not need the contribution. |
| `none` | No counterpart exists, because the hook edits a project a Bazel build does not have. | The add-on can only state that the application does not need it. |

A supported minor's source declares no hook without a row, so a new Godot minor never passes
a hook unreviewed.

## Virtual methods

26 virtuals in 4.7 and 4.8 (`editor_export_plugin.h:120-152`). Scripts override them by
method name (`core/object/make_virtuals.py:17-55`).

| Hook | Godot consumer | Disposition | Operating systems | Counterpart |
| --- | --- | --- | --- | --- |
| `_export_begin`, `_export_file`, `_export_end` | `ExportNotifier` `:798-834`; `export_project_files` `:1544` | pack | — | Godot's pack export. `_export_end` edits of native export files have no effect. |
| `_begin_customize_resources`, `_customize_resource`, `_end_customize_resources` | `export_project_files` `:1457-1462`, `:1600`, `:1749` | pack | — | Godot's pack export |
| `_begin_customize_scenes`, `_customize_scene`, `_end_customize_scenes` | `:1465-1469`, `:1715`, `:1753` | pack | — | Godot's pack export |
| `_get_customization_configuration_hash` | `:1462`, `:1469` | pack | — | Godot's pack export |
| `_get_export_features` | `:1778-1780`, written to `project.binary` | pack | — | Godot's pack export; the project's custom features come from the build settings `godot_project.custom_features` names, and extension library selection reads none |
| `_get_export_options`, `_get_export_options_overrides` | `create_preset` `:623`; `update_value_overrides` before the export (`editor_node.cpp:1376`) | pack | — | Godot's pack export; options rules_godot owns keep their checks |
| `_should_update_export_options`, `_get_export_option_visibility`, `_get_export_option_warning`, `_get_name`, `_supports_platform` | Editor UI, `can_export`, ordering, gating | pack | — | No effect needed |
| `_get_android_libraries` | Gradle build only (`platform/android/export/export_plugin.cpp:3906`) | counterpart | android | Android library (`aar_import`, `android_library`) |
| `_get_android_dependencies` | Gradle build only (`:3914`) | counterpart | android | Maven artifact (`@maven//:…`) |
| `_get_android_dependencies_maven_repos` | Gradle build only (`:3917`) | counterpart | android | Maven repository of the root module's `maven.install` |
| `_get_android_manifest_element_contents`, `_get_android_manifest_application_element_contents`, `_get_android_manifest_activity_element_contents` | Gradle build only (`:1068-1082`, `gradle_export_util.cpp:298-413`) | counterpart | android | Library manifest (`android_library` with `exports_manifest = 1`, or `aar_import`); activity entries merge by `android:name="com.godot.game.GodotApp"` |
| `_update_android_prebuilt_manifest` | APK export without Gradle only (`:4176-4188`) | none | android | Rewrites a binary manifest; manifest content goes through a library manifest instead |
| `_end_generate_apple_embedded_project` | Xcode export on a macOS host (`editor_export_platform_apple_embedded.cpp:2109-2113`) | none | ios | Edits the Xcode project. What the edit adds has its own counterpart: Swift packages as `swift_library`, an Icon Composer icon as `godot_app.ios_app_icons` |

## Native-packaging methods

| Method | Godot consumer | Disposition | Operating systems | Counterpart |
| --- | --- | --- | --- | --- |
| `add_file`, `skip` | `export_project_files` `:1428-1433`, `:1559-1576` | pack | — | Godot's pack export |
| `add_shared_object` | Dropped by the pack export (`:1930-1936`) | counterpart | all | Extension library of a `godot_extension`, or a platform library (`cc_library`, `aar_import`, XCFramework import) |
| `add_apple_embedded_platform_framework`, `add_apple_embedded_platform_embedded_framework` (aliases `add_ios_framework`, `add_ios_embedded_framework`) | Xcode export (`editor_export_platform_apple_embedded.cpp:1386-1392`) | counterpart | ios | XCFramework import (`apple_static_xcframework_import`, `apple_dynamic_xcframework_import`) |
| `add_apple_embedded_platform_project_static_lib` (alias `add_ios_project_static_lib`) | `:1394-1399`, `:2030-2041` | counterpart | ios | Static library (`cc_import`, `objc_library`) |
| `add_apple_embedded_platform_plist_content` (alias `add_ios_plist_content`) | `:748-755`, into the Info.plist template | counterpart | ios | Info.plist fragment |
| `add_apple_embedded_platform_linker_flags` (alias `add_ios_linker_flags`) | `:757-772`, into `OTHER_LDFLAGS` | counterpart | ios | `linkopts` of a platform library |
| `add_apple_embedded_platform_bundle_file` (alias `add_ios_bundle_file`) | `:1401-1403`, into the Resources phase | counterpart | ios | Bundle resource of a platform library (`data` of an `objc_library`, `apple_resource_group`) |
| `add_apple_embedded_platform_cpp_code` (alias `add_ios_cpp_code`) | `:774-781`, into `dummy.cpp` | counterpart | ios | Sources of a platform library (`objc_library`, `cc_library` with `alwayslink`) |
| `add_apple_embedded_platform_spm_package` (4.8 only) | 4.8 Xcode export (`editor_export_platform_apple_embedded.cpp:1662-1710`, Swift package references in the project) | counterpart | ios | Swift package products as Bazel targets, such as rules_swift_package_manager's `@swiftpkg_…` libraries |
| `add_macos_plugin_file` | macOS export (`platform/macos/export/export_plugin.cpp:1499-1514`) | none | macos | The macOS application backend takes no plugin files |

## Legacy plugin descriptors

| Descriptor | Godot consumer | Disposition | Operating systems | Counterpart |
| --- | --- | --- | --- | --- |
| `.gdap` under `res://android/plugins/` | Gradle build only (`platform/android/export/export_plugin.cpp:712-777`) | counterpart | android | Its `binary` and `dependencies` as Android libraries and Maven artifacts |
| `.gdip` under `res://ios/plugins/` | Xcode export (`editor_export_platform_apple_embedded.h:287-365`) | counterpart | ios | Its libraries, frameworks, plist keys and linker flags as above; in 4.8 also its Swift packages |

## Built-in export plugins

Godot registers its own export plugins: GDExtension, DedicatedServer, ShaderBaker, GDScript,
OpenXR and, in .NET editors, C#. They are not add-on hooks. rules_godot replaces the
GDExtension plugin's native part (extension delivery and iOS static linking), and the OpenXR
plugin's Android hooks fall under rules_godot's rejection of XR exports.

## Version differences

`4.8-beta1` adds `add_apple_embedded_platform_spm_package` and Swift packages in `.gdip`
descriptors. The virtuals and the other methods are the same as in 4.7.2. The 4.7.3 snapshot
declares the same hooks as 4.7.2.
