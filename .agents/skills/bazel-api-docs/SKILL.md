---
name: bazel-api-docs
description: Document and maintain rules_godot's Bazel APIs and CI documentation checks. Use when adding, changing, reviewing or removing public Starlark rules, macros, providers, aspects, repository rules, module extensions, tag classes, toolchains or configuration APIs.
---

# Bazel API documentation

Treat the Starlark definitions as the API documentation's source of truth: the
Bazel Central Registry renders it from their extracted docstrings. Write English
documentation using Bazel's `.bzl` style and Stardoc conventions. Read
[upstream practices](references/upstream.md) when changing this standard or
its enforcement; use [the maintenance guide](../../../rules_godot/docs/internal/api-reference.md)
for API inventory and metadata details, and the
[API documentation recipe](../../../docs/internal/verification-recipes.md#api-documentation)
for its checks.

## Organize and cover the complete surface

- Give public consumers clear, task-oriented entrypoints. Keep core project
  APIs in `godot:defs.bzl`; use dedicated extension, platform, engine,
  toolchain, repository and provider modules for those tasks. Keep platform
  dependency boundaries rather than forcing every API into one facade.
- Assign every `rules_godot/godot/**/*.bzl` module a role in
  `rules_godot/docs/public/api/modules.bzl`: public entrypoint,
  generated-repository implementation, or private implementation support. A
  public name does not become private merely because it is absent from the
  facade.
- Give each symbol exactly one public load path. Identify
  symbols by the defining file and name that Bazel reports and by API kind, so a
  renamed export cannot introduce a second public entrypoint for the same API.
  Re-export private implementations only through their intended entrypoint.
- Keep implementation modules under `private/` and restrict their actual
  Starlark load visibility. Directory names and BUILD source visibility alone
  do not enforce Starlark load visibility.
- Helpers loaded by generated repositories are implementation details, not
  consumer APIs. Classify them in `CROSS_REPOSITORY_MODULES`; exclude them
  from BCR metadata. Keep useful
  implementation explanations in source comments and docstrings. Never export
  them through public consumer entrypoints, even under a different name.
- Generated repositories can have caller-chosen names. Their implementation
  modules therefore need explicit public load visibility for cross-repository
  loads, despite being outside the supported public API. Preserve and check
  this technical access when changing the documentation inventory.
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
| Rule, aspect, symbolic macro | `doc` and each public `attr.*(doc = ...)` | Inputs, accepted providers, outputs/providers, execution or configuration behavior, constraints |
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

Explain `DefaultInfo`, custom providers, output groups, generated filenames and
runtime/runfiles behavior when consumers use them. Toolchains must distinguish
execution platform from target platform; packaging APIs must state relevant
SDK, signing and native-linking requirements. Describe actual error conditions.
Document deprecations with their replacement and migration implications.

Keep guides for setup, composition, architecture and troubleshooting. Link from
the reference instead of duplicating long explanations. Use plain prose and
small tables/examples; use diagrams only for relationships that need them.

## Extract and enforce

1. Update definitions and their documentation together. Classify new modules
   in `rules_godot/docs/public/api/modules.bzl`; workspace discovery must detect
   unlisted files independently of Bazel's declared inputs. Choose the primary
   owner of each new public symbol and update guides/examples to use that load
   path.
2. Extract unfiltered export inventories with Bazel's built-in
   `starlark_doc_extract`, using declared `bzl_library` dependencies. Check
   documentation and ownership against every public export before selecting
   the primary symbols of the registry's metadata. That selection must never hide new APIs.
   Do not replace Bazel evaluation with regexes or a Python Starlark emulator.
3. Publish each public contract at its sole entrypoint. Do not publish
   generated-repository implementation modules. Reject duplicate owners,
   additional public load paths, unowned exports, implementation helpers leaked
   through public entrypoints and selected symbols missing from extraction.
4. Follow the [API documentation recipe](../../../docs/internal/verification-recipes.md#api-documentation)
   for checking, and the [verification policy](../../../docs/internal/verification.md)
   for completion evidence.
5. Keep the documentation check enforcing complete source/export inventory,
   structured descriptions and unique primary ownership.
   Buildifier supplements these gates. Cover meaningful rejection cases,
   including second public exports, unrestricted private support modules and
   generated-repository modules losing external load access.
   Unsupported new API kinds must fail until extraction and checking are extended.
6. For a BCR documentation archive, use only `//public/api:bcr_docs` of the documentation
   module `rules_godot/docs`, the curated
   evaluated metadata for public primary contracts. Never archive all extractor
   outputs: those also contain unfiltered inventories and test fixtures. Archive
   publication is a separate release integration.

Nonempty descriptions and links are machine-checkable.
Accurate behavior, useful examples, compatibility implications and explanatory
quality require source review.
