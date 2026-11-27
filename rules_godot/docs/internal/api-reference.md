# Maintaining the Bazel API documentation

The ruleset's API documentation is its docstrings. The release archive's documentation
metadata carries them to the [Bazel Central Registry](https://registry.bazel.build/modules/autoload_rules_godot), which renders them; the
repository keeps no generated reference of its own. Each symbol has one public load path.
Platform setup, tutorials and architecture remain in the guides.

## Public entrypoints and implementation modules

The public entrypoints are listed in `_BCR_DOCS` of the ruleset's
[root BUILD file](../../BUILD.bazel). The registry documents every symbol an entrypoint
exports, so an entrypoint exports only its public symbols. Every other `godot/**/*.bzl`
module is implementation, with no registry documentation.

Use `godot:defs.bzl` for projects, resources, exports, runs and tests. Use the
dedicated extension, platform, engine, toolchain, repository and provider
entrypoints for those tasks. Application packaging and optional signing use the symbolic
`godot:app.bzl` entrypoint; engine acquisition keeps dedicated modules. The public providers,
`GodotPackInfo` and `GodotDesktopAppInfo`, live in `godot:providers.bzl` and name the rules
that produce them; the providers between the ruleset's own rules live in
`godot/private:providers.bzl`. `godot/testing:adapter.bzl` holds `adapter_test`, the test
adapter that test framework modules such as autoload_gdunit build their tests on.

Public API that may still change incompatibly carries this notice at the end of its
documentation, as rules_python marks its volatile API: "Volatile API: public, but it may
still change incompatibly in a release of rules_godot. A module that builds on it pins the
rules_godot release it works with." `adapter_test` is the only such API.

Core rule implementations live in `godot/private/`; the shared desktop
implementation lives in `godot/platforms/private/`. Their explicit Starlark
load visibility permits the public entrypoints to load them and prevents
direct consumer loads. Implementation re-exports expose each symbol through
its sole public entrypoint.

The binding and source-generation helpers are implementation details. Generated
repositories can have caller-chosen names, so their source modules explicitly
retain public load visibility. This technical requirement does not make them
consumer entrypoints: they have no registry documentation. No other module loads an
implementation module: the repository's examples, consumer scenarios and add-on modules load
public entrypoints only ([B3](../../../docs/internal/verification-architecture.md#boundary-rules)).
Keep implementation notes in source comments and docstrings.

Consumers configure `godot_cpp_bindings` in `MODULE.bazel`, then pass its
generated C++ library as `deps = ["@godot_cpp//:godot_cpp"]` to
`godot_cc_extension`. These are the public contracts documented in `godot_cpp_bindings`'
docstring and the [C++ integration guide](../public/gdextension.md#c-bindings).

Breaking changes are fine ([AGENTS.md](../../../AGENTS.md)), so API moves update every
repository consumer directly without retaining previous load paths.

## Outputs and generated targets

Keep four distinct interfaces apart:

| Interface | Purpose |
| --- | --- |
| `DefaultInfo` | Default requested files and, for executable targets, run behavior |
| `OutputGroupInfo` | Explicitly requested output subsets such as archives or symbols |
| Public companion target | A distinct operation or analysis/configuration boundary |
| Semantic provider | Structured input to consuming rules |

Prefer an output group when the difference is only which files a build requests. A convenient
label alone does not justify another public macro target: callers can select a group through
`filegroup(output_group = "...")` when an attribute of another rule needs a label. Private
filegroups of this kind inside a macro serve such attributes; they are not additional public APIs.

Keep a separate target when it represents a runnable operation, a real Bazel test, or a
required analysis/configuration boundary. Output groups select outputs/actions; they do not
prune the producing target's configured dependency graph, analysis-time checks or toolchain
resolution. Transitive validation still applies. Document that distinction whenever a
companion target promises fewer prerequisites, for example symbol access independent of signing.
Use providers for semantic file access in custom rules instead of scraping paths or selecting
arbitrary default files. Test execution reports follow Bazel's test-result interfaces.

Additional macro target names follow [RG002](../../../docs/internal/conventions.md#rg002): `<name>.<role>`.
The convention, including slash-suffixed rules_android basenames, is owned there. A dotted name does
not grant public visibility, and output-group keys and artifact filenames do not inherit
the target separator.

Public guides link to the registry's documentation and show short build, run, output group
and companion target examples.

## Metadata for the BCR documentation archive

`bazel build //:bcr_docs` in `rules_godot/` extracts, with Bazel's `starlark_doc_extract`, the
`.binaryproto` metadata of each public entrypoint. Each extraction depends on
the `bzl_library` that Gazelle generates beside its module
([generated BUILD declarations](../../../docs/internal/verification-recipes.md#generated-build-declarations)),
so a load without a library fails the build. The release script packs exactly these files
into the documentation archive that the registry renders, as
[Releasing](../../../docs/internal/releasing.md) describes.

When a public entrypoint is added, moved or removed, update `_BCR_DOCS` together with the
source and its consumers.

Modules without a public `bzl_library` that the extractions need otherwise are named in the
comment on their `deps` in the root BUILD file.

## Third-party documentation dependencies

`rules_android` 0.8.0 exports its API `.bzl` files, but its transitive
`//rules:bzl` documentation library has restricted visibility. The ruleset's module
applies `third_party/rules_android/doc_visibility.patch` to expose that single
library for `starlark_doc_extract`. `rules_android_ndk` 0.1.5 exports no files; the
module applies `third_party/rules_android_ndk/doc_visibility.patch` to export
`rules.bzl`, which `godot_android_toolchains` loads. Both change BUILD visibility only and,
as overrides, apply only where the ruleset is the root module, never to its consumers.
Rulesets that build on rules_android publish no registry documentation or document no
Android rules; `godot_app` loads rules_android, so its extraction needs the patches.
Remove each patch once its upstream file is publicly accessible; do not disable
Bazel's visibility checking.

## Writing standard

The repository skill
[bazel-api-docs](../../../.agents/skills/bazel-api-docs/SKILL.md) defines the writing
and review standard. Its [upstream references](../../../.agents/skills/bazel-api-docs/references/upstream.md)
explain which practices come from established rule sets.

Buildifier's docstring warnings ([.buildifier.json](../../../.buildifier.json)) require
module and function docstrings with their arguments and return values, and exempt short
functions. Nothing checks the documentation of rules, macros, aspects, attributes, provider
fields and tag classes; review it together with semantic correctness, useful examples and
accurate support claims.
