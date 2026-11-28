# Architecture

The project and pack API is in `godot/defs.bzl`; `godot/app.bzl` provides the unified
application API, which `godot/private/app.bzl` implements. Export platforms from
`godot/platforms/defs.bzl` select the operating system, CPU set and iOS environment. The
application backends, the operating-system rules `godot_app` selects, live under
`godot/platforms/private/`. `godot_android_runtime`, which generated engine hubs load, is in
`godot/platforms/private/android.bzl`.
`godot_app` selects optional macOS signing through `//godot:macos_signing`; the private
signer is `godot/platforms/private/macos_signing.bzl`.
Providers in `godot/providers.bzl` join the independent build layers.

The application context, the values of a `godot_app` its pack's export depends on
(application ID, iOS minimum version and device families, Android SDK levels), reaches the
pack export through a transition, so applications that share it share one export. The
edge from an operation to its resources resets the application context, and native code
is reached with the project context reset too, so packaging and operations share the
providers of extension and platform libraries rather than rebuilding libraries or merging
duplicate manifests for each application identity or project.

Reusable `godot_resources` declarations describe resource membership, path
relationships, the add-ons their files use and one import unit each, independently of
processing. A `godot_addon` (`godot/private/addon.bzl`) declares an add-on once: its
runtime and editor parts, roles, extensions, platform libraries on a resetting
`<name>.platform_libraries` helper, and its contributions.
`godot_project` is a configuration context and holds no resources. Each operation
macro (pack, source run, test, check, editor view, metadata sync, resource graph)
declares an internal `_godot_view` over its `deps` whose transition sets the
`//godot/private:project` context (`godot/private/context.bzl`). Every resources
target reached in that context imports its own importable files under the project's
import configuration, once per project and target platform; the view collects the
add-ons its resources use and those the project names, merges their runtime parts and
contributions with the project's configuration, stages their editor parts for the
processes of their roles, and initializes the members for the operation. A pack reaches
the extensions and platform libraries of those add-ons through an internal per-pack
native target, whose `deps` the aspects of rules_android and rules_apple follow. Import inputs remain available to the
final Godot scan without becoming export members. See [projects and resources](../public/resources.md) for configuration conflict rules
and cache boundaries.

```mermaid
flowchart LR
  Prebuilt[Checksum-pinned editor] --> TC[Editor toolchain]
  Sources[Patched engine sources] --> Configure[SCons configure graph]
  Configure --> Generate[Independent generator actions]
  Generate --> CC[rules_cc objects]
  CC --> Runtime[Engine runtime]
  Templates[Prebuilt export templates] --> Runtime
  Assets[Import units] --> Import[Independent GodotImport actions]
  TC --> Import
  Import --> Pack[GodotPack]
  Scripts[Scripts and scenes] --> Pack
  Objects[Extension library objects] --> Extension[Extension]
  Extension --> Pack
  TC --> Pack
  Pack --> Package[Application package]
  Runtime --> Package
  Extension --> Package
```

## Reuse and decisions

- `rules_cc` owns C++ compilation, discovered header dependencies, archive/link
  actions and C++ toolchain resolution. `godot-cpp` uses its upstream
  binding generator with declared outputs and C++ compilation.
- `rules_swift` compiles the iOS engine's SwiftUI entry point with the selected
  Apple toolchain.
- `rules_python` supplies Python tools and interpreters; action tools require
  no globally installed Python packages.
- `rules_apple` owns iOS linking, platform transitions, SDK/framework selection,
  signing and IPA assembly. It also supplies the macOS codesigning tool.
- `rules_android` owns Android compilation, AAR resources, manifest merging,
  dexing, JNI and APK assembly; Maven dependency resolution belongs to
  `rules_jvm_external`.
- `rules_foreign_cc` does not support SCons as one of its delegated build
  systems. Wrapping an entire SCons build would also hide the required object
  cache granularity. A configure-only translation preserves Godot's existing graph
  while exposing its actual compile and generator actions to Bazel.
- Resources remain explicit. Reflection, dynamically assembled load paths and
  arbitrary GDScript make automatic inference of all used modules/resources
  unreliable. The application declares its asset and engine-module dependency
  sets; unknown engine modules fail configuration.

## Reproducibility

Resource identities never contain Bazel output paths. Build tools receive
explicit input manifests, copy only declared inputs and isolate Godot's HOME,
configuration, cache, temporary files and log. Diagnostics and output structure
are checked even when Godot reports exit status zero.
Run manifests contain all fields for the selected execution mode; missing required
fields fail explicitly. Desktop packaging consumes `GodotRuntimeInfo`, including
its operating system, executable and bundle files.

Desktop archive timestamps, order, permissions and ownership are normalized.
Signing is a separate action. Production certificate signing runs locally and
does not upload private keychain state to a remote cache.

