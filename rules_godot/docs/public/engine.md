# Engines

A Godot build needs two engines: the **editor**, which imports and exports projects, and
the **runtime**, the export template an application packages. rules_godot resolves both
as Bazel toolchains, so projects, packs and apps need not name one. Register each engine by
name and Godot version: a catalogued release brings Godot's official editors and
templates, and the tags that name the engine add your own sources, binaries, modules,
patches and options. Each role, platform and CPU, plus, for runtimes, the iOS environment
and the variant, is one slot, and the first registered candidate for a slot wins. A target
uses one engine, the default one or the one it [names](#name-an-engine), and takes no other
engine's components.

| You want | Use |
| --- | --- |
| The official editors and templates of a release | [An `engine` tag](#register-an-engine) |
| Your own modules, patches or options | [A `build` tag](#build-an-engine-from-source) |
| A fuller editor beside reduced runtimes | [An `editor` tag](#build-the-editors-differently) |
| A fork, or a release outside the catalogue | [`source` and `binaries` tags](#use-other-sources-or-binaries) |
| An engine that only the targets naming it use, such as one with your own module | [An engine name](#name-an-engine) |
| Components of different sources in one engine | [`--extra_toolchains`](#replace-slots) or [`select()`](#choose-between-prepared-recipes) |

The supported versions are **>=4.7.2 <5.0.0**; [versions](versions.md) lists the built-in
release pins.

## Register an engine

1. Register an engine in `MODULE.bazel`:

   ```starlark
   godot_engines = use_extension("@autoload_rules_godot//godot:extensions.bzl", "godot_engines")
   godot_engines.engine(name = "godot", default = True, version = "4.7.2")
   ```

2. Build a pack or app as usual; `bazel build //path/to:app` downloads only the editor
   of your host and the templates the app needs.

An engine is one `engine` tag, completed by the `source`, `binaries`, `build`, `editor` and
`runtime_profile` tags that name it with `engine = "<name>"`. Its `name` is what targets
[select](#name-an-engine), the name of its hub repository `@<name>`, whose `toolchains`
package holds its components, and the prefix of its other repositories. `default = True`
makes it the engine of every target that names none; at most one engine of a module is the
default. The root module's default wins; a dependency's, such as an add-on module's own
engine, counts only when the root module names none. What an engine can do follows from
its tags:

| Tags | Prebuilt binaries | Built from source |
| --- | --- | --- |
| `engine` of a catalogued version | Godot's official ones | the slots they lack, and every runtime of an application with a build profile or of an optimized release |
| + [`build`](#build-an-engine-from-source) | none of the catalogue's | every slot |
| + [`binaries`](#use-other-sources-or-binaries) | these | as above, beside them; with pinned editors or templates, a fork's, only from a `source` tag's sources |
| + [`source`](#use-other-sources-or-binaries) | as above | from these sources instead of the catalogue's |
| `binaries` of an uncatalogued version, no `source` | these | none: build profiles fail analysis, and [engine optimization](#optimization) leaves the binaries unchanged |

The hub has a component for every valid slot: an editor per editor platform and a runtime
per platform, CPU, iOS environment and variant. You register no toolchains yourself: the
extension also generates `@godot_engines_toolchains`, the toolchains of every registered
engine's components, which rules_godot's own module registers. `use_repo` is needed only
for the repositories you reference directly, such as a recipe or `@<name>//:pin`. Declaring the components costs nothing: an engine downloads,
configures and compiles only the payloads a build requests, so slots of platforms a build
never targets are never fetched.

For a catalogued version, `version` is enough: the hub covers the official editors per
editor platform, the Linux and macOS runtimes, the iOS device and simulator runtimes and
the Android runtimes. Where the official artifacts lack a runtime slot, the hub builds it
from the release's sources:

- Official Android shell AARs are release builds, so the Android debug runtimes are
  source-built, unless the engine's [`binaries`](#use-other-sources-or-binaries) pin
  `android_debug_shell_urls` and `android_debug_shell_integrity`.
- The official Simulator Godot libraries contain x86_64 objects, although the 4.7.2
  XCFramework metadata advertises an ARM64 slice. In 4.8-beta1, the required AccessKit
  library contains ARM64 objects, so those Simulator libraries cannot link together at
  all. A Simulator build with a missing slice fails validation, naming each library and
  the slices it has, so the ARM64 Simulator runtimes are source-built. The first arm64
  Simulator build on a Mac compiles the engine once, and Bazel's cache keeps it. The
  4.8-beta1 sources do not bundle the AccessKit SDK, so its source-built Simulator
  runtimes have no screen reader support; device builds keep the official template's.

These recipes enable the modules Godot's official builds enable by default
(`default_modules` of a [`build` tag](#build-an-engine-from-source)); iOS recipes leave out
Vulkan, which would need the MoltenVK SDK on the configuring Mac, and keep Metal and
OpenGL. Like every recipe, one configures and compiles only when a build selects its slot,
on a host Godot accepts for its platform, such as a Mac for iOS. The prebuilt slots keep
the official artifacts only for builds whose runtime needs no tuning: a prebuilt runtime
cannot leave classes out or compile differently, so for an application with a
[build profile](#an-applications-build-profile), or under `-c opt` with
[engine optimization](#optimization) other than the defaults, the hub builds every runtime
slot from the same sources, as its `runtime_<slot>_tuned` components. To fill such slots with your own engine instead,
register your components [ahead of the engine's](#replace-slots). `bazel fetch --all` and
`bazel vendor` configure every recipe that no [lock file](#pin-the-recipes) pins,
including the iOS ones, which only a Mac can; fetch the targets you build instead, or pin
the recipes.

## Use other sources or binaries

A `source` tag builds the engine from an immutable archive other than the catalogue's,
such as a fork's or a snapshot of a maintenance branch:

```starlark
godot_engines.engine(name = "patched", version = "4.7.3-rc1")
godot_engines.source(
    engine = "patched",
    sha256 = "90ef5ad9f4c59750004813813534527eb3f82f1975789fb5b79b609fe841beb8",
    strip_prefix = "godot-2ea68c77c3157c95793987569dc44662fe4f83cf",
    urls = ["https://github.com/godotengine/godot/archive/2ea68c77c3157c95793987569dc44662fe4f83cf.tar.gz"],
    version = "4.7.3-rc",
)
```

The engine's `version` is its exact canonical version, which must be numbered, such as
`4.7.3-rc1`. The source tag's `version` is what the archive's `version.py` names, such as
`4.7.3-rc` or `4.8.0-beta` for an unnumbered prerelease; empty takes the engine's. A
recipe whose sources say otherwise fails.

A `binaries` tag pins prebuilt editors, export templates or Android shells, each part
replacing the catalogue's. Declaring them states that they match the engine's sources and
build, such as a fork's release artifacts: the engine builds only the slots they lack.
Pinned editors or templates are a fork's, so the engine then builds only from a `source`
tag's sources, never from the catalogue's upstream sources; without one, it builds nothing.
Digests are Subresource Integrity strings:

```starlark
godot_engines.engine(name = "beta", version = "4.8.0-beta1")
godot_engines.binaries(
    engine = "beta",
    android_shell_urls = ["https://github.com/godotengine/godot-builds/releases/download/4.8-beta1/godot-lib.4.8.beta1.template_release.aar"],
    android_shell_integrity = "sha256-G1KpV92jFIn4OirzO17zy2euXFLyE40BSATgYs9MI5Y=",
)
```

`editor_urls`, `editor_integrity` and `editor_binaries` are keyed by editor platform
(`linux_x86_64`, `linux_arm64`, `macos`, `macos_arm64` or `macos_x86_64`);
`templates_urls`, `templates_integrity`, `templates_macos_cpus`, `templates_linux_cpus` and
`ios_simulator_cpus` describe the export templates; `android_shell_urls` and
`android_debug_shell_urls` pin the release and debug Android shells. An uncatalogued
version without a `source` tag needs the editors of its `binaries` and builds nothing from
source. The [API documentation](https://registry.bazel.build/modules/autoload_rules_godot)
of `godot_engines` lists every attribute and the generated targets.

A module completes only the engines it registers. The root module's request owns its
engine name, identical requests from dependencies share one engine, and conflicting ones
fail.

## Replace slots

Registration order decides between the candidates of one engine for a slot. A root
module's own `register_toolchains` and `--extra_toolchains` come before the engines'
toolchains, so a set you register replaces only the slots it covers:

```starlark
register_toolchains("//engines/custom:all")  # wins for its slots; the engine keeps the others
```

A registration set is any package of components; each component joins the engine its
`engine` attribute names, or the default engine without one, and `default_engine = True`
lets a named default engine's components also serve targets that name none, as the
default engine's hub does. For one
invocation, `--extra_toolchains=//path/to/engines:all` puts a set ahead of every registered
one; `--extra_toolchains` gives its last entry priority. Each component also has a
`<name>.toolchain` target, so one slot can be prioritized alone, such as only the editor:

```sh
bazel build //path/to:app --extra_toolchains=//path/to/engines:editor_macos_arm64.toolchain
```

`@<name>//toolchains:all` holds the components of one engine alone, for a build that
registers that engine's slots ahead of the others.

The editor and runtime of one build may come from different sets, versions or sources.
They are not compared: the editor exports the pack, and the runtime that loads it must
read that pack format, as Godot's own export does. A slot without a candidate fails
analysis with `no registered Godot runtime component of the selected engine matches this
target platform and Godot variant`, naming the role. `bazel query 'kind(toolchain, //engines/...)'` lists a set.

Editors depend on the execution platform as well. Bazel tries execution platforms in their
registration order and takes the first one any registered editor matches, so an execution
platform listed earlier with an older editor wins over a preferred editor on a later one;
that is Bazel's selection, not a fallback. To choose a specific editor, register its
execution platform first, constrain the execution platforms a build may use, or register
only the editors you want. Tests resolve their editor for their test action's execution
platform, and `bazel run` and `godot_editor` for the host, while the project's imports and
packs come from the build, wherever its editor actions ran. Which extension libraries each
editor loads is described in
[the tool configuration](gdextension.md#the-tool-configuration).

## Name an engine

An engine name keeps an engine apart: its components fill slots only for targets that
select it, and such a target takes no component of another engine, whatever the
registration order. Register each engine beside the others:

```starlark
godot_engines.engine(name = "godot", default = True, version = "4.7.2")
godot_engines.engine(name = "studio", version = "4.7.2")
godot_engines.build(
    engine = "studio",
    # ... modules, patches and options
)
```

A target selects an engine with its `engine` attribute: `godot_editor`,
`godot_metadata_sync`, `godot_runtime_profile`, `godot_pack`, `godot_run`, `godot_test` and
`godot_app` take it, and
what the target reaches, such as its project's imports, uses the same engine. One build can
hold targets of several engines:

```starlark
godot_pack(name = "pack", engine = "studio", project = ":project", deps = [":game"])
godot_app(name = "app", engine = "studio", pack = ":pack")
```

An empty `engine` keeps the build's engine: the default engine, or the one
`--@autoload_rules_godot//godot:engine` names for a whole invocation, such as a check of
every target against a newer engine. The default engine also answers to its name, so
`engine = "godot"` and an empty `engine` select the same components. A run of a pack and
an application name the engine their pack was exported with. Registering an engine
downloads nothing until a target selects it.

To give the whole repository your own engine, set `default = True` on it instead of on the
official one. Keep each engine's inputs in a directory of its own, `engines/<engine name>/`:
its modules in `modules/<module>/`, its patches in `patches/` and its lock file beside them.
Engines are shared by the applications that name them, so they live apart from every
project; [project layout](project-layout.md) shows the place in a repository.

A slot the named engine does not cover has no candidate: a target platform it lacks fails
analysis with the missing role, rather than taking the default engine's runtime. An
execution platform it has no editor for is skipped: Bazel resolves the actions that run the
editor on the next execution platform with one, such as this host behind a remote Linux
executor, and the build's other actions stay where they are.

## Build an engine from source

A `build` tag compiles the engine from its sources, the catalogue's or a
[`source` tag's](#use-other-sources-or-binaries), with your modules, patches and options,
and the catalogue's binaries then no longer serve it: every slot its `binaries` tag does
not pin is built. The engine declares one source recipe per row: SCons evaluates the
feature graph once, and Bazel compiles each object and runs each code generator as its own
cached action.

```starlark
godot_engines = use_extension("@autoload_rules_godot//godot:extensions.bzl", "godot_engines")
godot_engines.engine(
    name = "my_engine",
    version = "4.7.2",
    lock_file = "//engines/my_engine:my_engine.lock.json",
)
godot_engines.build(
    engine = "my_engine",
    enabled_modules = ["gdscript", "text_server_fb", "my_module"],
    custom_modules = {"//engines/my_engine/modules/my_module:config.py": "my_module"},
    patches = ["//engines/my_engine/patches:fix.patch"],
    renderers = ["gl_compatibility"],
)
```

Every recipe of an engine shares its build policy; slots with different policies belong
to separate engines, or, for the editors, to an [`editor` tag](#build-the-editors-differently).
Declaring the engine configures nothing: a recipe is configured, with its operating
system's SDK, only when a build needs its payload. Godot configures a recipe only on a host
its build scripts accept for that platform; macOS, for example, configures no Linux recipe.
A build on macOS that registers a Linux execution or target platform, such as a remote
executor, selects the hub's Linux slots and fails, rather than taking another engine's
editor; [pin the recipes](#pin-the-recipes) so that any host builds every slot.

Hub components are named `editor_<platform>_<cpu>` and
`runtime_<platform>_<cpu>[_<environment>]_<variant>`. The engine's other repositories are
`@<name>_source`, its sources; `@<name>_<row>`, one source recipe per row, such as
`@my_engine_macos_arm64_editor` or `@my_engine_ios_arm64_simulator_template_release`;
`@<name>_source_android_shell`, the Android shell library built from source; and, for
pinned binaries, `@<name>_editor_<platform>`, `@<name>_templates_<platform>`,
`@<name>_android_shell` and `@<name>_android_debug_shell`. Name a recipe's outputs to
[compose components of your own](#choose-between-prepared-recipes).

Editors compile for the execution platform. macOS and iOS recipes compile for the
deployment target Godot's own build sets, raised to what the libc++ of current Xcode
supports: 11.0 on macOS (Godot sets 10.13 on Intel Macs) and 15.0 on iOS (Godot sets
14.0), whatever the build's `--macos_minimum_os` or the application's minimum says, so one
engine build serves every application; an application's minimum is its bundle's and its
extension libraries', set by [`macos_minimum_os_version`](platforms.md#linux-and-macos) and
`ios_minimum_os_version`, and may not fall below the recipe's target.

The `my_module` and patch entries are optional; remove them if unused. Export
`config.py` and the patch from their BUILD packages. A custom module uses
Godot's normal `config.py`, `SCsub`, `register_types.h` and C++ source layout.
The recipe watches and copies that directory, then evaluates its upstream
registration logic. A custom module may override a built-in module of the same
name. Bazel BUILD files in that directory are excluded from the copy.

A recipe's configuration reads no host packages or SDK: Linux recipes configure against
Godot's bundled libraries, so options such as `builtin_freetype = "no"` fail, and without
Wayland, whose code generators are shell commands; Android recipes configure without the
host's SDK, since Bazel's NDK toolchain compiles them.

`renderers` names Godot's rendering methods the engine runs: `gl_compatibility`, `mobile`
and `forward_plus`. The example keeps the Compatibility renderer, so the project's rendering
method must be `gl_compatibility`; [choose the renderers](engine-size.md#2-choose-the-renderers)
has the driver rules and the check.

The module list is an allowlist, as [choose the modules](engine-size.md#1-choose-the-modules)
explains. `default_modules = True` starts from the modules Godot enables by default for the
platform, as its official builds do: without a list, a recipe then enables only Godot's
defaults, which include `text_server_adv`. Editor builds also include upstream's required
`freetype`, `regex` and `svg` modules. Misspelled modules, cycles, unreadable dynamic
dependency declarations and modules rejected by Godot's configuration fail with an error.

A `build` tag takes no build profile. Options that the editor and every runtime of the
engine share belong in `build_options`, `enabled_modules` and `renderers`; classes and
options that cut one game's runtime belong in that application's
[build profile](#an-applications-build-profile), so the editor, imports and tests keep
them.

Patches use the host `patch` executable with fuzz disabled and strip level 1
(`patch_strip`); every hunk must apply, to every recipe and to the Android shell library.
`build_options` accepts upstream options;
options rules_godot controls are rejected: Godot's `platform`, `arch` and `target`, the iOS
simulator switch, module selection, raw `profile` and `build_profile` paths (an
application's [build profile](#an-applications-build-profile) takes their place),
`optimize` and `lto`, which follow the [optimization](#optimization) settings, and
`debug_symbols`, which follows Bazel's flags as in [debug symbols](#debug-symbols). Generator actions use hermetic Python 3.14.
Builders must read literal keys from `env` or pass it directly to named Python
helpers with an `env` parameter. Dynamic callbacks, environment aliases and
unsupported forwarding fail configuration instead of silently omitting inputs.

### Build the editors differently

An `editor` tag replaces the build tag's `enabled_modules`, `default_modules` and
`build_options` for the engine's editor recipes only, such as a fuller editor beside
reduced runtimes; patches and custom modules stay the build tag's:

```starlark
godot_engines.editor(
    engine = "my_engine",
    enabled_modules = ["gdscript", "text_server_adv", "zip", "my_module"],
    build_options = {"vulkan": "no"},
)
```

The editor imports and exports what the runtimes then load, so keep the modules a project
uses in both.

### Pin the recipes

A lock file pins the build graph of every recipe of an engine, as `maven_install.json`
pins a Maven resolution: the recipe repositories read it and configure nothing on the
host, so a Mac declares the Linux editor's actions and a remote Linux executor compiles
them. Name the file with the engine's `lock_file` and write it with the hub's `:pin`,
which the module reaches through `use_repo`:

```starlark
godot_engines.engine(
    name = "my_engine",
    version = "4.7.2",
    lock_file = "//engines/my_engine:my_engine.lock.json",
)
use_repo(godot_engines, "my_engine")
```

```bash
bazel run @my_engine//:pin --config=remote
```

The package of `lock_file` must exist; the file itself is created by the first pin. `:pin`
configures each recipe in a build action on an execution platform of an operating system
Godot accepts for it: Linux recipes on a Linux executor, macOS and iOS recipes on a Mac,
Android recipes on any. A host whose execution platforms reach only some of them pins one
platform's recipes with `:pin_linux`, `:pin_macos`, `:pin_android` or `:pin_ios`, which
writes them into the lock file and keeps the others; a Linux CI job can pin the Linux
recipes, and a Mac the macOS ones:

```bash
bazel run @my_engine//:pin_linux --config=remote
bazel run @my_engine//:pin_macos
```

A recipe without a pin fails only when a build needs it, naming the pin command. The hub's
`:pinned` fails while any recipe or runtime variant has no current pin, on every host,
whatever platform the recipes are for; a `build_test` of it beside the lock file checks
the pins in `bazel test //...`:

```starlark
load("@bazel_skylib//rules:build_test.bzl", "build_test")

build_test(
    name = "pinned_test",
    targets = ["@my_engine//:pinned"],
)
```

Each pin records the digest of what its graph depends on: the archive, the patches, the
recipe's platform, CPU, target, modules and options, for a runtime variant its runtime
profile's build options (not its class list), its build name, the SCons release and
rules_godot code that capture the graph, and of each custom module its `SCsub`,
`config.py` and shader sources and the paths of its other files. A recipe whose digest no
longer matches, after such a change or a rules_godot upgrade that changes that code,
fails with the pin command instead of reconfiguring silently; editing a custom module's
C++ code keeps its pin, and so does a rules_godot upgrade that changes only how a graph
becomes Bazel targets. Commit the lock file with the change that requires it.

### Android shell libraries

An Android runtime is Godot's Java/Kotlin library, the Android shell library, with the
engine library inside. An engine that builds Android runtimes from source builds the shell
library from the same patched sources, so a fork's Java changes come with its sources.
rules_godot adds the shell library's Maven dependencies, including `kotlin-stdlib` at
Godot's Kotlin version, to your shared `maven` repository; repin it after adding
rules_godot (`RULES_JVM_EXTERNAL_REPIN=1 bazel run @maven//:pin`). The contribution pins
`listenablefuture` 1.0, which the shell library's AndroidX dependencies reference; an
application that packages Guava declares Guava's empty `listenablefuture` placeholder
artifact instead. Java and Kotlin target Godot's level per target, so no Kotlin toolchain
is registered.

An Android plugin that compiles against Godot's classes, such as `GodotPlugin`, depends
on `@autoload_rules_godot//godot/platforms:android_plugin_api`. It supplies the shell
library of the runtime component the plugin's configuration selects: that of the engine
and variant of the application, or of the pack, that the plugin is built for. A plugin
thus compiles against the engine its application ships, whatever that engine is named,
and a module with plugins registers no engine of its own. Where the runtime carries a
source-built engine library, the plugin compiles against the shell library without it, so
compiling a plugin never waits for an engine build. The classes are for compilation only;
the application packages its runtime itself, so they appear once in the app.

```starlark
android_library(
    name = "plugin",
    srcs = ["MyPlugin.java"],
    exports_manifest = 1,
    manifest = "AndroidManifest.xml",
    target_compatible_with = ["@platforms//os:android"],
    deps = ["@autoload_rules_godot//godot/platforms:android_plugin_api"],
)
```

## Choose between prepared recipes

A component's payload may be a source recipe's output, such as
`@my_engine_macos_arm64_template_release//:godot`, or a `select()`, so a build setting can
choose between recipes of the same slot; only the selected recipe is configured:

```starlark
godot_runtime_component(
    name = "runtime_macos_arm64_release",
    platform = "macos",
    cpu = "arm64",
    variant = "release",
    version = "4.7.2",
    runtime = select({
        ":minimal": "@minimal_macos_arm64_template_release//:godot",
        "//conditions:default": "@godot//toolchains:runtime_macos_arm64_release",
    }),
)
```

A payload that is itself a component forwards that component's payload and provenance.
Every branch must fill the declared slot; packaging inspects the operating system,
CPU and variant of what it receives.

## Inspect the selection

Every resolved component carries a provenance record: its label, kind (`prebuilt` or
`source`), version, origin, digest (the archive integrity or the source sha256) and the
requested modules, patches and options. The pack names its editor and a desktop app the
runtime it packages:

```sh
bazel cquery //path/to:pack --output=starlark \
  --starlark:expr='providers(target)["@@autoload_rules_godot+//godot:providers.bzl%GodotPackInfo"].editor_component'
bazel cquery //path/to:app --output=starlark \
  --starlark:expr='providers(target)["@@autoload_rules_godot+//godot:providers.bzl%GodotDesktopAppInfo"].runtime_component'
```

Provider keys use the canonical repository name; `providers(target).keys()` lists them.

`--toolchain_resolution_debug='@autoload_rules_godot//godot:.*'` shows how Bazel chose each slot.

## Version stamp

A source-built engine names its base version, a build name with the origin of its
hash, and the hash in Godot's version scheme, such as
`4.7.2.stable.simulation-git.d33b04459`. `Engine.get_version_info()` returns the
build name as `build` and the full hash as `hash`, the startup line and crash
reports print them, and on Android the engine AAR's manifest names the same
version (see [Android shell libraries](#android-shell-libraries)).
This tells a crash report's engine apart from the official build of the same
version and from other custom builds. The build name is the engine's name, here `simulation`; a recipe that
`godot_engine_build` declares directly takes its `build_name` attribute, `custom` by
default.

The hash and Godot's version time stamp take the place of a Git commit and its
time. Which ones the engine names depends on Bazel's stamping:

| Build | Origin | Hash | Time stamp | Example |
| --- | --- | --- | --- | --- |
| `--stamp` with `STABLE_GIT_COMMIT` in the workspace status | `git` | That commit | `STABLE_GIT_COMMIT_TIMESTAMP`, else none | `4.7.2.stable.simulation-git.d33b04459` |
| Otherwise | `bazel` | Hash of the engine's declared inputs | None | `4.7.2.stable.simulation-bazel.c5058d28e` |

With a time stamp, the startup line and the editor show the commit's time in
UTC, and `Engine.get_version_info()` returns it as `timestamp`.

To stamp release builds with the commit they are built from, add a workspace
status script and a configuration to `.bazelrc`:

```sh
#!/bin/sh
# tools/workspace_status.sh
echo "STABLE_GIT_COMMIT $(git rev-parse HEAD)"
echo "STABLE_GIT_COMMIT_TIMESTAMP $(git log -1 --format=%ct)"
```

```text
build:release --stamp --workspace_status_command=tools/workspace_status.sh
```

The commit must be lowercase hexadecimal and its time a Unix time in seconds;
uncommitted changes leave no mark in either. The build time is not used: as a
stable key it would relink the engine in every build. A new commit regenerates and recompiles one engine source file, relinks the
engine and repackages the application; imports, packs and the other engine
objects stay cached. Switching between stamped and unstamped builds changes the
origin, which recompiles the engine sources that include Godot's version header.

The hash of the declared inputs covers the archive digest, the patches, the
custom modules' files and the recipe's `platform`, `build_target`, `enabled_modules`
and `build_options`, so an unchanged engine keeps its hash and its cached actions. The
CPU is not part of it, so the engines of one configuration for several
Android ABIs name the same version. Neither are compiler and toolchain flags.

## Optimization

[Make the engine small](engine-size.md) combines these settings with module selection,
renderers, feature switches and a build profile.

Under `-c opt`, a source-built engine compiles at the level of
`--@autoload_rules_godot//godot:engine_optimize`, with Godot's values and meaning plus
one of the ruleset's own:

| Value | Compiles with |
| --- | --- |
| `auto` (default) | Godot's own choice: `speed` for release runtimes, `speed_trace` for debug runtimes and editors |
| `speed` | `-O3` |
| `speed_trace` | `-O2` |
| `size` | `-Os` |
| `size_extra` | `-Os` and Godot's `SIZE_EXTRA`, which stops forced inlining |
| `size_min` | `-Oz` and `SIZE_EXTRA`, the smallest engine |

`--@autoload_rules_godot//godot:engine_lto` adds link-time optimization: `none` (default),
`thin` or `full`. Apple engines carry it in their objects into the application's link;
Android and desktop engines also link with it. `thin` needs Clang, and `-Oz` needs Clang or
GCC 12; `full` takes the longest to link.

`--@autoload_rules_godot//godot:engine_vfe` lets the full LTO link drop the virtual
functions nothing calls. It compiles the engine with Clang's `-fvisibility=hidden
-fwhole-program-vtables -fvirtual-function-elimination` and Godot's `TYPED_METHOD_BIND`;
the link needs nothing beyond `-flto`. It needs `engine_lto=full` and Clang: under `-c opt`,
any other `engine_lto` fails the build. The setting is off by default;
[make the engine small](engine-size.md#5-optimize-for-size) explains why.

The settings apply to the engine's own code only, after the build's `--copt` and `--linkopt`, so
their level wins over the toolchain's and the command line's there, while extensions and
application code keep the build's flags. Other compilation modes keep Bazel's levels: `-c dbg`
debugs the engine unoptimized whatever the settings say.

A prebuilt runtime cannot apply these settings. Under `-c opt` with any setting other
than the defaults (`engine_optimize=auto`, `engine_lto=none`, `engine_vfe` off), an
application takes the runtime its engine builds from source instead, as the
`runtime_<slot>_tuned` components of a [catalogued engine](#register-an-engine) provide;
in `fastbuild` and `dbg`, the prebuilt runtime stays. An engine with binaries but no
sources has no such runtime, so the settings leave its prebuilt runtimes unchanged.
Prebuilt editors are unaffected.

`godot_app`'s `engine_optimize`, `engine_lto` and `engine_vfe` (`on`, `off`, or empty to
keep the build's) override the build's settings for the application's own engine; one
recipe then serves a small release application beside a fast debug one, each with an
engine built for it. [Optimize for size](engine-size.md#5-optimize-for-size) shows the
command and the `godot_app` attributes for the smallest release engine.

## An application's build profile

`godot_app`'s `build_profile` takes a build profile, a `.gdbuild` file as in
[use a build profile](engine-size.md#4-use-a-build-profile), and leaves its
`disabled_classes` out of that application's runtime only. Packs, imports, tests and the
editor keep every class, so the same project can ship a reduced release application while
development uses the full runtime:

```starlark
godot_app(
    name = "app",
    pack = ":pack",
    build_profile = "release.gdbuild",
)
```

The class list reaches the generator of `core/disabled_classes.gen.h` as an input when it
runs: no recipe is configured or repinned. Only the sources that register classes read the
profile; the engine's other objects reach the runtime through a rule that resets the
application's profile, so applications with different profiles share them and compile only
those sources and their link again. When the engine's `core/object/class_db.h` includes the
profile as upstream does, rules_godot lets it include the profile only in the sources whose
includes reach a `GDREGISTER_*` macro or `GD_IS_CLASS_ENABLED`, and any other source that
evaluates a class's state fails to compile instead of ignoring the profile.

The runtime must be built from source, such as one of an engine with a
[`build` tag](#build-an-engine-from-source) or the runtimes a
[catalogued engine](#register-an-engine) builds from its release's sources for
applications that need tuning: a prebuilt runtime has no class generator, and an
application with a `build_profile` whose runtime component is prebuilt fails analysis
naming it. Before you ship, run the whole game: an application that loads a disabled class
fails when it loads it, not at build time.

### Build options in a build profile

A profile's `disabled_build_options`, such as `disable_3d` or `module_gridmap_enabled`,
shape the engine's graph, so they need a runtime variant of the engine with its own graph.
Register the profile in `MODULE.bazel` for the engine whose runtimes apply it, with its
`engine` naming that engine; empty, the default, is the default engine:

```starlark
godot_engines.runtime_profile(profile = "//game:release.gdbuild")
```

Every runtime recipe of that engine then declares a runtime variant: the recipe configured with the
recipe's own build options with the profile's beside them. The variant lives in the recipe's repository
beside the recipe's own graph; the targets the two declare alike keep one label, and the
attributes that differ select on the application's profile. An application whose
`build_profile` names the registered file gets the variant; other applications keep the
recipe's graph. Under path mapping, the variant's objects that compile alike share the
recipe's cache entries; only the sources whose preprocessing reads a definition the options
change compile again, with the class registrations.

A profile that only disables classes needs no registration. An application whose profile
sets build options without one fails its build, naming the `runtime_profile` line to add.
To switch single options or modules, write a small profile with only them:

```json
{
	"type": "build_profile",
	"disabled_build_options": {
		"module_gridmap_enabled": false
	}
}
```

With a [lock file](#pin-the-recipes), each variant has its own pin beside its recipe's;
`bazel run @<name>//:pin` writes both, and an application that selects a variant without a
current pin fails with that command. Without one, the recipe's repository configures each
variant before the recipe. A profile that names an option the recipe's Godot version does
not have, sets an option rules_godot controls, as `build_options` may not (`platform`,
`target` or `optimize`, for example; module switches are the profile's to set), whose
options contradict the recipe's `build_options`, or that disables a module the recipe's
`enabled_modules` names leaves that recipe without the variant: the applications that
select it fail with the reason, and the recipe's other applications build as before; with a
lock file, pinning that variant fails with the reason. `module_<name>_enabled` switches
custom modules too, those a recipe enables through `default_modules`.

A recipe reads a profile's options as its Godot version does. The switches the editor writes
that the version's build lacks, such as 4.7's `rendering_device`, are left out, and an
option whose build needs another brings it: in 4.7.0 to 4.7.2, `disable_physics_3d` turns
`module_gridmap_enabled` off, since gridmap does not compile without 3D physics there. A
profile that turns a rendering driver off, such as Metal for a project on the Compatibility
renderer, leaves the methods that need it out of the recipe's `renderers`, so applications
check their project's method against what the variant runs.

## Debug symbols

A source-built engine's debug information follows Bazel's `-c`, `--copt`,
`--per_file_copt` and `--apple_generate_dsym`, for `template_release` and
`template_debug` engines alike; its optimization follows the
[optimization](#optimization) settings under `-c opt`. `fastbuild`, the default,
compiles it unoptimized.

`-c dbg` debugs an application together with its engine. A store build whose
crash reports name engine frames compiles with `-c opt --copt=-g`, the
[store release](platforms.md#debug-symbols) of the platform guide; to give only
the engine debug information, match its sources. In this command template,
replace `//path/to:target` with your application's label and `my_engine` with
your engine's name:

```sh
bazel build //path/to:target -c opt --per_file_copt='external/autoload_rules_godot[+][+]godot_engines[+]my_engine_.*@-g'
```

Applications provide the engine's symbols as part of their
[debug symbols](platforms.md#debug-symbols), which also says where they are on each
operating system and how `--strip` treats them.

Debug information names sources relative to the execution root, such as
`external/autoload_rules_godot++godot_engines+my_engine_macos_arm64_template_release/core/object/object.cpp`, so engine
bytes do not depend on the build machine and stay cacheable.
`separate_debug_symbols` is rejected: Bazel does not run Godot's symbol extraction
after linking.

### Debug a source-built editor

`--@autoload_rules_godot//godot:editor_debug` compiles source-built editors in Bazel's
`dbg` mode: with debug information, without optimization and unstripped, whatever the
build's `-c`. Runtimes keep the build's mode. An editor builds in the execution
configuration, which resets custom flags, so propagate the flag with it, for example as a
config in your `.bazelrc`:

```
common:editor-debug --@autoload_rules_godot//godot:editor_debug
common:editor-debug --experimental_propagate_custom_flag=@autoload_rules_godot//godot:editor_debug
```

`bazel run --config=editor-debug` of a [`godot_editor`](development.md#editor-view) then opens the project in
an editor you can attach a debugger to. Prebuilt editors are unaffected.

## Cache behavior and limits

Each translation unit is its own native library, named after its source, and
declares only the files its source can include: the configuration scans the
`#include`, `#import` and `__has_include` directives of the engine tree,
transitively and regardless of conditional compilation, together with headers
that macros or compile options name for computed includes. A header change
therefore reruns only the compile actions whose sources reach it, also on another
machine, in a new checkout or on CI, where the remote or disk cache, not Bazel's
local header dependency tracking, decides; a change to a header that almost every
source includes, such as `core/object/class_db.h`, still recompiles most of the
engine. Generated files are scanned by the include directives their generator's
code writes. A source that reaches a header in a way the scan cannot see, such as
an include path that a macro assembles, fails to compile in a sandbox or on a
remote executor. A GDScript edit does not compile engine objects; an engine edit
does not re-import unrelated assets.

Include directories follow the same rule. Godot gives every source of a compile group the
same include directories, among them `_custom_modules`, the directory that holds a recipe's
custom modules, and each one is part of the compile command. Each source keeps only the
include directories, in their order, that hold a file it reaches: the scan resolves an
include to every directory that has the file, so no other directory can resolve one of
the source's includes. Removing the only custom module of an Android recipe of 731
sources reruns the 19 sources whose files change or reached the module instead of all of
them, and so does adding one back.

Macro definitions follow the same rule. Build options such as `disable_3d` add `-D`
options, and every compile option is part of a compile action's cache key. A C or C++
source therefore compiles without the recipe's `-D` and `-U` options and with `-include`
of a header that holds only the definitions its preprocessing reads. An analysis action
writes that header: with the source's own compile command and `-Wunused-macros`, it
preprocesses a wrapper that defines the options and then includes the source, and it
drops the definitions the compiler, Clang or GCC, reports unused. A canary definition
that no source reads must be reported too, so a compiler that reports nothing fails the
analysis instead of keeping or dropping definitions silently. A definition that the preprocessing
never reads cannot change it, so the object stays the same, and the compile reruns only
when a definition it reads changes. One analysis action covers up to 32 sources of a
compile group and directory and reruns when one of their files changes. Flipping
`disable_3d` on an Android recipe of 731 sources recompiles 278 of the 863 sources it
then has, instead of all of them. Objective-C and Objective-C++ sources keep their `-D`
options: they import implicit Clang modules, which see the command line's macros but not
a header's, so a definition the analysis reports unused could still change a module
they import. Assembly sources, such as zstd's `.S` files on Linux, keep their `-D` options
too: the analysis covers C and C++. Options of the toolchain and of `--copt`, `--cxxopt` and `--conlyopt`, such
as `-c opt`'s `NDEBUG`, stay on every command line, and the analysis preprocesses with
them. Starlark cannot read `--per_file_copt`, so with it set every source keeps all of its
definitions.

A build with `--experimental_output_paths=strip` shares more: a source recipe's native
targets declare `supports-path-mapping`, compile without module maps, and its define
analysis and code generators name output files only through their arguments, so an action
keeps one cache key in every configuration whose command and inputs it shares. Applications
with different [build profiles](#an-applications-build-profile) or engine settings then
share every object they compile alike, locally and in a remote cache. Without the flag,
nothing changes. A `.bazelrc` that removes `supports-path-mapping` with
`--modify_execution_info` must keep it for `CppCompile`, `CppArchive`, `CppLink`,
`ObjcCompile` and `DefineAnalysis`.

Engine objects compile with upstream's warning flags. Warning groups that the
Bazel C++ toolchain adds and unmodified Godot sources trigger are turned off:
apple_support's thread-safety, 64-to-32-bit and undeclared-selector warnings
on macOS and iOS, and the NDK's C++20-extension warnings for omitted variadic
macro arguments and designated initializers on Android. Other warnings,
including those from patches and custom modules, stay visible.

Each upstream generator is a separate `GodotGenerate` action with declared
file and serialized SCons `Value` inputs. Shader dependencies are expanded
transitively. Builder Python files are conservatively shared inputs: changing
them can rerun generators, while unchanged generated bytes preserve downstream
compile cache hits.

Recipe configuration runs rules_python's Python 3.14 host interpreter and target
SDK/compiler feature probes, and stops after 30 minutes. SDK provisioning and this configure phase are not fully hermetic;
the target SDK must be available on the configuring host, which for
[pinned recipes](#pin-the-recipes) is the execution platform of `:pin`. Compilation uses
Bazel's selected C++ toolchains and generators use the execution Python
from `rules_python`.

Feature facts the build cannot see stay the consumer's responsibility: a project that
needs a module only through reflection, dynamic resource paths or an external PCK must
enable it explicitly, and an opaque payload, such as a plain template file, carries only
the facts its component declares. The [platform guide](platforms.md) describes
application setup. Arbitrary custom SCsub
commands, Rust builders, custom Swift build scripts, MSVC and upstream postlink
bundling are outside the source translator's scope. Application packaging
and signing belong to the corresponding Bazel rules.

Upstream: [Godot 4.7 build system](https://docs.godotengine.org/en/4.7/engine_details/development/compiling/introduction_to_the_buildsystem.html),
[pinned Godot source](https://github.com/godotengine/godot/tree/4.7.2-stable).
