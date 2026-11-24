# Engines

A Godot build needs two engines: the **editor**, which imports and exports projects, and
the **runtime**, the export template an application packages. rules_godot resolves both
as Bazel toolchains, so projects, packs and apps name no engine. Register Godot's official
builds, build an engine from a pinned source with your own modules and patches, or mix
both: each role, platform and CPU, plus, for runtimes, the iOS environment and the
variant, is one slot, and the first registered candidate for a slot wins. A build uses
one engine, the default one or the one `--@autoload_rules_godot//godot:engine` names, and takes no
other engine's components.

| You want | Use |
| --- | --- |
| The official editors and templates of a release | [`godot_engines.prebuilt`](#use-a-prebuilt-engine) |
| Your own modules, patches or a fork in some slots | [A source recipe and a component](#build-an-engine-from-source), registered ahead |
| Source-built engines for many slots, with one build policy | [`godot_engines.source_build`](#declare-a-source-build) |
| Components of different sources in one engine | [`--extra_toolchains`](#replace-slots) or [`select()`](#choose-between-prepared-recipes) |
| An engine that only the builds naming it use, such as one with your own module | [An engine name](#name-an-engine) |

The supported versions are **>=4.7.2 <5.0.0**; [versions](versions.md) lists the built-in
release pins.

## Use a prebuilt engine

1. Declare a prebuilt engine and register its components in `MODULE.bazel`:

   ```starlark
   godot_engines = use_extension("@autoload_rules_godot//godot:extensions.bzl", "godot_engines")
   godot_engines.prebuilt(name = "godot", version = "4.7.2")
   use_repo(godot_engines, "godot")
   register_toolchains("@godot//toolchains:all")
   ```

2. Build a pack or app as usual; `bazel build //path/to:app` downloads only the editor
   of your host and the templates the app needs.

For a catalogued version, `version` is enough: the hub covers the official editors per
editor platform, the Linux and macOS runtimes, the iOS device and simulator runtimes and
the Android runtimes. Where the official artifacts lack a runtime slot, the hub builds it
from the release's sources:

- Official Android shell AARs are release builds, so the Android debug runtimes are
  source-built, unless you pin `android_debug_shell_urls` and
  `android_debug_shell_integrity`.
- The official 4.7.2 iOS simulator libraries contain x86_64 code only, so the arm64
  simulator runtimes are source-built ([iOS](platforms.md#source-built-engines)).

These source recipes enable the modules Godot's official builds enable by default
(`default_modules` of a [source build](#declare-a-source-build)); iOS recipes leave out Vulkan, which would need
the MoltenVK SDK on the configuring Mac, and keep Metal and OpenGL. Like any
[source build](#declare-a-source-build), a recipe downloads the sources, configures and
compiles only when a build selects its slot, on a host Godot accepts for its platform, such
as a Mac for iOS. The prebuilt slots keep the official artifacts. To fail the missing slots
instead, or to fill them with your own engine, set `build_missing_runtimes = False`, or
register your components [ahead of the hub](#replace-slots). Only catalogued releases
with pinned sources build missing runtimes. A hub that pins its own templates or editors
builds none, and one that pins its own Android shell builds no Android runtimes, since the
upstream sources would not match a fork's artifacts. `bazel fetch --all` and `bazel vendor` configure every recipe, including the iOS
ones, which only a Mac can; fetch the targets you build instead, or set
`build_missing_runtimes = False` where you need a whole-module fetch.

For a release outside the catalogue, or an archive built elsewhere, pin each artifact.
Digests are Subresource Integrity strings; explicit values replace catalogue entries:

```starlark
godot_engines.prebuilt(
    name = "godot_beta",
    version = "4.8.0-beta1",
    android_shell_urls = ["https://github.com/godotengine/godot-builds/releases/download/4.8-beta1/godot-lib.4.8.beta1.template_release.aar"],
    android_shell_integrity = "sha256-G1KpV92jFIn4OirzO17zy2euXFLyE40BSATgYs9MI5Y=",
)
```

`editor_urls`, `editor_integrity` and `editor_binaries` are keyed by editor platform
(`linux_x86_64`, `linux_arm64`, `macos`, `macos_arm64` or `macos_x86_64`);
`templates_urls`, `templates_integrity`, `templates_macos_cpus`, `templates_linux_cpus` and
`ios_simulator_cpus` describe the export templates. The
[API documentation](https://registry.bazel.build/modules/autoload_rules_godot) of `godot_engines` lists every attribute and the
generated targets. Names are shared with the `source` and `source_build` tags: a root module's
request owns its name, identical requests from dependencies share one hub, and
conflicting ones fail.

## Replace slots

Registration order decides between the candidates of one engine for a slot. Register a set
before the one it overrides; it replaces only the slots it covers:

```starlark
register_toolchains(
    "//engines/custom:all",         # wins for its slots
    "@godot//toolchains:all",       # every other slot
)
```

A registration set is any package of components. For one invocation,
`--extra_toolchains=//path/to/engines:all` puts a set ahead of every registered one;
`--extra_toolchains` gives its last entry priority. Each component also has a
`<name>.toolchain` target, so one slot can be prioritized alone, such as only the editor:

```sh
bazel build //path/to:app --extra_toolchains=//path/to/engines:editor_macos_arm64.toolchain
```

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

An engine name keeps an engine apart: its components fill slots only in builds whose
`--@autoload_rules_godot//godot:engine` names it, and such a build takes no component of another
engine, whatever the registration order. Components that name no engine form the default
engine, which builds use while the flag is empty. Name the engine on its tag, or on each
component of your own registration set with `engine`:

```starlark
godot_engines.source_build(
    name = "godot_studio",
    engine = "studio",
    # ... sources, modules and platforms
)
```

```bash
bazel build //path/to:app --extra_toolchains=@godot_studio//toolchains:all --@autoload_rules_godot//godot:engine=studio
```

A slot the named engine does not cover has no candidate: a target platform it lacks fails
analysis with the missing role, rather than taking the default engine's runtime. An
execution platform it has no editor for is skipped: Bazel resolves the actions that run the
editor on the next execution platform with one, such as this host behind a remote Linux
executor, and the build's other actions stay where they are. A `config_setting` on the flag
gates the targets that need the engine:

```starlark
config_setting(
    name = "studio_engine",
    flag_values = {"@autoload_rules_godot//godot:engine": "studio"},
)
```

## Build an engine from source

A source build compiles Godot from an immutable archive, an upstream release or a fork,
with your modules, patches and options. The `source` tag of `godot_engines` pins the
archive by digest and its version; the `source_build` tag configures one recipe per slot
from it: SCons evaluates the feature graph once, and Bazel compiles each object and runs
each code generator as its own cached action.

```starlark
godot_engines = use_extension("@autoload_rules_godot//godot:extensions.bzl", "godot_engines")
godot_engines.source(
    name = "godot_sources",
    sha256 = "e954996374cbd1cb5d72e0e3781cc537408e6ce73b010b12c6c2f308a820690a",
    strip_prefix = "godot-4.7.2-stable",
    urls = ["https://github.com/godotengine/godot/archive/refs/tags/4.7.2-stable.tar.gz"],
    version = "4.7.2",
)
godot_engines.source_build(
    name = "my_engine",
    source = "@godot_sources//:source.json",
    platforms = ["macos"],
    cpus = ["arm64"],
    build_targets = ["template_release"],
    enabled_modules = ["gdscript", "text_server_fb", "my_module"],
    custom_modules = {"//native/my_module:config.py": "my_module"},
    patches = ["//engine:fix.patch"],
    renderers = ["gl_compatibility"],
)
use_repo(godot_engines, "godot_sources", "my_engine")
register_toolchains("@my_engine//toolchains:all")
```

`version` is the archive's canonical version as its `version.py` names it, such as `4.7.2`
or `4.8.0-beta` for an unnumbered beta; a recipe whose sources say otherwise fails.
`build_targets` are `editor`, `template_debug` and `template_release`; iOS recipes add
`ios_environments`, `device` or `simulator`. Editors compile for the execution platform.
macOS and iOS recipes compile for the deployment target Godot's own build sets, raised to what the libc++ of current Xcode supports: 11.0 on macOS (Godot sets 10.13 on Intel Macs) and 15.0 on iOS (Godot sets 14.0), whatever
the build's `--macos_minimum_os` or the application's minimum says, so one engine build
serves every application; an application's minimum is its bundle's and its extension
libraries', set by [`macos_minimum_os_version`](platforms.md#linux-and-macos) and
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
and `forward_plus`. The recipe derives the drivers from them, OpenGL for Compatibility and
for the other two the platform's RenderingDevice driver, Metal on Apple platforms and Vulkan
on Android and Linux, so `build_options` may not set `opengl3`, `metal` or `vulkan` too.
Godot 4.7 builds both RenderingDevice methods or neither; 4.8 builds each on its own and
leaves RenderingDevice out without them. Godot's iOS Simulator build has no Metal, so a
Simulator engine runs `gl_compatibility` only. An application checks the rendering method
its project uses on its platform, `rendering/renderer/rendering_method` with its `.mobile`
override, against its engine's: Godot has no fallback for a method an engine lacks, so the
build fails instead of the application at start. Without `renderers`, a recipe keeps
Godot's drivers and its `build_options`, and nothing is checked. The example keeps the
Compatibility renderer; set the project's rendering method to `gl_compatibility`. Some
options apply to templates only, such as `disable_3d`; an editor recipe rejects them.

The module list is an allowlist: other modules start disabled, unless
`default_modules = True` starts from the modules Godot enables by default for the platform,
as its official builds do. Without a list, a recipe enables `gdscript` and `text_server_fb`,
or, with `default_modules = True`, only Godot's defaults, which include `text_server_adv`.
An engine takes one text server: `text_server_adv` and `text_server_fb` define the same
symbols, so a recipe that enables both fails. Required
upstream dependencies are added transitively (`theora`, for example, needs
`vorbis` and `ogg`); optional dependencies remain disabled. Editor builds also
include upstream's required `freetype`, `regex` and `svg` modules. Misspelled
modules, cycles, unreadable dynamic dependency declarations and modules rejected
by Godot's configuration fail with an error.

The app owner chooses the allowlist. Reflection, dynamic resource paths,
extensions and external PCKs prevent reliable inference of every engine module
from a project scan.

`build_profile` takes a Godot build profile, a `.gdbuild` file such as the editor's
Engine Compilation Configuration writes. Its `disabled_classes` leave those classes out of
the engine, so linking drops their code; an application whose scenes, resources or scripts
need a disabled class fails when it loads them. Its `disabled_build_options` must agree with
`build_options`: a profile that sets an option the recipe sets differently fails
configuration. The profile is part of the recipe's inputs and of a lock file's pins.

```starlark
godot_engines.source_build(
    name = "my_engine",
    source = "@godot_sources//:source.json",
    platforms = ["ios"],
    build_profile = "//engines:game.gdbuild",
)
```

Patches use the host `patch` executable with fuzz disabled and strip level 1
(`patch_strip`); every hunk must apply. `build_options` accepts upstream options;
options rules_godot controls are rejected: Godot's `platform`, `arch` and `target`, the iOS
simulator switch, module selection, raw `profile` and `build_profile` paths (use the
`build_profile` attribute),
`optimize` and `lto`, which follow the [optimization](#optimization) settings, and
`debug_symbols`, which follows Bazel's flags as in [debug symbols](#debug-symbols). Generator actions use hermetic Python 3.14.
Builders must read literal keys from `env` or pass it directly to named Python
helpers with an `env` parameter. Dynamic callbacks, environment aliases and
unsupported forwarding fail configuration instead of silently omitting inputs.

## Declare a source build

A source build applies one build policy (sources, modules, patches and options) to every
slot you select: the `source_build` tag declares one source recipe per slot and a hub with
the same layout as a prebuilt one, `@<name>//toolchains:all`. The `source` tag declares the
archive in the same extension:

```starlark
godot_engines.source(
    name = "godot_sources",
    sha256 = "e954996374cbd1cb5d72e0e3781cc537408e6ce73b010b12c6c2f308a820690a",
    strip_prefix = "godot-4.7.2-stable",
    urls = ["https://github.com/godotengine/godot/archive/refs/tags/4.7.2-stable.tar.gz"],
    version = "4.7.2",
)
godot_engines.source_build(
    name = "godot_source_build",
    source = "@godot_sources//:source.json",
    platforms = ["android", "ios"],
    cpus = ["arm64"],
    build_targets = ["template_release"],
    ios_environments = ["simulator"],
    build_options = {"vulkan": "no", "opengl3": "yes"},
)
use_repo(godot_engines, "godot_source_build", "godot_sources")
register_toolchains("@godot_source_build//toolchains:all", "@godot//toolchains:all")
```

`platforms` is required; empty `cpus`, `build_targets` and `ios_environments`
select every valid slot, and the source build never generates invalid ones such as an iOS
editor. Every recipe of a source build shares its modules, patches and options; slots with
different policies belong to separate source builds. Declaring one configures nothing:
a recipe is configured, with its operating system's SDK, only when a build needs its
payload. Godot configures a recipe only on a host its build scripts accept for that
platform; macOS, for example, configures no Linux recipe. A build on macOS that registers
a Linux execution or target platform, such as a remote executor, selects the hub's Linux
slots and fails, rather than taking another engine's editor; [pin the
recipes](#pin-the-recipes) so that any host builds every slot. Hub components are named
`editor_<platform>_<cpu>` and `runtime_<platform>_<cpu>[_<environment>]_<variant>`; the
recipes are `<name>_<platform>_<cpu>[_<environment>]_<build_target>`.

### Pin the recipes

A lock file pins the build graph of every recipe of a source build, as `maven_install.json`
pins a Maven resolution: the recipe repositories read it and configure nothing on the
host, so a Mac declares the Linux editor's actions and a remote Linux executor compiles
them. Name the file with `lock_file` and write it with the hub's `:pin`:

```starlark
godot_engines.source_build(
    name = "godot_source_build",
    lock_file = "//engines:godot_source_build.lock.json",
    # ... as above
)
```

```bash
bazel run @godot_source_build//:pin --config=remote
```

The package of `lock_file` must exist; the file itself is created by the first pin, and
until then every recipe fails with the pin command. `:pin` configures each recipe in a
build action on an execution platform of an operating system Godot accepts for it: Linux
recipes on a Linux executor, macOS and iOS recipes on a Mac, Android recipes on any.
Without a Linux execution platform, such as a remote executor, a Mac cannot pin Linux
recipes; a Linux CI job can run the same command.

Each pin records the digest of what its graph depends on: the archive, the patches, the
recipe's platform, CPU, target, modules and options, its build name, the SCons release and
rules_godot code that capture the graph, and of each custom module its `SCsub`,
`config.py` and shader sources and the paths of its other files. A recipe whose digest no
longer matches, after such a change or a rules_godot upgrade that changes that code,
fails with the pin command instead of reconfiguring silently; editing a custom module's
C++ code keeps its pin, and so does a rules_godot upgrade that changes only how a graph
becomes Bazel targets. Commit the lock file with the change that requires it.

### Android shell libraries

An Android runtime is Godot's Java/Kotlin library, the Android shell library, with the
engine library inside. Android source builds build the shell library from the same patched
source, so a fork's Java changes come with its sources.
rules_godot adds the shell library's Maven dependencies, including `kotlin-stdlib` at
Godot's Kotlin version, to your shared `maven` repository; repin it after adding
rules_godot (`RULES_JVM_EXTERNAL_REPIN=1 bazel run @maven//:pin`). The contribution pins
`listenablefuture` 1.0, which the shell library's AndroidX dependencies reference; an
application that packages Guava declares Guava's empty `listenablefuture` placeholder
artifact instead. Java and Kotlin target Godot's level per target, so no Kotlin toolchain
is registered.

An Android plugin that compiles against Godot's classes, such as `GodotPlugin`, depends
on the hub's `@godot//android:plugin_api`. It supplies the shell library's classes for
compilation only; the application packages the runtime its variant selects, so the
classes appear once in the app.

## Choose between prepared recipes

The payload of a component may be a `select()`, so a build setting can choose between
recipes of the same slot; only the selected recipe is configured:

```starlark
godot_runtime_component(
    name = "runtime_macos_arm64_release",
    platform = "macos",
    cpu = "arm64",
    variant = "release",
    version = "4.7.2",
    runtime = select({
        ":minimal": "@godot_minimal//toolchains:runtime_macos_arm64_release",
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
`4.7.2.stable.custom-git.d33b04459`. `Engine.get_version_info()` returns the
build name as `build` and the full hash as `hash`, the startup line and crash
reports print them, and on Android the engine AAR's manifest names the same
version (see [Android shell libraries](#android-shell-libraries)).
This tells a crash report's engine apart from the official build of the same
version and from other custom builds. The recipe's `build_name` attribute sets the
build name, `custom` by default.

The hash and Godot's version time stamp take the place of a Git commit and its
time. Which ones the engine names depends on Bazel's stamping:

| Build | Origin | Hash | Time stamp | Example |
| --- | --- | --- | --- | --- |
| `--stamp` with `STABLE_GIT_COMMIT` in the workspace status | `git` | That commit | `STABLE_GIT_COMMIT_TIMESTAMP`, else none | `4.7.2.stable.custom-git.d33b04459` |
| Otherwise | `bazel` | Hash of the engine's declared inputs | None | `4.7.2.stable.custom-bazel.c5058d28e` |

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

Both apply to the engine's own code only, after the build's `--copt` and `--linkopt`, so
their level wins over the toolchain's and the command line's there, while extensions and
application code keep the build's flags. Other compilation modes keep Bazel's levels: `-c dbg`
debugs the engine unoptimized whatever the settings say. Prebuilt engines are unaffected.

For the smallest release engine of an application:

```sh
bazel build //path/to:app -c opt \
  --@autoload_rules_godot//godot:engine_optimize=size_min \
  --@autoload_rules_godot//godot:engine_lto=full
```

An application can set both for its own engine with `godot_app`'s `engine_optimize` and
`engine_lto`, which override the build's settings; one recipe then serves a small release
application beside a fast debug one, each with an engine built for it:

```starlark
godot_app(
    name = "game",
    pack = ":pack",
    application_id = "com.example.game",
    engine_optimize = "size_min",
    engine_lto = "full",
)
```

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
your source build's name:

```sh
bazel build //path/to:target -c opt --per_file_copt='external/autoload_rules_godot[+][+]godot_engines[+]my_engine_.*@-g'
```

The engine links without Bazel's `--strip`, so its debug information reaches
the applications' debug symbols; applications strip the copy they package as
`--strip` asks.

Applications provide the engine as part of their
[debug symbols](platforms.md#debug-symbols):

| Operating system | Where the symbols are |
| --- | --- |
| Android | `libgodot_android.so` with its DWARF and symbol table in `<name>_debug_symbols.zip` |
| iOS | The application's dSYM includes the engine; build with `--apple_generate_dsym` |
| macOS | The runtime's `.dSYM` has the engine's DWARF; build with `--apple_generate_dsym`, without which it names engine functions only |

Debug information names sources relative to the execution root, such as
`external/autoload_rules_godot++godot_engines+my_engine_macos_arm64_template_release/core/object/object.cpp`, so engine
bytes do not depend on the build machine and stay cacheable.
`separate_debug_symbols` is rejected: Bazel does not run Godot's symbol extraction
after linking.

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

Feature macros follow the same rule. A build option such as `disable_3d` or `xr` adds a
macro such as `_3D_DISABLED` to the compile options of every source, and every `-D`
option is part of a compile action's cache key. Each source keeps only the feature
macros that a file it reaches can read, so flipping `disable_3d` reruns the sources
whose files test `_3D_DISABLED`, about a hundred of an Android engine's 731, instead
of all of them. Feature macros are the names that end in `_ENABLED` or `_DISABLED`
and that the implementation does not reserve, which `__` or `_` and a capital letter
start; other macros, such as `NDEBUG` or `_FILE_OFFSET_BITS`, which toolchain and
system headers read, stay on every source. A dropped macro that a file reads would
compile silently into a different object, so the scan keeps a macro whenever it cannot
rule out a read: when its name is a word anywhere in a file the source reaches, comments
and strings included, or in the value of another `-D` option, or when token pasting
(`##`) or a generator can assemble its name. Pasting is followed through the literal
operands of `##`, the arguments of macros that paste their parameters or pass them on,
and the words those arguments expand to; a generated file can contain any word of its
generator's code, data and text inputs. Feature macros that most of the engine reads,
such as `DEBUG_ENABLED` and `THREADS_ENABLED`, still rebuild most of it.

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

Recipe configuration uses a local Python 3.9+ and target SDK/compiler feature
probes. The `python` attribute can supply a declared executable instead of PATH
discovery. SDK provisioning and this configure phase are not fully hermetic;
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