Source graph configuration needs a host Python and installed target
SDK/tool probes. The repository rule can receive a declared Python label and
watches configuration scripts, patches and custom-module trees. Consequently
this configure phase is host-sensitive; it is not a claim of fully hermetic SDK
provisioning. Generated compile actions use Bazel's C++/Apple toolchains.

## Build tools

The Python build tools in `tools/` are layered packages; each builds only on those below
it, which [`tools/layers.ini`](../../tools/layers.ini) states for the file lint's
import-linter:

| Package | Responsibility |
|---|---|
| `checkout`, `source_run`, `validation` | Programs `bazel run` starts on the checkout (editor view, metadata sync, runtime profile), the runner of source runs and tests, the content validation of units |
| `editor_action` | Godot processes on a staged project: imports, initialization, probes and exports, the action plugin whose record decides each one, and the isolated process environment |
| `pack` | PCKs without Godot: the format, a pack's contents, the writer and the merge of extension descriptors |
| `staging`, `resource_graph` | The files an operation stages and its project directory; the static reference graph, its queries and pack selection |
| `project`, `resources` | Godot's configuration files; the text of resources and the metadata Godot derives for files (sidecars, UIDs, node IDs, the class cache) |
| `inputs` | How a tool reaches its files: action manifests, originals and the runfiles of a program |

`engine`, `extension` and `platforms` hold the tools of engine builds, GDExtension bindings
and application packaging beside them.

## Progress messages

An action's `progress_message` is one verb from this table, then `%{label}`: Bazel prints
it on its status line, and a long label already fills one. The verbs are gerunds, as in
rules_cc, rules_java, rules_android and rules_apple (`Linking %{output}`, `Building %{output}`,
`Validating %{label}`, `Bundling %{label}`). The mnemonic names the action's kind in
`--subcommands`, the execution log and BuildBuddy, so the message neither repeats it nor
says what the action reads.

| Verb | Actions | Mnemonics, for example |
|---|---|---|
| Importing | The editor converts a unit's assets. | `GodotImport` |
| Initializing | The editor derives a view's script-class and UID caches. | `GodotInitialize` |
| Exporting | The editor exports, or the writer writes, a pack's PCK or its configuration. | `GodotPack`, `GodotPackConfiguration`, `GodotPackWrite` |
| Probing | The editor reports facts Godot decides. | `GodotImportableSuffixes`, `GodotShellAssets` |
| Validating | A check whose product is its pass or fail: scripts and scenes, resource references, metadata, flags, export options, the engine version, Maven minimums. | `GodotValidate`, `GodotResourceGraphCheck` |
| Generating | A build tool derives files from its inputs: configuration, class fragments, unit interfaces, metadata, the resource graph, pack content and descriptors, shell files, engine sources, bindings, an icon, a `.dSYM`. | `GodotProjectConfig`, `GodotMetadata`, `GodotShellFile` |
| Bundling | Files are put into an archive or a bundle. | `GodotDesktopPackage`, `GodotDebugSymbols` |
| Stripping | Native code loses its symbols. | `GodotStrip` |
| Signing | A bundle is code signed. | `GodotMacosSign` |

An output name in parentheses follows the label where one target runs the same verb for
outputs that vary with its content or configuration: a unit (`Importing <unit label>`), a
shell file (`Generating %{label} (Info.plist)`), a configuration purpose, a kind of metadata
check, a binary's `.dSYM`. Fixed stages of one rule share a verb and a label.

A new action takes a verb of the table, or extends the table with the action's row.

## Tests

White-box tests beside the implementation packages cover build contracts and
diagnostics; the consumer scenarios in the repository's `e2e/rules_godot/` export and run real
projects as a consumer,
through the public module boundary and the root module's artifact test rules in `tools/artifact_tests/`. Cache checks compare selected Bazel actions and output bytes.
Repository commands and controlled fixture inputs are documented in the
[fixture catalogue](../../../docs/internal/verification-recipes.md#regression-fixtures).

## Primary references

- [Bazel toolchains](https://bazel.build/extending/toolchains)
- [rules_cc](https://github.com/bazelbuild/rules_cc)
- [rules_python](https://github.com/bazel-contrib/rules_python)
- [rules_apple](https://github.com/bazelbuild/rules_apple)
- [rules_android](https://github.com/bazelbuild/rules_android)
- [rules_foreign_cc supported systems](https://github.com/bazel-contrib/rules_foreign_cc)
- [Godot SCons build system](https://docs.godotengine.org/en/4.7/engine_details/development/compiling/introduction_to_the_buildsystem.html)
- [Godot command line export](https://docs.godotengine.org/en/4.7/tutorials/editor/command_line_tutorial.html)
