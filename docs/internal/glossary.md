# Glossary

The terms this repository uses in code, documentation, commits, reviews and conversation.
Paths in the "In code" columns are relative to `rules_godot/`. Paths and labels of the root
module start with `//`, such as `//tools/ci/work.py`; `.aspect/`, `.github/` and `addons/`
paths start at the repository root; the ruleset's labels start with `@autoload_rules_godot`.

## How this glossary works

- **One entry per concept**, under its preferred term. "Not to be confused with" names a
  contrasting concept, which has its own row, only where readers mix the two up.
- **Headwords.** A term that prose writes as a compound, such as worktree slot, is its own
  headword. A word that prose uses bare in several senses has one entry per sense, with the
  context in parentheses, such as `slot (engine)`. [Words with several
  meanings](#words-with-several-meanings) lists these words, the sense the bare word carries
  and the question that tells the senses apart.
- **Meaning** defines the concept in one or two sentences. Mechanics, reasons and procedures
  belong to the page that owns them, which the entry links.
- **In code** names identifiers and paths that carry the term, all of which exist. A label a
  macro generates is written as `<name>.<suffix>`.
- **What belongs here.** A term enters when one of these holds: it means something of its own
  here, or something narrower than in Bazel or Godot; it collides with another meaning; prose
  in three or more files uses it, or a public API is named after it. A term that only code
  uses and one docstring explains stays in that docstring. Bazel's and Godot's terms in their
  own sense stay out, unless an entry must be told apart from them.
- **[Terms to avoid](#terms-to-avoid)** lists the forms to replace, each with its replacement,
  the reason and the code that still uses it. A row without a context in parentheses applies
  everywhere outside code; a row with one needs a reviewer's judgment. A form joins the list
  after an actual or likely confusion. A renamed term stays there with its successor.

## Naming rules

Reviewers apply these rules to the names of fields, attributes, targets and other identifiers.

- Name an identifier after the term this page gives its concept.
- Name a rules_godot provider value after its term: `pack`, `extension`, `project`,
  `resources`, `runtime`, `desktop_app`, never `info` or `*_info`. A File inside it takes a
  qualifier, such as `pack_file` or `runtime_executable`; a list takes the plural or its
  role, such as `dependencies` or `importers`.
- When a provider or rule has two fields or attributes of the same kind, qualify both names,
  such as `runtime_resource_paths` and `editor_resource_paths`, unless the difference between
  the two is obvious. A dict of
  resource paths to Files is `*_resource_paths`; a list of paths is `*_paths`.
- `runtime_` qualifies what the runtime loads, `editor_` what the editor loads. The extension
  library fields use them without an `extension_` prefix: `GodotExtensionInfo` and the
  extension rules already say whose library it is.
- `engine` names checks of engine files of either role, such as `check_engine` and the
  mnemonic `GodotEngineVersion`.
- `target` names only Bazel targets, never the runtime side; `native` names only compiled code
  and Bazel's `native.*` module ([Words with several meanings](#words-with-several-meanings)).
- Write terms out: `operating_system`, `operating_systems`, `cpu`, `cpus`; never `os`, `oses`,
  `arch` or `architecture`.
- Tests, test files and fixtures are named by the verification architecture's
  [naming](verification-architecture.md#naming) rules.
- A name in upstream terms keeps them, even where it breaks a rule above:
  - Bazel's and Godot's own names, such as `@platforms//os`, SCons's `arch=` and the export
    options `binary_format/architecture` and `architectures/*`.
  - `build_target` of `godot_engine_build` and `--build-target` of
    `tools/engine/configure.py`, after SCons's `target=`.
  - `godot_app.ios_minimum_os_version`, after rules_apple's `minimum_os_version`.
  - The export platforms `ios_sim_arm64` and `ios_sim_x86_64`, after apple_support's
    platforms.
  - `binary` for an executable, as in `godot_editor_archive.binary`, `prebuilt_editor.binary`,
    `prebuilt_runtime.binary` and `godot_engines.binaries.editor_binaries`, after Godot's
    release archives. Prose says editor executable or runtime executable.
  - `<name>.native_apk` and `<name>.native_bundle`, rules_android's outputs.

## Words with several meanings

The bare word carries the sense in bold; every other sense is written with its qualifier.

| Word | Senses | Ask |
|---|---|---|
| check | **check (repository)**; content validation, a check of the build | Does `aspect check` run it, or a build? |
| component | **engine component**; released module, never called a component; Godot's scene components; Android SDK components | Does it fill an engine's slot? |
| editor | **editor (executable)**; editor view; editor part; editor variant; the `editor` purpose and feature tag | Is it a program, a directory, files of an add-on, or a configuration? |
| extension | **extension (GDExtension)**; a Bazel module extension such as `godot_engines`; a file suffix | Does it have a `.gdextension` descriptor? |
| hook | export hook; Git hook; an agent's hook | Does Godot, Git or an agent call it? |
| import, export | **import (Godot)**, **export (Godot)**; Python's `import`, Bazel's `exports_files` | Does the Godot editor do it? |
| lock file | **lock file (engine)**; `MODULE.bazel.lock`; Maven's `maven_install.json` | Does it hold recipe pins? |
| member | **member (operation)**; a member of an archive or PCK | Does an operation's selection reach it? |
| module | **Bazel module**; engine module; a Python or Starlark source module | Does it have a `MODULE.bazel`? |
| native | **native**, compiled code (C, C++, Objective-C, Swift, Java through JNI) and its libraries, and Bazel's `native.*` module; every other sense has its own term: extension, extension library or platform library, Bazel's built-in, evaluated, shell | Is it compiled code, or Bazel's `native.*`? |
| owner | **owner (declaration)**; option owner; the page that owns a fact | Is it the label of the target that declared something? |
| platform | platform (Godot); platform (Android, Apple); Bazel's execution, target and export platforms, always qualified | Is it Godot's operating system, Android or Apple, or a Bazel `platform()`? |
| profile | **build profile**; engine profile; Bazel profile | Is it a `.gdbuild` file, per-minor tables, or an output base? |
| project | **project (target)**; project context; Godot project (directory) | Is it a `godot_project` target, a build setting, or a directory? |
| role | role (engine); role (add-on) | Does it tell editor from runtime, or importer from editor tooling? |
| row | **row (source recipe)**; a row of a table | Does a source recipe build it? |
| runner | **runner (launcher)**; runner (CI) | Does a launcher start it, or does a workflow job run on it? |
| selection | **selection (operation)**; an engine's selection of components | Is it an operation's `deps`? |
| slice | **platform slice**; admitted for a slice of an XCFramework or a universal Mach-O file | Does it describe the build for one CPU, or a part of one binary? |
| slot | **slot (engine)**; worktree slot; a shell default's slot | Does a component fill it, or does a checkout lease it? |
| target | **target**, a Bazel target; target platform; never the runtime side, which `runtime_` names | Is it something Bazel builds from a label? |
| task | **task (Aspect)**; a Gradle task | Is it defined in `.aspect/*.axl`? |
| unit | **import unit**; a unit test | Do the files of one `godot_resources` target make it up? |
| variant | **variant**; template variant; profile variant; Godot's `Variant` type | Is it `release`, `debug` or `editor`? |
| view | **view (operation)**; editor view; tool view | Is it `<name>.view`, a directory, or an extension's target in the tool configuration? |

## Platforms and operating systems

| Term | Meaning | Not to be confused with | In code |
|---|---|---|---|
| host | The machine Bazel runs on, such as your Mac; `bazel run` starts its binary here. | The execution platform; a host job. | `@platforms//host`, `HOST_CONSTRAINTS` |
| execution platform | The Bazel platform build actions run on: the host locally, the remote executors' platform with remote execution. | The host; the target platform, Bazel's platform of the outputs; a remote executor, a machine of a remote execution service. | `cfg = "exec"`, `--extra_execution_platforms` |
| platform (Godot) | Godot's name for an operating system it builds and exports for, as in SCons's `platform=`. rules_godot uses it only in the engine configuration: components, recipes and prebuilt archives. | A Bazel platform; an operating system, the word everywhere else; Godot's preset platform name, such as `iOS`, which is `preset_platform`. | `platform` of `godot_editor_component`, `godot_runtime_component`, `GodotComponentInfo` |
| operating system | What a pack, application or extension library is for: `linux`, `macos`, `android` or `ios`. | A Bazel platform, which also fixes the CPU. | `operating_system` of `GodotPackInfo`, `GodotDesktopAppInfo`, `GodotExtensionInfo.library` |
| CPU | The instruction set a build is for, Bazel's `@platforms//cpu`. Inside, rules_godot names it by Godot's CPU tag, such as `arm32`; Godot calls it architecture. | An Android ABI, such as `arm64-v8a`; Bazel's `--cpu` values. | `cpu`, `cpus`, `CPU_TABLE` in `godot/private/config/settings.bzl` |
| environment (iOS) | `device` or `simulator`: the Apple environment of an iOS export platform. | An SDK installation; the Apple build platform a Mach-O file records, which code calls `sdk`. | `@autoload_rules_godot//godot/private/config:environment`, `godot_export_platform.environment` |
| export platform | A target platform declared with `godot_export_platform`: an operating system, a set of CPUs and, for iOS, an environment. | Godot's export platform, which is only the operating system. | `godot_export_platform` in `godot/platforms/defs.bzl` |
| platform slice | The part of an export platform that builds for one of its CPUs, a target platform of its own; a desktop export platform is its own single platform slice. | A slice of an XCFramework or a universal Mach-O file. | `@autoload_rules_godot//godot/private/config:platform_slices`, `<name>.platform_slice_<cpu>`, `platform_slice_transition` |
| variant | `release`, `debug` or `editor`: which of Godot's binaries a build is for, after Godot's build targets. | C++ optimization (`--compilation_mode`); the role of an engine component. | `--@autoload_rules_godot//godot:variant`, `variant` of `godot_runtime_component` |
| template variant | `release` or `debug`, the variants of Godot's export templates, which select the runtime, the export's feature tags and the source-built extension libraries. | The editor variant. | `variant` of `prebuilt_runtime`, `GodotRuntimeInfo` |
| editor variant | The variant `editor`, in which a `godot_app` runs its start pack's project from sources with the editor executable ([the editor variant](../../rules_godot/docs/public/platforms.md#the-editor-variant)). | The editor platform; the `editor_runtime` feature tag. | `@autoload_rules_godot//godot:editor`, `godot_source_application` in `godot/private/run.bzl` |
| feature tag | Godot's name for a property of a running engine, such as `linux`, `arm64`, `debug` or `editor_runtime`; a descriptor lists each library under a set of them. | A Bazel feature, which configures rules_cc toolchains. | `GodotExtensionInfo.library.tags`, `_RESERVED_FEATURE_TAGS` |
| custom feature | A feature tag that a project's build settings give in a configuration ([custom features](../../rules_godot/docs/public/configuration.md#custom-features)). | A feature tag that a platform slice fixes. | `godot_project.custom_features` |
| tool configuration | The build configuration in which Godot runs as a build tool: imports, initialization, exports and the editor. | The `editor` purpose; the editor variant, which runs a project on the target platform. | `@autoload_rules_godot//godot:tool`, `tool_transition` |
| content configuration | The one configuration in which a pack exports for all its platform slices. Everything it exports must agree across them, except the extension descriptors. | The configuration of a platform slice. | `content_transition` in `godot/private/config/transitions.bzl` |

## Engine

| Term | Meaning | Not to be confused with | In code |
|---|---|---|---|
| engine | Godot as `godot_engines.engine` registers it under an engine name: its archives or source recipes, its hub and its components ([engines](../../rules_godot/docs/public/engine.md)). | The Godot version; one engine component. | `godot_engines.engine` |
| engine name | The name that keeps an engine apart; its components fill slots only for targets that select it ([name an engine](../../rules_godot/docs/public/engine.md#name-an-engine)). | The Godot version. | `--@autoload_rules_godot//godot:engine`, `engine` of `godot_app` |
| default engine | The engine registered with `default = True`, which serves targets that name no engine. | An engine without a name. | `@autoload_rules_godot//godot:default_engine` |
| editor (executable) | The Godot editor executable, which the build runs to import, initialize and export projects and to start source runs. | The editor view; an add-on's editor part. | `@autoload_rules_godot//godot:editor_toolchain_type` |
| runtime | The engine an application ships: Godot's export template for one platform slice and template variant. | The `runtime` purpose; an add-on's runtime part. | `@autoload_rules_godot//godot:runtime_toolchain_type`, `GodotRuntimeInfo` |
| role (engine) | Whether an engine component is the editor or the runtime. | The variant; the role of an add-on. | `role` of `GodotComponentInfo` |
| engine component | A declaration that fills one slot with the editor or a runtime: its payload and its toolchain registration. | A released module; Godot's scene components. | `godot_editor_component`, `godot_runtime_component`, `GodotComponentInfo` |
| slot (engine) | One combination of role, platform and CPU and, for runtimes, iOS environment and variant, which a component of the selected engine fills ([replace slots](../../rules_godot/docs/public/engine.md#replace-slots)). | A platform slice; a worktree slot; a shell default's slot. | `--extra_toolchains` |
| payload | The engine files a component declares: an editor executable, or a runtime's executable or libraries with the files it needs beside them. | Extension libraries. | `ToolchainInfo.godot.payload`, `GodotRuntimeInfo.bundle_files` |
| provenance | Where a component's payload comes from: its kind, version, origin, digest and customizations, for diagnostics. | Bazel's build provenance. | `ToolchainInfo.godot.provenance` |
| registration set | A package of components registered together through its `:all` target ([replace slots](../../rules_godot/docs/public/engine.md#replace-slots)). | An engine. | `@<name>//toolchains:all`, `@godot_engines_toolchains//:all` |
| hub | The repository `@<name>` that `godot_engines` generates for an engine, with one component per valid slot. | A registration set of your own. | `godot/engine/private/hub.bzl` |
| editor platform | The operating system and CPU an editor executable is built for. | The export platform. | `EDITOR_PLATFORMS` in `godot/engine/private/catalogue.bzl` |
| prebuilt engine | An engine whose components come from Godot's release archives or another pinned archive of executables and templates. | A source-built engine. | `godot_engines.binaries`, `GodotComponentInfo.kind` |
| source-built engine | An engine whose components source recipes compile; one engine can be prebuilt for some slots and source-built for others. | A prebuilt engine; the Source engine workflow. | `godot_engine_build`, `GodotComponentInfo.kind` |
| official engine | A prebuilt engine from Godot's own releases, which the engine catalogue pins per catalogued version. | A prebuilt engine from another archive. | bazelrc config `official` |
| engine catalogue | The table of the Godot versions rules_godot supports, with the pinned editors and export templates of their official releases. | The [conventions catalogue](conventions.md). | `godot/engine/private/catalogue.bzl` |
| source archive | One pinned archive of Godot's sources. | The engine tree. | `@godot_source_<digest>` |
| engine tree | One source archive's Godot sources, extracted once with SCons added and made read-only, whose files every source recipe of that archive links. | The source archive; a recipe's repository. | `godot_engine_tree`, `tools/engine/tree.py` |
| engine module | A Godot C++ module under `engines/<name>/modules/` that a source recipe compiles into the engine. | A Bazel module. | rule [engine-files-under-engines](conventions.md#engine-files-under-engines) |
| source recipe | One engine build from pinned Godot sources with the engine's modules, patches and options, for one row. | A prebuilt engine. | `godot_engine_build`, `@<name>_<row>` |
| row (source recipe) | One valid combination of platform, CPU, iOS environment and build target, for which an engine that builds from source declares one source recipe. | A slot, which a row's recipe fills. | `godot/engine/private/source_build_rows.bzl` |
| build policy | The modules, patches and options every source recipe of an engine shares. | A source recipe; a build profile. | `godot_engines.build`, `godot_engines.editor` |
| recipe pin | A source recipe's configured build graph with the digest of what that graph depends on ([pin the recipes](../../rules_godot/docs/public/engine.md#pin-the-recipes)). | A Bazel lock file. | `@<recipe>//:pin`, `tools/engine/pin.py`, mnemonic `GodotPinRecipe` |
| lock file (engine) | The file that holds the recipe pins of an engine's source recipes. | `MODULE.bazel.lock`; `maven_install.json`. | `lock_file` of `godot_engines.engine`, `@<name>//:pin`, `@<name>//:pinned` |
| build profile | Godot's `.gdbuild` file: engine classes and build options to leave out, which an application's runtime applies; its build options need a profile variant ([build options](../../rules_godot/docs/public/engine.md#build-options-in-a-build-profile)). | Bazel's `--profile`; godot-cpp's build profile of an extension; the engine profile. | `build_profile` of `godot_app`, `godot_runtime_profile`, `godot_engines.runtime_profile` |
| profile variant | A source recipe's build graph configured with the build options of a registered build profile, beside the recipe's own graph and with its own pin. | A variant; a separate engine. | `tools/engine/variants.py`, `@<recipe>//:pin_variant_<n>` |
| engine library | The engine compiled as a library: Android's `libgodot_android.so` and iOS's static library. | Extension libraries. | `godot_android_runtime.engine_library`, `@<recipe>//:engine_library` |
| Android shell library | Godot's Java and Kotlin library (an AAR), the Android part of the shell. | The engine AAR. | `godot_android_shell` |
| engine AAR | The AAR an Android application packages: the Android shell library with the slot's engine library. | The Android shell library as Godot ships it. | `<name>.engine_aar` |
| shell | The native application code around the engine: the Android shell library, and on every operating system the shell files and shell assets an application rule writes. | The host; a command shell such as `sh`. | `godot_android_runtime.shell` |
| shell file | A file application rules write for the shell from what Godot decides for the export, such as a manifest, a theme, an `Info.plist` or Android's command line file `assets/_cl_`. | A file of the project. | `godot/platforms/private/shell.bzl`, mnemonic `GodotShellFile` |
| shell asset | An icon or splash image application rules write for the shell from the export. | A platform resource. | `godot/private/shell_assets.bzl`, mnemonic `GodotShellAssets` |
| shell default | A shell file or shell asset as the shell writes it for its slot, such as an Android resource, a top-level `Info.plist` key or the app icons. | A slot of an engine. | `godot/platforms/private/shell.bzl` |
| shell override | A file an application supplies in place of a shell default ([platforms](../../rules_godot/docs/public/platforms.md)). | A patch of a shell file; an export option. | `godot_app.android_manifest`, `ios_infoplists`, `tools/platforms/shell_overrides.py` |
| template activity | Godot's `com.godot.game.GodotApp`, the activity of Godot's Android Gradle template, which an Android application runs unchanged ([Android shell](../../rules_godot/docs/internal/android-shell.md)). | Godot's `GodotActivity` base class. | `template_activity` of the engine profile |

## Projects and resources

| Term | Meaning | Not to be confused with | In code |
|---|---|---|---|
| resource path | Where a file appears inside the Godot project: its project-relative path without the `res://` prefix, such as `levels/one.tscn`; with the prefix it is a `res://` path. | A workspace or execroot path. | `godot_extension.resource_path`, `godot_resources.resource_paths` |
| resources | A `godot_resources` target: files with their resource paths, the resources they depend on and the add-ons their files use; prose may say resources target. | Godot's `Resource` class; platform resources; an add-on. | `godot_resources`, `GodotResourcesInfo` |
| add-on | A directory of a Godot project declared once with its parts and what it brings ([add-ons](../../rules_godot/docs/public/resources.md#add-ons)); an extension by itself is an add-on of only that extension. | Resources; Godot's editor plugin, only the editor part; an add-on module. | `godot_addon`, `GodotAddonInfo` |
| runtime part | The files of an add-on that every operation containing it treats as members. | The runtime. | `godot_addon.srcs`, `GodotAddonInfo.runtime_files` |
| editor part | The `plugin.cfg` of an add-on and the files its editor plugin loads, which only the Godot processes of its roles stage. | The editor executable. | `godot_addon.editor_srcs`, `GodotAddonInfo.editor_files` |
| role (add-on) | What an add-on's editor part does for a build: importer or editor tooling. | A purpose; the role of an engine component. | `godot_addon.importer_suffixes` |
| importer | An add-on whose editor part converts files of its suffixes ([importers](../../rules_godot/docs/public/resources.md#importers)). | Godot's built-in importers. | `GodotAddonInfo.importer_suffixes` |
| used add-on | An add-on in the `deps` of resources whose files use it, which every operation containing them contains. | A dependency on other resources, which imports first. | `GodotResourcesInfo.addons`, `classify` in `godot/private/resources.bzl` |
| named add-on | An add-on a project lists in its `deps` because no content uses it, such as an editor-only add-on. | A used add-on. | `GodotProjectInfo.named_addons` |
| contribution | An autoload, setting or Info.plist fragment an add-on or a project declares ([precedence](../../rules_godot/docs/public/configuration.md#precedence-and-conflicts)). | A pack's own `settings`. | `GodotAddonInfo.autoloads`, `settings`, `platform_contributions` |
| project (target) | A `godot_project` target: the configuration of a product, with its authored `project.godot`, settings, autoloads, main scene, context files and named add-ons, but no resources. | A Godot project directory; a view. | `godot_project`, `GodotProjectInfo` |
| project context | The project an operation's view imports its resources under, which a transition sets. | The project target itself. | `@autoload_rules_godot//godot/private:project_setting`, `godot/private/context.bzl` |
| Godot project (directory) | A directory with a `project.godot`, such as the projects of `examples/` and the consumer scenarios. | A project target. | rule [projects-at-fixed-places](conventions.md#projects-at-fixed-places) |
| context file | A file bound to a project's configuration rather than its content, such as an application icon. | A member. | `godot_project.context_files` |
| authored | Of a file: written in the checkout by a person. Generated, staged and pinned files are not authored. | | |
| operation | A target that runs Godot or reads files under a project, such as `godot_pack` or `godot_editor`, each with one project and its own selection. | A Bazel action; an application. | `declare_view` in `godot/private/view.bzl` |
| selection (operation) | An operation's `deps`: the resources and add-ons it works on, with what they depend on and use. | Pack content, what of the selection a pack contains. | `_selection` in `godot/private/resources.bzl` |
| view (operation) | The Godot project one operation runs on: its project's configuration over its selection, with imports, initialization, metadata and resource graph. | A project target; the editor view; a tool view. | `<name>.view`, `GodotViewInfo` |
| composition | What a `godot_resources` target or a view merges from its files and its dependencies. | An editor view. | `compose` in `godot/private/resources.bzl` |
| member (operation) | A file that belongs to an operation's content through its selection: a script, scene, asset or data file. | An import input; a member of an archive. | `GodotViewInfo.member_resource_paths`, `member_owners` |
| import input | A file that only the import of another file reads, such as the `.bin` buffer of a glTF model. | A member. | `godot_resources.import_inputs`, `import_owners` |
| ignored file | A file Godot's editor file system never scans: below a directory with a `.gdignore` or a `project.godot`, or hidden ([split imports](../../rules_godot/docs/public/resources.md#split-imports-at-useful-boundaries)). | A member. | `GodotResourcesInfo.ignored_resource_paths`, `godot_ignored` in `godot/private/paths.bzl` |
| owner (declaration) | The label of the target that declared a resource path, unit, setting, autoload or relationship, like Bazel's `File.owner`. | An option owner; the page that owns a fact. | `member_owners`, `import_owners` |
| relationship | A declared reference from one resource path to another, with its kind and owner. | A detected reference, which the resource graph finds in a file. | `GodotResourcesInfo.relationships` |
| resource graph | The static reference graph a view builds from its files' detected references and the declared relationships. | A Bazel dependency graph. | `tools/resource_graph/graph.py`, `godot_resource_graph` |
| import unit | The files of one `godot_resources` target that Godot imports together in one action with one cache entry. | A Bazel package; a unit test. | `GodotResourcesInfo.units`, `godot/private/import_units.bzl` |
| closure | What an import unit may use: its own files, the units it depends on and the runtime parts of the add-ons they use. | The selection of an operation. | `godot/private/import_units.bzl` |
| import (Godot) | The editor's conversion of a unit's importable assets, such as PNG to compressed textures. | Python's `import`; Bazel's `aar_import`. | mnemonic `GodotImport` |
| import result | What the import of one unit writes: an archive of the converted files and their sidecars. | The import unit. | `GodotResourcesInfo.imports` |
| initialization | The editor state an initialize action derives for a view: the global script-class and UID caches. | Godot's `_init`. | `GodotViewInfo.initialized`, mnemonic `GodotInitialize` |
| class fragment | One unit's part of the global script-class cache. | The unit interface. | mnemonic `GodotClassFragment`, `tools/resources/class_fragment.py` |
| content validation | The check of one unit's scripts and scenes under its project context, which compiles them without running their code ([content validation](../../rules_godot/docs/public/development.md#content-validation)). | A test, which runs code; the resource graph, which checks references. | `validate_unit` in `godot/private/import_units.bzl`, mnemonic `GodotValidate` |
| unit interface | What content validations of a unit's dependents read from it: its scripts without function bodies and stand-ins for its imported assets. | The class fragment. | `unit_interface` in `godot/private/import_units.bzl`, mnemonic `GodotUnitInterface` |
| export (Godot) | The editor's writing of a pack's PCK from its view. | Bazel's `exports_files`; the written pack form. | mnemonic `GodotPack` |
| pack | A `godot_pack` target and its PCK, exported by Godot or written, with extension descriptors but no extension libraries. | An application, which ships packs. | `godot_pack`, `GodotPackInfo` |
| pack form | How a pack's PCK is made: Godot's export or the written pack ([pack forms](../../rules_godot/docs/public/resources.md#pack-forms)). | The variant; `script_export_mode`. | `--@autoload_rules_godot//godot:pack_conversion` |
| packing | A pack's choice of what of its selection it contains: all of it (`deps`) or what its configuration and entry points reach (`reachable`). | Pack content, the result. | `godot_pack.packing` |
| pack content | The members a pack contains, decided from its packing and checked for references to unavailable files; the content file lists it for the packs that require this one. | The selection; the export report. | `<name>.content.json`, mnemonic `GodotPackSelection` |
| entry point | A resource path that reachable packing starts from, beside the project's main scene and autoloads. | A program entry. | `godot_pack.entry_points` |
| required pack | A pack whose content another pack may reference without containing it. | The start pack. | `godot_pack.required_packs` |
| program entry | An operation that starts the game itself: a pack without `required_packs`, or a `godot_run` with `deps`. | An entry point. | `GodotViewInfo.missing_entries`, `left_out_entries` in `godot/private/project.bzl` |
| content file | The file `<name>.content.json` that lists a pack's content for the packs that require it. | The content report. | `<name>.content.json` |
| content report | The `selection` output group of `godot_pack`: the reference chains that brought each file into a reachable pack, and the warnings of its reference check. | The export report. | `<name>.selection.json`, output group `selection` |
| export report | The `report` output group of `godot_pack`: the declared, selected, excluded and actual PCK paths. | A test report; the content report. | output group `report` |
| Godot process | One run of the Godot editor or runtime for one purpose: an import, initialization, export, probe, validation, source run or editor view. | A Bazel action or an operation, which may start several. | `run_editor_action` in `godot/private/actions.bzl` |
| purpose | A kind of Godot process, each with its own `project.godot` ([purposes](../../rules_godot/docs/public/resources.md#purposes)). | A role. | `purpose` in `tools/project/config.py` |
| source run | Starting the game from an operation's view with the editor executable, without exporting. | Running a pack or an exported application. | `godot_run`, `godot_test`, `gdunit_test` |
| editor view | The directory that `godot_editor` opens in the Godot editor UI ([editor view](../../rules_godot/docs/public/development.md#editor-view)). | The checkout; the view of another operation. | `godot_editor`, `tools/checkout/editor.py` |
| sidecar | A `.uid` or `.import` file Godot keeps beside a script, shader or asset. | The metadata index. | `GodotViewInfo.metadata` |
| metadata index | The JSON file a view writes with the UIDs its files declare and the scene node IDs it assigns. | The sidecars themselves. | `GodotViewInfo.metadata_index`, `tools/resources/index.py` |
| staging | Copying or linking files to their resource paths in the directory a Godot process uses as its project, the staged project. | Bazel's runfiles. | `tools/staging/` |
| action manifest | The JSON file that is the entire input set of one editor action. | A run manifest. | `load_manifest` in `tools/inputs/manifest.py` |
| resource path manifest | A JSON file that lists the execroot path of each resource path of a target. | A run manifest. | `GodotResourcesInfo.resource_path_manifests` |
| run manifest | The JSON file a launcher passes to the runner, which stages the project from it. | An Android manifest. | `godot/private/run.bzl`, `tools/source_run/run.py` |

## Extensions

| Term | Meaning | Not to be confused with | In code |
|---|---|---|---|
| extension (GDExtension) | A GDExtension: a descriptor and the extension libraries it names. | A Bazel module extension; a file suffix. | `godot_extension`, `godot_cc_extension`, `GodotExtensionInfo` |
| descriptor | An extension's `.gdextension` file, which names its libraries per feature tags ([GDExtension](../../rules_godot/docs/public/gdextension.md)). | The export hook kind `descriptor`. | `GodotExtensionInfo.runtime_descriptor`, `descriptor_path` |
| descriptor fragment | The descriptor one configuration writes, with its one library entry, which a pack merges with those of its other platform slices. | The whole descriptor. | mnemonic `GodotExtensionDescriptors` |
| extension library | A library a descriptor names. | A platform library; the engine library. | `godot_extension.library` |
| configured extension library | The extension library of one configuration, which `select()` chooses. | | `GodotExtensionInfo.library` |
| link kind | How an extension library links: dynamic, static or framework. | Bazel's `linkstatic`. | `link_kind` in `godot/extension/private/library.bzl` |
| extension runtime library | The extension library of the target configuration, which the runtime and the editor running the project load. | The extension editor library. | `GodotExtensionInfo.runtime_resource_paths` |
| extension editor library | The extension library of the tool configuration, which editor actions load ([the tool configuration](../../rules_godot/docs/public/gdextension.md#the-tool-configuration)). | The extension runtime library. | `GodotExtensionInfo.editor_resource_paths` |
| extension host editor library | The extension's tool view built for the host, which `godot_editor` and `bazel run` load. | The extension editor library, built for the execution platform. | `host_tool_view`, `GodotExtensionInfo.host_editor_resource_paths` |
| tool view | An extension's target in the tool configuration, which provides the extension editor library. | A view of an operation. | `tool_view`, `<name>.tool` |
| runtime dependencies | The files an extension library needs at run time beside it, which the descriptor's `[dependencies]` section lists. | `deps`; Bazel's `runtime_deps`. | `GodotExtensionInfo.library.runtime_dependencies`, `godot_extension.data` |
| platform (Android, Apple) | Android or Apple, in the names platform library, platform resources and `platform_deps`. | A Bazel platform; platform (Godot). | `platform_deps`, `platform_libraries` |
| platform library | An Android or Apple library, such as an AAR or an XCFramework, that applications link and package beside the engine. | An extension library; Godot's Android plugin mechanism. | `godot_extension.platform_deps`, `godot_app.platform_deps` |
| delivery | Which extension libraries and runtime dependencies an application packages for its platform slices. | Linking. | `GodotViewInfo.runtime_extensions` |

## Applications

| Term | Meaning | Not to be confused with | In code |
|---|---|---|---|
| application | What `godot_app` packages: a desktop bundle and archive, an APK or AAB, or an IPA. | A pack. | `godot_app`, `GodotDesktopAppInfo` |
| start pack | The pack `godot_app.pack` names, which the application mounts at start. | A required pack; a loadable pack. | `godot_app.pack` |
| loadable pack | A pack an application may load after start, whose extension libraries the application delivers. | The start pack. | `godot_app.loadable_packs` |
| application context | The values of a `godot_app` that the export of its pack depends on, such as the application ID and minimum versions; applications that share them share one export. | The export platform. | `@autoload_rules_godot//godot/private/config:application_context`, `godot/private/config/application.bzl` |
| application backend | The operating-system application rule that `godot_app` selects for the export platform. | The shell; an add-on's backend. | `<name>.linux`, `<name>.android_apk`, `<name>.ios` of `godot_app` |
| runtime bridge | The rule that resolves the runtime toolchain inside an Android or Apple split and forwards the payload's providers to rules_android or rules_apple. | The runtime's engine component. | `runtime_bridge_android`, `runtime_bridge_ios` |
| platform resources | Files that a platform library or `godot_app.platform_resources` brings for Android resources or the iOS bundle. | Resources of the Godot project. | `godot_app.platform_resources` |
| configured application | A `godot_app` built under an export platform and build settings of its own ([release builds](../../rules_godot/docs/public/platforms.md#release-builds-in-one-invocation)). | A `--config` of `.bazelrc`. | `godot_configured_app`, `ANDROID_RELEASE`, `APPLE_RELEASE` |
| debug symbols | The unstripped libraries and `.dSYM` directories from which an application's stripped copies were made ([debug symbols](../../rules_godot/docs/public/platforms.md#debug-symbols)). | The debug variant. | `<name>.debug_symbols` |
| application launcher | The build tool that installs and starts an application for `bazel run`. | The launcher a rule writes. | `tools/platforms/launch` |

## Ruleset internals

| Term | Meaning | Not to be confused with | In code |
|---|---|---|---|
| build tool | A program under `rules_godot/tools/` that rules run as an action, a runner or a test ([build tools](../../rules_godot/docs/internal/architecture.md#build-tools)). | Repository tooling under `//tools`; the tool configuration; Godot's `@tool` scripts. | `tools/` |
| editor action | A build action that runs the Godot editor on a staged project: an import, initialization, probe or export. | A source run. | `run_editor_action` in `godot/private/actions.bzl`, `tools/editor_action/` |
| action plugin | The editor plugin a build tool adds to every staged project an editor action runs on. Its record of Godot's own result data decides whether the action succeeds. | An add-on's editor plugin. | `tools/editor_action/plugin`, `join_action` in `tools/editor_action/action.py` |
| probe | An editor action whose record carries facts Godot reports: the importers, features and shell probes. | An engine probe test. | operations `importers`, `features`, `shell` of `tools/editor_action/plugin` |
| shell probe | The probe that records what Godot decides for an export's shell files and shell assets, the export facts. | The shell files themselves. | `tools/editor_action/plugin/shell.gd` |
| export facts | What the shell probe records for a pack's export, such as feature tags, export options with defaults and project settings with feature overrides. | The export report. | `Facts` in `tools/platforms/shell_common.py`, output group `export_facts` |
| configured context | What a rule reads in its own configuration from the export platform's build settings and constraint lookups. | The project context. | `configured_context` in `godot/private/config/settings.bzl` |
| engine profile | What rules_godot mirrors of Godot's exporters for one Godot minor version, which build tools get as data. | A build profile. | `engine_profile()` in `godot/private/engine/profiles.bzl` |
| setting kind | How rules_godot classifies a project setting that names a file, per Godot minor. | A purpose. | `setting_kinds()` in `godot/private/engine/setting_kinds.bzl` |
| pinned settings | The project settings the ruleset fixes in the configuration of imports and exports, replacing authored values. | A pack's own `settings`. | `PINNED_SETTINGS` in `godot/private/configuration.bzl` |
| export hook | A virtual method of Godot's `EditorExportPlugin` or a legacy plugin descriptor, with its disposition ([inventory](../../rules_godot/docs/internal/export-plugin-hook-inventory.md)). | A Git hook. | `export_hooks` of the engine profile |
| owned export option | An export option that rules_godot sets itself and rejects or checks when authored. | An option of the project's configuration. | `owned_export_options`, `rejected_export_options` |
| option owner | The attribute or flag to use instead of an owned export option. | The owner of a declaration. | `option_owners` |
| launcher | An executable script a rule writes for `bazel run` or `bazel test`, which starts the runner or the application launcher with the target's manifest. | The application launcher. | `launcher()` in `godot/private/run.bzl` |
| runner (launcher) | The build tool a launcher starts: `tools/source_run/run.py` for source runs and tests, and the programs of `tools/checkout/` for `godot_editor` and `godot_metadata_sync`. | A CI runner; a test target or test adapter. | `_runner` attributes in `godot/private/run.bzl` |
| run logger | The autoload the runner adds to every run and test, which records the errors Godot reports while the game's scene tree exists. | Bazel's test log. | `tools/source_run/errors.gd`, `engine_errors` of `godot_run` |
| test adapter | A main script that runs a test framework under Bazel's test contract (sharding, `--test_filter`, JUnit). | A test target; a runner. | `adapter_test` in `godot/testing:adapter.bzl` |
| exec group | One of the exec groups named after what runs in them: `editor` builds the extension editor library beside the editor actions, `run` is the host of `bazel run`, `test` is Bazel's group of a test action. | An execution platform. | `_EXEC_GROUPS` in `godot/extension/private/extension.bzl`, `RUN_EXEC_GROUPS` and `TEST_EXEC_GROUPS` in `godot/private/execution.bzl` |
| mapped path | An output file's path as Bazel's path mapping stages it, with `cfg` in place of the configuration. | An execroot path. | `mapped_path` in `godot/private/paths.bzl`, `PATH_MAPPING` in `godot/private/actions.bzl` |
| companion target | A public target a macro generates beside its main target as `<name>.<suffix>`, such as `<name>.debug_symbols` ([API documentation](../../rules_godot/docs/internal/api-reference.md)). | A helper target. | `<name>.debug_symbols` |
| helper target | A private target a macro generates beside its public ones ([target ownership](../../rules_godot/docs/public/project-layout.md#target-ownership-and-project-context)). | A companion target. | |
| volatile API | Public API that may still change incompatibly in a release, marked by a notice at the end of its documentation. | Private API. | `VOLATILE_API` in `godot/private/macros.bzl` |
| `NOT_ACTUALLY_PUBLIC` | The visibility of a target every package may see but that is no API ([visibility inside the ruleset](verification-architecture.md#visibility-inside-the-ruleset)). | Public API. | `godot/private/visibility.bzl` |

## Repository and verification

| Term | Meaning | Not to be confused with | In code |
|---|---|---|---|
| Bazel module | A directory with a `MODULE.bazel`: the root module, the ruleset module, an add-on module or a registry test module. | An engine module; a Python module. | `MODULE.bazel` |
| root module | The repository's own Bazel module `autoload_dev` at its root, never published, with the repository tooling and the consumers of the released modules. | The ruleset module. | `//MODULE.bazel` |
| ruleset module | The Bazel module `autoload_rules_godot` in `rules_godot/`. | The root module's tooling. | `MODULE.bazel` |
| checkout | Your working copy of the repository: the authored files with the sidecars beside them. | An editor view; a CI checkout step. | `godot_metadata_sync`, `tools/checkout/` |
| add-on module | A Bazel module `autoload_<module>` at `addons/<module>/` with its own version and releases, which provides add-ons to applications. | An add-on, a directory of a Godot project. | `addons/<module>/`, `//tools/addons/new.py` |
| released module | The ruleset module or an add-on module: a Bazel module with its own releases. | An engine component. | `registry_test_modules` in `//tools/setup/modules.py` |
| consumer module | A part of the root module that uses `autoload_rules_godot` as a user's module does, through `local_path_override` and public API labels only: `examples/`, `e2e/rules_godot/` and `examples/addons/<module>/` ([boundary rules](verification-architecture.md#boundary-rules)). | The ruleset module; a Godot project. | `CONSUMER_ROOTS` in `//tools/conventions/layout.py` |
| development dependency | A `bazel_dep` with `dev_dependency = True`, which applies only when its module is the root. | A test-only dependency. | `dev_dependency = True` |
| public API label | A label of a released module that its API reference documents, the only kind a consumer module may name. | A `NOT_ACTUALLY_PUBLIC` target. | |
| `third_party/` | Where a module includes its dependencies and makes them usable: build files of pinned archives, wrapping targets and pinned lock files. | Vendored source the repository authors. | `ROOT_DIRECTORIES` in `//tools/conventions/rules/no_stray_entries_in_addon_module_roots.py` |
| release archive | The archive of a released module's release, from which the Bazel Central Registry builds. | A Godot release archive. | `//tools/ci/release_archive.py`, rule [release-archives-without-tests](conventions.md#release-archives-without-tests) |
| registry test module | The consumer module in `bcr/<name>/` of a released module that the Bazel Central Registry builds from the release archive. | A consumer scenario. | `registry_test_modules` in `//tools/setup/modules.py` |
| check (repository) | A verification that is no test, such as the conventions check, the lint check or the file lint, which `aspect check` runs, or a setup check. | A content validation. | `run_checks` in `.aspect/develop.axl` |
| conventions check | `bazel run //tools/conventions`: the convention rules that judge more than one file. | The file lint. | `//tools/conventions/check.py` |
| convention rule | One check of the conventions check or of the file lint, identified by a name that states its claim, such as `no-claude-md` ([catalogue](conventions.md)). | A Bazel rule. | `Rule` and `RULES` in `//tools/conventions/framework.py` and `registry.py` |
| finding | A violation a convention rule or Code Health reports, fixed in source or excepted with a reason. | A test failure. | `Finding` in `//tools/conventions/framework.py` |
| evaluated | What Bazel itself reports after loading and analysis, as opposed to what a parser reads from the source. | Analyzed providers. | `evaluated_frames` in `//tools/conventions/bazel.py` |
| file lint | The lint of files that have no Bazel targets of their own ([the file lint](verification-recipes.md#the-file-lint)). | The lint check. | `//tools/lint:files` |
| lint check | `--config=lint`: the linters of Python targets in Bazel's builds, applied as an aspect through `--config=check`. | The file lint. | `//tools/lint/check.bzl`, `//tools/lint/linters.bzl` |
| setup check | A check of `//tools/setup` that `aspect doctor` runs to say what a checkout lacks. | A conventions check. | `//tools/setup/` |
| Git hook | The pre-commit and pre-push hooks, which run `aspect pre-commit` and `aspect pre-push`. | An export hook; an agent's hook. | `pre_commit`, `pre_push` in `.aspect/hooks.axl` |
| task (Aspect) | A command of the Aspect CLI defined in `.aspect/*.axl`, such as `aspect check`. | Work. | `.aspect/develop.axl` |
| work | One named piece of verification that is no single Bazel command, such as `addon-template` or `source-engine:full`, which `aspect work <name>` runs. | A Bazel target; an Aspect task. | `Work` and `WORK` in `//tools/ci/work.py` |
| tier | `fast` or `all`: a config of test tag filters that selects which tests a run includes. | A host job. | `TIERS` in `.aspect/develop.axl` |
| host job | One of the two jobs of `.github/workflows/ci.yml`, `linux` and `macos`, each run as `aspect ci <host>` ([verification hosts](verification-platforms.md)). | A Bazel platform; the host. | `_ci_steps` in `.aspect/develop.axl` |
| runner (CI) | The machine a GitHub Actions job runs on. | The runner a launcher starts. | `.github/workflows/ci.yml` |
| Source engine workflow | The CI workflow that builds and tests source-built engines on its own, for pull requests that reach them. | A source-built engine. | `.github/workflows/source-engine.yml`, `//tools/ci/source_engine_changes.py` |
| test tag | A tag that selects a test by machine or cost, such as `godot_process`, `source_engine`, `android` or `ios`. | A test kind; a tier. | `--test_tag_filters` in `//shared.bazelrc` |
| worktree slot | A place of the Aspect CLI's worktree pool under `~/.aspect/worktrees` that keeps its path, Bazel server and output base for the next lease ([agent setup](agent-setup.md#worktrees)). | An engine's slot. | `aspect worktree add`, `//tools/worktree/` |
| Bazel profile | The output base the wrapper `tools/bazel` gives a run, such as `default` or `source-engine` ([verification recipes](verification-recipes.md)). | Bazel's `--profile`; a build profile. | `AUTOLOAD_BAZEL_PROFILE` in `//tools/bazel` |
| skill | Agent instructions under `.agents/skills/`, which both agents load. | A convention rule. | rule [linked-skills](conventions.md#linked-skills) |
| region | A part of a source file with one topic, from its region header to the next one ([region-headers-named-in-head](conventions.md#region-headers-named-in-head)). | GDScript's `#region`, which has an end marker. | `Region` in `//tools/conventions/rules/region_headers_named_in_head.py` |
| region header | The comment line that starts a region: the comment marker, `====`, the region's name and `=` up to column 80. | A Markdown heading. | `header()` in `//tools/conventions/rules/region_headers_named_in_head.py` |
| Code Health | CodeScene's score of a file's maintainability, which `aspect code-health` reports ([Code Health](code-health.md)). | A test's health or CI status. | `//tools/code_health/` |
| Gazelle language | A Go extension of Gazelle that declares the targets of one kind of source ([Gazelle for Godot](gazelle.md)). | A language Godot runs, such as GDScript. | `//tools/gazelle/godot` |
| test kind | A category of ruleset test that the [verification architecture](verification-architecture.md#test-kinds) defines, with its location, form, dependencies and claims. | A verification kind; a test tag. | |
| altitude | How much of the build a test observes, from one rule's analysis up to a running application ([test kinds](verification-architecture.md#test-kinds)). | Test size or duration. | |
| white-box test | A ruleset-module test below consumer altitude, which may load private files. | A consumer scenario. | `godot/**/tests/`, `tools/**/tests/` |
| consumer scenario | A package of `e2e/rules_godot/` in the root module that shows, with the public API only, what a user can build, inspect and run. | An example. | `//e2e/rules_godot/` |
| fixture | A target or Godot project that a white-box test builds or inspects to reproduce one case. | A consumer scenario. | `godot/private/tests/fixtures/` |
| artifact test rule | A test rule of the root module that inspects a built App Bundle or iOS application without running it ([artifact test rules](verification-architecture.md#artifact-test-rules)). | A test operation such as `godot_test`. | `android_bundle_test`, `ios_app_test` in `//tools/artifact_tests/` |
| demo test | A test of an add-on module's example application itself, in `examples/addons/<module>/tests/`. | An add-on end-to-end test, which tests the add-on. | `//examples/addons/<module>/tests/` |
| add-on end-to-end test | A test of the root module that uses an add-on as an application does, by running Godot or building a project ([add-on module tests](verification-architecture.md#add-on-module-tests)). | A consumer scenario; a test of an add-on module's own code. | `//e2e/addons/<module>/` |

## Terms to avoid

| Instead of | Say | Why |
|---|---|---|
| runtime extension library, editor extension library | extension runtime library, extension editor library | the extension comes first and its role follows, as the engine's roles are editor and runtime |
| GDExtension library | extension library | GDExtension stays for titles and Godot's concept |
| composed project, project members | view; the operation's members | a project holds no resources |
| pack selection, selection report | pack content, content report | selection is an operation's `deps`; code to rename: `GodotPackSelection`, `select_pack`, output group `selection`, `<name>.selection.json`, `tools/resource_graph/selection.py` |
| runtime profile | build profile | Godot's term; the runtime applies the profile, which is no runtime; code to rename: `godot_runtime_profile`, `godot_engines.runtime_profile`, `runtime_profiles` of `godot_engine_build` |
| runtime variant | profile variant | a variant is `release`, `debug` or `editor`; code to rename: the docstrings of `tools/engine/variants.py` |
| shell-assets probe, export probe, export-facts probe | shell probe | one probe had four names |
| Godot-ignored file | ignored file | prose says ignored file |
| regression project, regression scenario, regression module, regression fixtures | consumer scenario; the scenarios' module; scenario catalogue | the consumer scenarios replaced the regression projects; "regression" in its plain sense stays, but names no test; code to rename: `REGRESSION_ROOT` in `//tools/conventions/layout.py` |
| lane (for a CI job or a set of tests) | host job; test tag | no lane mechanism remains |
| source engine, source-engine (outside the Source engine workflow and the `source_engine` tag) | source-built engine | the workflow's name invites the short form |
| runner, test runner (for a test target, test adapter or test framework) | test target; test adapter; test framework | a runner is the build tool a launcher starts |
| component (for the ruleset or an add-on module) | released module | a component fills an engine's slot; code to rename: rule `no-component-names-in-tooling` |
| fixture (for a consumer scenario) | consumer scenario | a fixture serves one white-box test |
| lint check (for the file lint) | file lint | the lint check is `--config=lint` |
