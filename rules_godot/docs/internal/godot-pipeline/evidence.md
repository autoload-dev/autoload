# Evidence and Experiments

**Date:** 2026-11-01. Sources below were inspected for the catalogue. F means pinned
upstream source, R the ruleset at baseline 506d045; its file links and line ranges refer to
that commit, so the code may have moved since. Named functions and line ranges explain which
mechanisms were checked.
Bazel live reference pages are identified separately from version-pinned source/probes.
This is research evidence, not completed feature acceptance.

## Pinned upstream source ledger

### S01

Repository [MODULE.bazel](../../../MODULE.bazel), [.bazelversion](../../../../.bazelversion),
[examples/MODULE.bazel](../../../../MODULE.bazel), [engine profiles](../../../godot/private/engine/profiles.bzl)
and [strict source patching](../../../godot/private/patches.bzl). Pins:
Godot 4.7.2, Bazel 9.3.0, rules_android 0.8.0, rules_apple 5.3.1.
The Godot tag resolves to ed1daf0bf001b61586d9930840f2f1394092c079 (git ls-remote);
E01 independently reports the same official binary revision. Source-built engine fixture
patches/modules remain configurable inputs. No unrecorded engine patch is assumed.

### S02

[ProjectSettings](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/core/config/project_settings.cpp#L392):
feature overrides 392–434; _load_resource_pack 585–626; _setup/config/binary/override search
652–886; global class cache refresh/get/save 1433–1481; scene group cache load/save/path
1548–1582. Startup configuration is distinct from additional-pack class/UID refresh.
Custom project_settings_override and disable_project_settings_override depend on build support.

### S03

[Main entry](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/main/main.cpp#L4319):
explicit script/check-only dispatch 4319–4388 and SceneTree autoload startup 4496–4567;
editor flag controls override handling in setup. [GDScript reload](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/modules/gdscript/gdscript.cpp#L803)
parses/analyzes/compiles and can run static initialization. Runtime compilation need not be
a persistent output file.

### S04

[EditorFileSystem](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/editor/file_system/editor_file_system.cpp#L260):
first scan/classes/extensions ordering 260–366; filesystem_cache10 and reimport tests
553–747; UID sidecar generation 1320–1404; scene-group updates 2302–2377 (not command-line
mode); group import 2617–2777; _reimport_file options/defaults/generator/outputs 2813–3068;
ignored/nested project membership 3488–3509.

### S05

[ResourceUID](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/core/io/resource_uid.cpp#L113):
generic randomness/path-seeded generation and collision loop 113–155; registry/cache IO
272–390, including merge semantics. Path seed uses project name, lowercased path and source
MD5. Registry state participates; this is not a universal content-only identifier.

### S06

[ResourceFormatImporter](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/core/io/resource_importer.cpp#L43):
remap/feature selection 43–152 and import base-path construction 541–547.
[Editor paths](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/editor/file_system/editor_paths.cpp#L132) cover self-contained markers/roots;
[editor settings](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/editor/settings/editor_settings.cpp#L1342) versioned settings loading.
[Blender importer](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/modules/gltf/editor/editor_scene_importer_blend.cpp#L54)
reads executable settings/executes external tools.
[Texture importer](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/editor/import/resource_importer_texture.cpp#L231)
uses compression settings/variants and editor products (also 1010–1075).
[Scene importer](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/editor/import/3d/resource_importer_scene.cpp#L3396)
handles post-import callback scripts.
[EditorImportPlugin reference](https://docs.godotengine.org/en/4.7/classes/class_editorimportplugin.html)
describes dependency/generated-file/platform-variant/group contracts.
These examples establish classes of extension dependencies, not an audit of every importer.

### S07

[ShaderRD](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/servers/rendering/renderer_rd/shader_rd.cpp#L150):
source/defines/API/hash inputs 150–213 and cache IO 603–699. Renderer cache differs from
resource import cache. This does not establish identical behavior for all renderer backends.

### S08

[Editor export engine](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/editor/export/editor_export_platform.cpp#L1319):
selection/filters/encryption/plugins/customization 1319–1518; import variants/remaps/resource
conversion 1526–1800; project.binary/filtered class/UID/extension metadata 1801–1928;
optional shared-object collection 1930; export_pack 2464; patch export 2474.
[Preset storage](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/editor/export/editor_export.cpp#L270) loads preset/credential files
(270–443); [preset resolution](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/editor/export/editor_export_preset.cpp#L72)
applies project settings/features. [PC exporter](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/editor/export/editor_export_platform_pc.cpp#L94)
uses templates and collects/copies native shared objects for full application export.
[Android exporter](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/platform/android/export/export_plugin.cpp#L2863)
illustrates conditional keystore/environment/application export inputs; the baseline ruleset
delegates APK/AAB construction to Bazel instead of this full application exporter.

### S09

[GDExtension exporter](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/editor/export/gdextension_export_plugin.h#L46):
descriptors/AAR marker, feature libraries/shared objects, Apple registration/static hooks and
dependent libraries (46–168).
[Library loader](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/core/extension/gdextension_library_loader.cpp#L40):
feature dependency choice 40–71, optional prefix/directory autodetection 99–155,
physical operating-system library loading 176–208, entry/init/version/reload checks 224–385.
[Manager](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/core/extension/gdextension_manager.cpp#L44):
explicit lifecycle 44–151 and extension-list/platform startup 323–410.
Neither extension library bytes in a PCK nor mounting a new extension list alone causes
operating-system load/registration.

### S10

[GDScript export plugin](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/modules/gdscript/register_types.cpp#L83)
emits remapped .gdc tokenizer buffers, optionally ZSTD-compressed (83–120).
Use “token buffer”, not VM/native bytecode.

### S12

[Shader baker export plugin](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/editor/export/shader_baker_export_plugin.cpp#L56):
RendererRD/feature gate, driver/settings/resources, customization cache, emitted shader files
and container compiler (56–270, 373–458).
[Encrypted file access](https://github.com/godotengine/godot/blob/ed1daf0bf001b61586d9930840f2f1394092c079/core/io/file_access_encrypted.cpp#L44) uses random IV without an
explicit IV. Export engine encryption seed handling 377–429 and encryption environment-key
override 1139–1145 are conditional inputs. Source-backed capabilities do not imply exposure
by the baseline wrapper preset/environment.

### S13

[Pinned GdUnit scanner](https://github.com/godot-gdunit-labs/gdUnit4/blob/0127a55f4543dfc24746f6e5c7ba6f94105d51f2/addons/gdUnit4/src/core/GdUnitTestSuiteScanner.gd#L32):
global class metadata/scanning 32–133 and suite inheritance 234–247.
Candidate resource roots, dependency availability and recognized suites are distinct.

## Repository implementation ledger

### R01

[Project/resources](../../../godot/private/project.bzl): resource paths/deps/import inputs/
import unit metadata 253–329; per-import-unit action declaration 750–822; full project
imports/init/provider 839–1061; pack selection/export/shell input registration 1199–1412.
[Providers](../../../godot/providers.bzl) describe the contracts.
Whole-project memberships here are implementation facts, not desired minimum dependencies.

### R02

[Per-purpose configuration](../../../godot/private/project_config.py#L179), especially 227–250:
drops import autoload/editor-plugin section, main scene, resource-reference-valued settings
and inactive feature overrides, then reconstructs per-purpose plugin lists.
[Godot staging](../../../tools/godot_staging.py): staging/extensions 194–258; child environment
272–294. [Godot project actions](../../../tools/godot_actions.py): scan/conversion/output
capture 31–106; importer/feature probes 109–176. [Godot exports](../../../tools/godot_export.py):
generated presets 231–279; export lock/workspace 332–357; pack staging/rescan/export/report 393–433.
Per-import-unit output retention is .godot/imported changes + own sidecars; initialization captures
changed staged-project files. Custom output paths/alternative project-data layout need review.

### R03

[Editor and sidecar rules](../../../godot/private/editor.bzl),
[editor tool](../../../tools/godot_editor.py) and
[sidecar extraction/write/check](../../../tools/godot_metadata_sync.py).
Editor uses checkout links/copies and inherited environment; generated/source files have
different writeback ownership. Missing-sidecar writer does not overwrite existing files.

### R04

[Run rules and launcher](../../../godot/private/run.bzl) 21–148 and
[runner](../../../tools/godot_run.py) 245–365:
source full project imports/init/runfiles, main-pack-only extension library staging, extra PCK
delivery, explicit env plus test variables, report publishing.
[Test adapter](../../../godot/private/adapter.bzl),
[GdUnit adapter](../../../../addons/gdunit/gdunit/private/gdunit_test.bzl) and
[GdUnit test adapter script](../../../../addons/gdunit/gdunit/private/run.gd) show case selection/framework/report policy.

### R05

[Extension construction](../../../godot/extension/defs.bzl),
[desktop backend](../../../godot/platforms/private/desktop.bzl),
[Android](../../../godot/platforms/private/android.bzl),
[iOS](../../../godot/platforms/private/ios.bzl),
[macOS signing](../../../godot/platforms/private/macos_signing.bzl),
[shell file writers](../../../godot/platforms/private/shell.bzl),
[symbol rules](../../../godot/private/symbols.bzl),
[native symbol tool](../../../tools/platforms/native_symbols.py) and
[signing tool](../../../tools/platforms/sign_macos.py).
Editor and runtime extension providers, transitive native code/resources/manifests/plists,
ABI/Swift/framework aspects, strip/dSYM/UUID preservation and signing locality are distinct
edges.
macOS certificate signing has no-cache/no-sandbox/no-remote; adhoc still no-remote.

### R06

[Graph declaration](../../../godot/private/graph.bzl),
[graph inspection rule](../../../godot/private/analysis.bzl),
[scanner/selector](../../../tools/resource_graph.py):
analyzed/opaque/leaf classes 1–75, runtime/import input validation and unknown dynamic refs,
selection 1091 onward. Static scanning does not dynamically declare new Bazel inputs.
[Pack format inspection](../../../tools/pck.py) validates the PCK structure.

### R07

[Engine components](../../../godot/engine/private/components.bzl),
[engine source repositories](../../../godot/engine/private/source_repositories.bzl),
[engine generators](../../../godot/engine/private/generator.bzl) and
[patch handling](../../../godot/private/patches.bzl).
Archive/checksum, module trees, ordered patches, host configure tools/imported env,
generator source/stamp and native compilation/link inputs feed actual executable identity.

### R08

[Shell assets](../../../godot/private/shell_assets.bzl),
[probe export script](../../../tools/action/shell.gd),
[action plugin](../../../tools/action/plugin.gd),
[engine profiles](../../../godot/private/engine/profiles.bzl) and
[export shell mode](../../../tools/godot_export.py#L120).
Probe reports actual defaults/settings/feature tags; engine profiles supply remaining versioned
tables.
The shell-assets action does not parse the already generated main PCK as its input.

## Bazel mechanism sources

### B01

[Bazel 9.3 aspects](https://bazel.build/versions/9.3.0/extending/aspects):
actions/providers attach to configured dependency graph applications.
A resource-reference graph and a configured aspect/action graph are different mechanisms.

### B02

[Bazel configurations](https://bazel.build/extending/config) and
[action APIs](https://bazel.build/rules/lib/builtins/actions.html):
label settings/transitions, configuration growth, declared actions/tree-directory expansion.
These live references describe Bazel mechanisms, not pinned Godot facts or proof that an
automatic Godot import-sharing design is correct.

### B03

[Bazel test environment](https://bazel.build/reference/test-encyclopedia) and
[remote caching](https://bazel.build/remote/caching):
declared dependencies/runfiles/temp/report environment and cache validity.
Artifact equality does not account for untracked device/network/keychain/live
operating-system state.

## Bounded experiments

### E01

**New cold-import observation, 2026-11-01.** Two empty, separately isolated projects used
the existing official executable reporting 4.7.2.stable.official.ed1daf0bf. Each ran
`--headless --path <absolute-probe-project> --editor --import`; the placeholder is replaced
with that fresh project directory. Both returned 0. Environment used the baseline wrapper's
child_environment, which isolates HOME/TMPDIR/XDG roots and fixes locale/TZ.

Each project had identical probe.gd (`class_name CatalogProbe`, then `extends RefCounted`)
and an identical 8×8 red-rectangle SVG. Configuration was config_version=5, rendering method
gl_compatibility and application/config/name of CatalogAlpha or CatalogBeta. No authored
.uid/.import, addons or preset were supplied. The varying physical root is not claimed
independently controlled; S05 establishes which logical inputs participate in UID generation.

Observed generated files:

- .godot/.gdignore
- .godot/editor/filesystem_cache10 and project_metadata.cfg
- .godot/global_script_class_cache.cfg and uid_cache.bin
- .godot/imported/icon.svg-218a8f2b3041327d8a5756f3a245f83b.ctex and its .md5
- icon.svg.import and probe.gd.uid

Observed script UIDs were uid://c6xegu6cd1byq (Alpha) and uid://cbklui350ya1c (Beta).
Class cache and converted .ctex/.md5 bytes matched; project config, source sidecars,
filesystem cache and UID cache differed. Source files were identical. This is a narrow
observation, not proof all project-name changes leave converted bytes unchanged or all
UIDs are deterministic. No group/extension library/shader/export/mobile behavior was exercised.

Local receipts: /private/tmp/godot-pipeline-probes/result.json and each case's import.log.
The recipe/results are recorded here so conclusions do not depend on temporary files surviving.
