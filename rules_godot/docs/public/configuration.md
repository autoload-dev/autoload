# Godot configuration

Configure game behavior in `project.godot` and Godot's export namespaces. Declare build
inputs as Bazel labels. `godot_app` consumes an explicit pack and the registered runtime; the pack owns
export configuration, and the project it names owns the configuration its imports, runs
and editor views share.

## Three namespaces

| Namespace | Godot representation | Bazel owner |
|---|---|---|
| Project Settings | `project.godot`, `section/property` keys | Authored `godot_project.project_file`; resource/project `settings`; [project `settings_from_flags`](#settings-from-build-settings) for per-build values; pack `settings` for export-only overrides |
| Preset Settings | `[preset.N]` | Pack `preset_settings`: `script_export_mode`; custom features come from [build settings the project names](#custom-features) |
| Export Options | `[preset.N.options]` | Pack `export_options`, using registered exporter or declared export-plugin keys |

A project file is required. The rules generate an export preset; they do not read or
select presets from an existing `export_presets.cfg`. A setting's `res://` path must name
a declared resource. A string path does not add files or dependencies to the build.

Values in the dictionaries are **Godot literal strings**, as in `export_presets.cfg`,
rather than Starlark values: `'"My Game"'`, `"true"`, `"7"`, `'PackedStringArray("a", "b")'`,
or `"Color(0.1, 0.2, 0.3, 1)"`. Arrays, dictionaries and supported built-in constructors
are accepted. Keep complex serialized objects and typed arrays in the authored project
file; their existing serialization is preserved.

```starlark
load("@autoload_rules_godot//godot:app.bzl", "godot_app")
load("@autoload_rules_godot//godot:defs.bzl", "godot_pack", "godot_project", "godot_resources")

godot_resources(name = "main", srcs = ["main.gd", "main.tscn", "icon.svg"])

godot_project(
    name = "game",
    project_file = "project.godot",
    main_scene = "main.tscn",
    settings = {"application/config/name": '"My Game"'},
)

godot_pack(
    name = "pack",
    project = ":game",
    deps = [":main"],
    settings = {"application/config/version": '"2.3.4"'},
)

godot_app(name = "app", pack = ":pack")
```

Supply a mobile `application_id` where applicable; see [platform setup](platforms.md);
the [registered engines](engine.md) supply editor and runtime. Add `export_options` for one operating system with
`select()` when one pack serves several operating systems. For example, an Android pack can set
`export_options = {"permissions/vibrate": "true"}`.

## Precedence and conflicts

1. The authored project file is the base, including Godot feature-qualified settings.
2. The add-ons an operation contains and its project contribute `settings` and
   `autoloads`, merged per operation in the add-ons' dependency order, the project's
   last. Equal contributions compose; differing values require project
   `setting_overrides` or `autoload_overrides`. Resolved contributions
   replace selected base-file keys. Imports see only the project's own settings.
3. Project `settings_from_flags` replace their keys in every export and source run of the
   project; see [settings from build settings](#settings-from-build-settings).
4. Pack `settings` replaces selected keys for that export. It does not change imports,
   editor initialization or another pack, and cannot resolve a conflict between
   contributions.
5. `preset_settings` and `export_options` configure their own namespaces. They are not
   additional Project Settings layers. Godot supplies omitted registered defaults.

Use `main_scene`, `autoloads` and the editor parts of add-ons for those declared relationships;
the dictionaries reject attempts to bypass their membership checks. Godot resolves
feature-qualified settings, such as `key.mobile`, `release/channel.integration_test` or a
test runner add-on's `application/run/main_scene.gdunit_host`, in the running game, whose
custom features come from the [project's build settings](#custom-features); scripts read
them with `ProjectSettings.get_setting_with_override()`.

An explicit pack version/export option takes precedence over the `app_version` and
`build_number` build settings, followed by Godot's fallback. See
[version and build number](platforms.md#version-and-build-number).

## Custom features

A product variant, such as a build channel or a capability, is Bazel configuration. The
project names the build settings whose values are its Godot custom features; a build chooses
their values, and `select()` on the same settings decides what the variant contains:

```starlark
load("@bazel_skylib//rules:common_settings.bzl", "bool_flag", "string_flag")

string_flag(
    name = "channel",
    build_setting_default = "development",
    values = ["development", "internal", "production"],
)

bool_flag(name = "debug_tools", build_setting_default = False)

config_setting(name = "with_debug_tools", flag_values = {":debug_tools": "true"})

godot_project(
    name = "game",
    project_file = "project.godot",
    custom_features = [":channel", ":debug_tools"],
)

godot_resources(
    name = "app",
    deps = [":core"] + select({
        ":with_debug_tools": [":debug_tools_module"],
        "//conditions:default": [],
    }),
)
```

```bash
bazel build //path/to:app --//path/to:channel=internal --//path/to:debug_tools
```

| Setting | Custom feature |
|---|---|
| string, such as `channel=internal` | its value, `internal`; none when empty |
| boolean, such as `debug_tools` | its own name, `debug_tools`, when true |

- Every pack of the project exports with these tags, and every source run (`godot_run`,
  `godot_test` from sources) starts with them, so `OS.has_feature("internal")` and
  feature overrides such as `key.debug_tools` see them alike. The editor and the build's own
  Godot processes never have them, so a variant reuses the imports of every other.
- A variant is chosen per build, on the command line or in a `.bazelrc` configuration such
  as `build:internal --//path/to:channel=internal --//path/to:debug_tools`; two variants of one
  project are two builds.
- Feature overrides with custom tags, in `project.godot` or in contributed and pack
  `settings`, keep Godot's meaning. A pack or source run that has the tag needs the files
  such an override names; one without the tag does not. Contents vary only by `select()`:
  an override adds no file.
- A tag consists of letters, digits, `_` and `-`, and is none Godot or the configuration
  sets: an operating system, CPU, variant, `device`, `simulator` or one of Godot's own tags
  such as `mobile` or `editor`.

## Settings from build settings

A value that changes per build, such as a build number, a commit hash or a server URL, is
a build setting. The project names the build settings whose values become project settings,
and a build passes the values:

```starlark
load("@bazel_skylib//rules:common_settings.bzl", "string_flag")

string_flag(name = "commit", build_setting_default = "")

godot_project(
    name = "game",
    project_file = "project.godot",
    settings_from_flags = {
        "@autoload_rules_godot//godot:build_number": "application/config/build_number",
        ":commit": "application/config/commit",
    },
)
```

```bash
bazel build //path/to:app --@autoload_rules_godot//godot:build_number=57 --//path/to:commit=$(git rev-parse HEAD)
```

A script reads them with `ProjectSettings.get_setting("application/config/build_number")`.

| Build setting | Project setting |
|---|---|
| string, such as `commit=4f2a` | the string `"4f2a"`, also when empty |
| integer, such as `build_number=57` | the integer `57`, also when 0 |
| boolean | `true` or `false` |

- Every pack of the project exports with the values, and every source run starts with
  them. Imports, the editor, validations and the other actions of a build never read them,
  so a new value reruns only exports.
- The values replace the authored ones; pack `settings` replace the values. A key may
  carry a feature tag, such as `network/server_url.debug_tools`.
- A key is set by one build setting. A contributed or project setting of the same key, or
  a feature override of it in `project.godot` or in contributed settings, fails the build:
  it would conflict with the value or hide it where its tag applies.
- A value is data the game reads, not a file reference: no check resolves a `res://`
  path it names, and exports render the shell assets, such as icons and splash images,
  without these values.

## Project Settings support

The rules preserve ordinary runtime settings and delegate their meaning to Godot. This
is not an exhaustive assessment of every runtime setting or every plugin's behavior.
The following families also affect the shell files and shell assets:

| Settings | Supported effect |
|---|---|
| `application/config/name`, `name_localized`, `version` | Display names, localization and version fallbacks; without a name, the app target's name |
| `application/config/icon` | Declared texture used for the generated shell assets (icons); without one, Godot's default icon |
| `application/boot_splash/image`, `bg_color` | Generated splash/launch assets and color fallbacks |
| `display/window/handheld/orientation` | Android/iOS orientation metadata |
| `rendering/renderer/rendering_method`, `.mobile` | Android Vulkan `uses-feature` entries and the iOS A12 device capability |
| `internationalization/locale/translations` | Declared translations and the localized strings of the shell files; Apple applications have localized strings only when the project has translations |
| Application runtime, input, audio and game/plugin settings | Preserved and interpreted by Godot; resource references remain declared inputs |

The rules fix `rendering/textures/vram_compression/import_s3tc_bptc` and `import_etc2_astc`
to `true` for imports and exports, replacing the authored values and their feature
overrides. Godot imports a VRAM-compressed texture in every format family whose setting is
true and, whatever the settings, in the family the importing machine's CPU prefers. With
both true, imports produce the same variants on every execution platform, whether a macOS
host, an x86_64 executor or an arm64 Linux executor runs them, and every export finds the
variants its platform needs. A pack contains only the variants of its feature tags.
Setting either to `false` in `settings`, `setting_overrides` or a contribution fails.

Export-only changes reuse imports when import inputs stay equal. Resource membership,
reachable packing and prerequisites are described in [resources](resources.md#export-membership).

## Preset Settings support

| Field | Accepted value and effect |
|---|---|
| `script_export_mode` | Integer literal `0` (source), `1` (tokens), or `2` (compressed tokens); omission uses the selected Godot default; a [written pack](resources.md#pack-forms) holds source |
| Operating system (the preset's `platform`) and CPU | Owned by `--platforms`; cannot be overridden in a dictionary |
| Preset name, runnable state and export path | Generated build details |
| Export/include/exclude filters | Generated from the pack's `deps` and `packing`; no authored filters |
| Encryption and other preset fields | Unsupported; rejected as authored inputs |

Custom features are no preset field; see [Custom features](#custom-features).

## Export Options support

Options use the names of Godot's export dialog. Godot's class reference lists those of
[Android](https://docs.godotengine.org/en/stable/classes/class_editorexportplatformandroid.html),
[iOS](https://docs.godotengine.org/en/stable/classes/class_editorexportplatformios.html)
and [macOS](https://docs.godotengine.org/en/stable/classes/class_editorexportplatformmacos.html).
An option that Bazel owns or that no workflow supports fails analysis and names the
attribute or setting to use instead. Other authored options are checked against the
**selected editor's registration and types**, including declared export-plugin options.
Registration alone does not mean the packaging effect is implemented; the table
lists the implemented effects.

| Family or keys | Supported effect or configuration owner |
|---|---|
| `texture_format/*` and exporter content options marked consumed | Godot's actual PCK export |
| Android `package/name`, category, retention/TV/backup fields | Generated manifest (shell file) |
| Android `permissions/*` | Generated permissions; permissions of the add-ons the pack contains also merge |
| Android `screen/*`, `user_data_backup/*` | Supported manifest/activity behavior and generated resources |
| Android `launcher_icons/*`, `splash_screen/*` | Generated image resources and splash configuration |
| Android `command_line/extra_args` | Additional runtime arguments through the generated Activity |
| Android `version/name`, `version/code` | Version fields of the manifest |
| Apple `application/short_version`, `application/version` | Version fields of the Info.plist |
| Apple supported `privacy/*` descriptions/localizations, tracking, collected-data and reason-API fields | Generated usage descriptions, localized strings and privacy manifest; exact fields depend on the operating system |
| iOS supported `capabilities/*`, `capabilities/additional` | Device-capability metadata |
| iOS `user_data/accessible_from_files_app`, `accessible_from_itunes_sharing` | Document-sharing metadata |
| iOS supported `icons/*`, `storyboard/*` | Generated app icons, launch image and background |
| macOS `application/icon`, `liquid_glass_icon`, `icon_interpolation` | Declared icon assets; Liquid Glass requires Xcode 26 |
| macOS category, copyright/localization, signature and `display/high_res` | Info.plist metadata and localized strings |
| macOS per-CPU minimum operating system options | Metadata; they do not rebuild or lower an imported engine's deployment target |
| Apple `application/additional_plist_content` | Strict XML dictionary merge, described below |
| Declared export-plugin options | Accepted when registration/type checks succeed; the plugin owns its content effects and dependencies |

The assessed baseline is Godot **4.7.2**. This is not full parity with every Godot
export workflow. Plugin-defined options need their own implementation and dependencies.

Additional plist content accepts additive keys and boolean overrides for
`UIRequiresFullScreen` and `UIStatusBarHidden`. Duplicate keys, unknown XML value tags,
conflicts between library fragments and protected generated identity/layout keys fail.
There is no recursive array merge. The `infoplists` of add-ons are merged by the same strict owner.

## Shell files and shell assets

Each application's shell files and shell assets are the ones Godot's exporter for its operating system
writes:
the Android manifest, launcher icons and splash screen; the iOS Info.plist, privacy
manifest, launch screen, app icons and localized strings; the macOS Info.plist, privacy
manifest, icon and localized strings. Godot decides their values from the pack's
`export_options` and the exported project's settings, with the export's feature overrides
and the defaults of the pack's Godot version, and renders the icons and splash images from
the imported textures. Values Godot's exporters do not report, such as Android app
categories or iOS app icon sizes, come from rules_godot's table for each Godot minor
version; a Godot minor version without one fails the build. An application's own file for
the same slot replaces a shell file or shell asset; see
[Replace shell files](platforms.md#replace-shell-files).

## Values that belong to Bazel

| Value or Godot option family | Set here |
|---|---|
| Operating system, CPU set and iOS environment; `binary_format/architecture` | An export platform (`godot_export_platform`) selected with `--platforms` |
| Variant (debug or release export template, or the editor) | `--@autoload_rules_godot//godot:variant`; register a matching runtime for a template |
| C++ optimization, debug info, stripping | Bazel `-c`, compiler/toolchain features, `--copt`, `--strip`, Apple symbol/stripping flags |
| A source-built engine's optimization level, LTO and virtual function elimination under `-c opt` | `--@autoload_rules_godot//godot:engine_optimize`, `engine_lto` and `engine_vfe`, or the `godot_app` attributes of the same names per application; see [optimization](engine.md#optimization) |
| APK versus AAB; Godot export-format controls | `--@autoload_rules_godot//godot:android_format=apk` or `aab` |
| Text or converted pack content | `--@autoload_rules_godot//godot:pack_conversion`; see [pack forms](resources.md#pack-forms) |
| Embedded PCK and physical bundle/executable names | App layout derived from the public target name |
| Engine, extension and platform library inputs | Typed labels and the Android and Apple library rules; components record their provenance |
| Android/Apple identity | `godot_app.application_id` |
| iOS deployment floor and device families | `ios_minimum_os_version` (default iOS 15), `ios_families` |
| Android minimum/target SDK | `android_min_sdk_version`, `android_target_sdk_version`; zero uses the Godot version's fallback (4.7: 24 and 36), and the target must be at least the minimum |
| Android compile SDK and NDK API | Toolchain inputs, chosen to be compatible with the SDK versions above |
| Android APK signing | `godot_app.android_debug_key`; the delivered AAB is unsigned |
| Android manifest placeholder values | `godot_app.android_manifest_values`, filling `${key}` in the application's and its platform libraries' manifests; keys other attributes or pack settings own are rejected |
| iOS provisioning and entitlements | Declared `ios_provisioning_profile`, `ios_entitlements` labels |
| macOS signing | `--@autoload_rules_godot//godot:macos_signing=unsigned` (default), `adhoc` or `certificate`; app-specific `macos_signing_identity` and `macos_entitlements` |
| App-only platform libraries and platform resources | `platform_deps` and `platform_resources`, selected with `select()` for Android/iOS and empty desktop branches; prefer libraries the add-ons of the pack bring |

Identity, iOS deployment and device-family Godot options can mirror these Bazel inputs,
but must agree exactly; contradictory pack options fail. These early values must be known
when Bazel analyzes the rules_android and rules_apple rules. Other Godot settings stay in
the configuration maps. Application identity belongs to app composition and pack export;
changing it does not create a separate import or extension library configuration.

## Unsupported export workflows

Explicit unsupported controls fail with their owner or a diagnostic; harmless automatic
Godot defaults do not fail simply because their effect is unused. This build uses
no Gradle, so Android `gradle_build/*` options fail; the SDK inputs above are their
supported replacement. An XR mode fails the build. Other unsupported workflows include
Xcode project generation, remote deployment, export-time script injection, encryption,
Godot signing/profile lookup, generic entitlement-option translation, notarization,
iOS `modules/camera`, iOS `application/signature`, ANGLE copying and
`storyboard/image_scale_mode`.

Applications take no raw plugin lifecycle hooks or desktop bundle injection; an
application's own manifest, themes, `Info.plist` keys, icons, launch screen and privacy
manifest replace the shell's instead, as
[Replace shell files](platforms.md#replace-shell-files) describes. Extension
support does not import Godot's Android or iOS plugins. Windows and Web exports and
.NET projects are outside this API.

Custom features take no part in choosing an extension library, which the configuration
decides.
