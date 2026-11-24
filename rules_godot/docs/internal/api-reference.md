# Maintaining the Bazel API documentation

The ruleset's API documentation is its docstrings. The release archive's documentation
metadata carries them to the [Bazel Central Registry](https://registry.bazel.build/modules/autoload_rules_godot), which renders them; the
repository keeps no generated reference of its own. Each symbol has one public load path.
Platform setup, tutorials and architecture remain in the guides.

## The documentation module

The extraction, the registry's metadata and their checks live in a Bazel module of their own,
[`rules_godot/docs/`](../MODULE.bazel), beside `tests/` and `examples/`.
It depends on the ruleset through a `local_path_override`, extracts the ruleset's Starlark
modules and holds every dependency and override that only the documentation needs: Stardoc's
output schema, Protobuf and the [visibility patches](#third-party-documentation-dependencies).
The ruleset's published `MODULE.bazel` thereby carries none of them. Its `//public/api`
package holds the inventory and the extraction, `//tools/docs` the checks and the contract
checker. Commands below run in `rules_godot/docs/` unless they name another directory.

## Public entrypoints and implementation modules

[`modules.bzl`](../public/api/modules.bzl) assigns every `godot/**/*.bzl` module a role:

| Role | Purpose | Registry documentation |
| --- | --- | --- |
| `PUBLIC_APIS` | Consumer entrypoints with their exact public symbols | Full contracts for the public symbols |
| `CROSS_REPOSITORY_MODULES` | Modules other repositories load without them being supported API: implementation helpers of generated repositories and the test rules of the tests module; external load access is required | None |
| `SUPPORT_MODULES` | Private implementation files without a standalone load contract | None |

Use `godot:defs.bzl` for projects, resources, exports, runs and tests. Use the
dedicated extension, platform, engine, toolchain, repository and provider
entrypoints for those tasks. Application packaging and optional signing use the symbolic
`godot:app.bzl` entrypoint; engine acquisition keeps dedicated modules. The public providers,
`GodotPackInfo` and `GodotDesktopAppInfo`, live in `godot:providers.bzl` and name the rules
that produce them; the providers between the ruleset's own rules live in
`godot/private:providers.bzl`.

Core rule implementations live in `godot/private/`; the shared desktop
implementation lives in `godot/platforms/private/`. Their explicit Starlark
load visibility permits the public entrypoints to load them and prevents
direct consumer loads. Implementation re-exports expose each symbol through
its sole public entrypoint.

The binding and source-generation helpers are implementation details. Generated
repositories can have caller-chosen names, so their source modules explicitly
retain public load visibility. This technical requirement does not make them
consumer entrypoints: they have no BCR metadata.
Keep implementation notes in source comments and docstrings.

Consumers configure `godot_cpp_bindings` in `MODULE.bazel`, then pass its
generated C++ library as `deps = ["@godot_cpp//:godot_cpp"]` to
`godot_cc_extension`. These are the public contracts documented in `godot_cpp_bindings`'
docstring and the [C++ integration guide](../public/gdextension.md#c-bindings).

Each public symbol identity (API kind plus its defining file and name) has
exactly one public owner. A second public export fails CI even when it uses a
different name. Breaking changes are fine ([AGENTS.md](../../../AGENTS.md)), so API moves
update every repository consumer directly without retaining previous load paths.

## Outputs and generated targets

Document output access at the rule or macro that produces it. Keep four distinct contracts:

| Interface | Purpose | Documentation required |
| --- | --- | --- |
| `DefaultInfo` | Default requested files and, for executable targets, run behavior | Artifact kind, cardinality, selected variant, launcher/runfiles semantics |
| `OutputGroupInfo` | Explicitly requested output subsets such as archives or symbols | Exact group keys, contents, operating-system availability and relevant prerequisites |
| Public companion target | A distinct operation or analysis/configuration boundary | Generated name pattern, justification beyond file selection, files/providers, visibility, testonly and configuration behavior |
| Semantic provider | Structured input to consuming rules | Fields, types, producer/consumer relationships and selected-result meaning |

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

Review the complete inventory in `modules.bzl`: public symbols, configuration targets,
generated-repository contracts and the private expansions reached by public macros. Classify
independently named repository datasets and toolchains separately from companion targets of a
main target. Neither an output group per provider field nor a synthetic main target for an entire
repository is required. Check actual visibility as well as documented support.

Additional macro target names follow [RG002](../public/conventions.md#rg002): `<name>.<role>`.
The convention, including slash-suffixed rules_android basenames, is owned there. A dotted name does
not grant public visibility, and output-group keys and artifact filenames do not inherit
the target separator. Document only the supported public companion targets as consumer interfaces.

Each owning source docstring contains the Markdown section `### Default outputs` and, where
the API has them, `### Output groups` and `### Generated targets`; a section without entries is
omitted. Private rules, macros and repository rules keep these sections too: they document
the ruleset's internal use and are ready when a symbol becomes public, although only public
ones are checked against Bazel. Each section is a list, which stays readable on narrow pages
such as the BCR's, in the form the [output-contract parser](../tools/docs/output_contracts.py)
defines:

```markdown
### Default outputs
- executable (one): build the application; bazel run installs and launches it
  - availability: ios

### Output groups
- `bundle`: Selected unpacked application bundle
  - prerequisites: matching desktop runtime component

### Generated targets
- `{name}.debug_symbols` (alias): Analyze the symbol producer without signer identities
  - purpose: analysis_boundary
  - visibility: caller
```

An entry's first line names a default output's kind and cardinality, a group's key or a
companion target's name pattern and kind, followed by its behavior, contents or concrete
reason. Indented `field: value` lines give the other fields where they differ from their
defaults: availability `always`, prerequisites `none`, purpose `operation`, visibility
`public` and testonly `false`. The parser reads evaluated docstrings from Bazel's
`starlark_doc_extract`; the registry renders the same metadata together with each symbol's
signature and attributes. Docstrings do not list the providers a target returns: a public provider names
its producers in its own documentation. Conditional availability must have representative
configured evidence. Configuration-only targets have explicit metadata roles; they must not
invent files.

The [case registry](../../godot/tests/api_contracts/cases.bzl) supplies Bazel-evaluated fixture labels
and configurations, not another copy of the public prose. It also names the behavior tests
that show why an API's public companion targets are separate; the checker requires them to
resolve. A case or behavior test names its `module` when its fixture lives in a consumer
module, such as the regression module `tests`; the checker evaluates it there, and
resolves a consumer module's behavior tests in the desktop lane, whose cases evaluate that module
anyway. The checker compares actual default files, executability, groups and public companion
targets against the source in both directions. Bazel's loading facts
establish target kinds, visibility, testonly and test behavior. Generated repositories have
independent entrypoint checks instead of a fictitious repository-wide main target. Only
interfaces the ruleset promises are compared: underscore-prefixed groups and, for roots that forward an upstream target, its groups are not. New public APIs or
unsupported API kinds cannot silently escape required coverage.

`aspect work docs` checks source schema, inventory, registry coverage, the
ruleset module's behavior tests and the cases of the docs lane. `bazel run //tools/docs:contracts -- --lane <lane>`
checks the cases of each profile lane, `desktop`, `source-engine`, `android` or `ios`, as the
lane's work `contracts:<lane>`. It builds the extraction in the documentation module and
evaluates the fixtures in the ruleset's module or in the consumer module a case names; the
verification selector runs
them in their lane when rules, contract sources, fixtures or the checker change.
Missing evidence of a selected lane remains pending; a host documentation pass cannot replace it.

Update source docs, inventories and consumers together when a public interface changes. Review actual behavior and the necessity of each companion target
separately: a resolvable test and a structurally valid justification do not establish that
another target is useful.
Public guides link to the registry's documentation and show short build/run/group/companion examples.

## Writing standard

The repository skill
[bazel-api-docs](../../../.agents/skills/bazel-api-docs/SKILL.md) defines the writing
and review standard. Its [upstream references](../../../.agents/skills/bazel-api-docs/references/upstream.md)
explain which practices come from established rule sets and which checks are
specific to this repository.

## Documentation contracts

The [verification policy](../../../docs/internal/verification.md) owns execution timing;
[verification lanes](../../../docs/internal/verification-platforms.md) own the lanes.
The documentation checker covers complete module and public target inventories, evaluated
API descriptions, primary ownership and internal boundaries. New modules must be explicitly classified in `modules.bzl`, including
private support files.

Extraction for coverage is unfiltered: every export of a public entrypoint
is inspected. Selecting the primary symbols of the registry's metadata cannot
hide a new export. Every public export must
belong to that entrypoint's exact symbol set. Duplicate ownership, additional
public load paths, unowned exports, missing selections and internal helpers
leaked through public entrypoints fail, even if selected explicitly for
documentation. Private support modules must declare restricted load visibility;
cross-repository modules must retain public load visibility.
All source modules remain classified even when excluded from the registry's metadata.

The coverage tests inspect Bazel's `starlark_doc_extract` metadata using
Stardoc's Protobuf schema. They reject empty module/API descriptions,
undocumented public attributes, function parameters, provider fields and
extension tags, and exports omitted by extraction. Source checks
also require documentation on short functions that Buildifier exempts.
Semantic correctness, useful examples and accurate support claims need review;
nonempty text alone cannot establish those qualities.

The workspace-level discovery lives in the Python command
because a Bazel sandbox only sees declared inputs and cannot discover an
undeclared new source file. `bazel run //tools/docs:check` runs it; it runs Bazel again
in the documentation and ruleset modules, so pass `-- --bazel /path/to/bazelisk` or set `BAZEL` when Bazel is
not on PATH.

## Metadata for the BCR documentation archive

`bazel build //public/api:bcr_docs` selects only the `starlark_doc_extract` `.binaryproto` files
for the public primary symbols. CI checks that they contain every configured
public symbol exactly once, with no implementation helpers or duplicate symbols.
The release script (`.github/workflows/release_prep.sh`) packs exactly these files into
`rules_godot-<tag>.docs.tar.gz`, which `docs_url` in `.bcr/rules_godot/source.template.json` names and
the registry renders; see [Releasing](../../../docs/internal/releasing.md).

Do not collect every `starlark_doc_extract` output into an archive: unfiltered
inventories and intentionally invalid test fixtures have different purposes.
The curated BCR metadata contains public contracts only.

## Third-party documentation dependencies

`rules_android` 0.8.0 exports its API `.bzl` files, but its transitive
`//rules:bzl` documentation library has restricted visibility. The documentation module
applies `tools/docs/rules_android_doc_visibility.patch` to expose that single
library for `starlark_doc_extract`. `rules_android_ndk` 0.1.5 exports no files; the
documentation module applies `tools/docs/rules_android_ndk_doc_visibility.patch` to export
`rules.bzl`, which `godot_android_toolchains` loads. Both change BUILD visibility only.
Rulesets that build on rules_android publish no registry documentation or document no
Android rules; `godot_app` loads rules_android, so its extraction needs the patches.
Remove each patch once its upstream file is publicly accessible; do not disable
Bazel's visibility checking.
