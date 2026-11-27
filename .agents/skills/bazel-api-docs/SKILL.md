---
name: bazel-api-docs
description: Document and maintain rules_godot's Bazel APIs and the registry's documentation metadata. Use when adding, changing, reviewing or removing public Starlark rules, macros, providers, aspects, repository rules, module extensions, tag classes, toolchains or configuration APIs.
---

# Bazel API documentation

Treat the Starlark definitions as the API documentation's source of truth: the
Bazel Central Registry renders it from their extracted docstrings. Write English
documentation using Bazel's `.bzl` style and Stardoc conventions. Read
[upstream practices](references/upstream.md) when changing this standard or
its tooling; use [the maintenance guide](../../../rules_godot/docs/internal/api-reference.md)
for public entrypoints and metadata details, and the
[API documentation recipe](../../../docs/internal/verification-recipes.md#api-documentation)
for its checks.

## Organize and cover the complete surface

- Give public consumers clear, task-oriented entrypoints. Keep core project
  APIs in `godot:defs.bzl`; use dedicated extension, platform, engine,
  toolchain, repository and provider modules for those tasks. Keep platform
  dependency boundaries rather than forcing every API into one facade.
- List each public entrypoint in `_BCR_DOCS` of `rules_godot/BUILD.bazel`; the
  registry documents every symbol it exports, so an entrypoint exports only its
  public symbols. Every other `rules_godot/godot/**/*.bzl` module is
  implementation. A public name does not become private merely because it is
  absent from the facade.
- Give each symbol exactly one public load path, also under another name.
  Re-export private implementations only through their intended entrypoint.
- Keep implementation modules under `private/` and restrict their actual
  Starlark load visibility. Directory names and BUILD source visibility alone
  do not enforce Starlark load visibility.
- Helpers loaded by generated repositories are implementation details, not
  consumer APIs: keep them out of `_BCR_DOCS`. Keep useful
  implementation explanations in source comments and docstrings. Never export
  them through public consumer entrypoints, even under a different name.
- Generated repositories can have caller-chosen names. Their implementation
  modules therefore need explicit public load visibility for cross-repository
  loads, despite being outside the supported public API. Preserve this
  technical access when changing them.
- Document repository configuration and the library targets consumers actually
  use. For godot-cpp, keep `godot_cpp_bindings` and the generated
  `@godot_cpp//:godot_cpp` dependency in `godot_cc_extension` documented; its
  binding-generation rule is an implementation detail.
- Breaking changes are fine (root `AGENTS.md`): when moving an API, update all
  loads, examples, tests and generated BUILD files directly, without retaining
  previous load paths or adding compatibility exports.
- Cover all public rules, legacy and symbolic macros, functions, providers,
  aspects, repository rules, module extensions and their tag classes. Include
  supported constants, structs, transitions or build settings when introduced.
- Keep a module docstring in every `.bzl`, including private implementation
  modules. Private helpers need explanations where their contracts are subtle;
  they are not part of the registry's documentation.
- Document consumer-facing target labels and the `ToolchainInfo.godot`
  contract as well as callable Starlark APIs. Examples, tests, generated
  artifacts and files in private packages are not automatically public APIs.

## Write entries for independent lookup

API documentation is a reference. Readers often arrive directly at one rule,
attribute, parameter or provider field, with little context beyond basic Bazel
knowledge. Each entry should let them quickly understand what the element is,
why it exists and what effect it has when used.

Lead with the element's purpose and meaning from the consumer's perspective.
Describe concretely what a value represents or controls, which inputs or
outputs it affects, and when a caller would use it. Explain necessary domain
terms locally and use a short example when it makes the intention clearer.
Restating the identifier or describing only an implementation mechanism does
not explain the contract.

For example, describe `runtime_deps` as resource targets whose files must be
included in the project because scripts load them dynamically, such as through
`load()`. State that their files become project members, just like `deps`.
This explains both the attribute's purpose and its effect.

Keep the essential meaning in the entry itself. Readers should not need to
inspect source code, read entries in order or follow a guide link to understand
it. Links can provide deeper context and workflows; the entry should remain
concise enough to scan as a reference.

Place `doc` first among the named arguments of Starlark API definitions and
attributes, before implementation details and configuration options.

Follow the source layout in `AGENTS.md`: multiline documentation starts below
its opening triple quotes. Align its first text line with the remaining prose
and closing quotes at the surrounding block's indentation, including function
docstrings and rule/attribute `doc` strings. Keep parameter descriptions and
examples indented relative to that prose. Keep short docstrings on one line.
Use the [verification policy](../../../docs/internal/verification.md) for verification timing
and the [API documentation recipe](../../../docs/internal/verification-recipes.md#api-documentation)
for its checks.

## Write the contract where Bazel can extract it

| API kind | Documentation source | Required contract |
| --- | --- | --- |
| Module | Leading docstring | Purpose, supported entrypoints and relevant setup/guide links |
| Rule, aspect, symbolic macro | `doc` and each public `attr.*(doc = ...)` | Inputs, accepted providers, returned providers, execution or configuration behavior, constraints |
| Legacy macro or public function | Docstring with `Args:`; `Returns:` when returning a value | Every parameter, forwarding through `**kwargs`, created targets/visibility or return value |
| Provider | `provider(doc = ..., fields = {name: description})` | Purpose, every field's type/shape, optionality, meaning and producer/consumer relationships |
| Repository rule | `doc` and each public attribute's `doc` | Acquisition/pinning, generated repositories/targets, host tools, environment inputs, failure conditions |
| Module extension and tags | `module_extension(doc = ...)`, `tag_class(doc = ...)`, attribute docs | Root/transitive conflict resolution, generated names, `use_repo`, registration and version constraints |
| Other exported value | Supported Starlark doc comments (`#:`) or a supported extraction mechanism | Type and meaning; ensure the extracted metadata actually includes it |

Document every public parameter and attribute, including tiny functions and
inherited/shared attribute dictionaries. Buildifier's short-function exemptions
are weaker than this repository's standard. If a provider has an initialization
callback exposed in its schema, document its parameters too.

Let Bazel generate signatures, attribute types, required/default values and
canonical load statements. Explain what those values *mean*: empty values,
`None`, path roots, units, accepted enums, mutual exclusion and platform/version
restrictions where relevant. Do not maintain a second handwritten signature or
attribute table in a guide. Shared attribute definitions should share their docs;
explicit overrides must retain accurate documentation.

Give each public operation a small realistic example or a direct link to a
maintained example covering it. A provider module may share one consumption
pattern across its providers. Distinguish `MODULE.bazel`, `BUILD.bazel` and rule
implementation contexts. Name prerequisite targets and setup; mark placeholder
artifacts as illustrative. Prefer existing tested examples to new untested
mini-projects.

Explain custom providers and runtime/runfiles behavior when consumers use them.
Toolchains must distinguish
execution platform from target platform; packaging APIs must state relevant
SDK, signing and native-linking requirements. Describe actual error conditions.
Document deprecations with their replacement and migration implications.

Keep guides for setup, composition, architecture and troubleshooting. Link from
the reference instead of duplicating long explanations. Use plain prose and
small tables/examples; use diagrams only for relationships that need them.

## Extract the registry's metadata

1. Update definitions and their documentation together. Regenerate the
   `bzl_library` targets of new modules with Gazelle
   (`bazel run //tools/gazelle:update`). Choose the sole entrypoint of each
   new public symbol, list a new entrypoint in `_BCR_DOCS`, and update guides
   and examples to use that load path.
2. Bazel's built-in `starlark_doc_extract` extracts the metadata from the
   declared `bzl_library` dependencies: `bazel build //:bcr_docs` in
   `rules_godot/`. Do not replace Bazel evaluation with regexes or a Python
   Starlark emulator.
3. Follow the [API documentation recipe](../../../docs/internal/verification-recipes.md#api-documentation)
   for checking, and the [verification policy](../../../docs/internal/verification.md)
   for completion evidence.
4. For a BCR documentation archive, use only `//:bcr_docs` of the ruleset's
   module. Archive publication is a separate release integration.

Buildifier's docstring warnings check only module and function docstrings, and
exempt short functions. The documentation of rules, macros, aspects, attributes,
provider fields and tag classes, accurate behavior, useful examples,
compatibility implications and explanatory quality require source review.
