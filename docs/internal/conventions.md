# Conventions: inventory, documentation and enforcement

**Research baseline:** 2026-11-01, repository `f5c6e66`, Bazel 9.3.0,
`buildifier_prebuilt` 10.1.0 and `aspect_rules_lint` 2.9.0.

This is an initial inventory and design comparison. Existing rules retain their current
owners. Accepted clarifications are recorded in owning guidance; the research proposals
below do not themselves introduce new rules, IDs, exceptions or lint gates.
At that research baseline, implementation and test-project migration still needed a
subsequent reviewed scope.

**Current enforcement:** The [convention catalogue](../../rules_godot/docs/public/conventions.md) owns the
automated policies, coverage and severity. The
[convention checker](../../tools/conventions/check.py) implements them. The comparison below
retains its research baseline; consult the catalogue for current enforcement.

For the naming subset, Buildifier remains responsible for formatting and its known label
rewrites. Buildozer's JSON interface exposes parsed calls without a new Go toolchain or
buildtools fork. Bazel loading identifies which calls actually produce targets and evaluates
the names of Bazel's built-in rules, so arbitrary helpers are not classified by a guessed function-name list.
The checker uses only Python's standard library for coordination and a token scan of the
parser's formatted call to recognize literal name arguments. It does not evaluate Starlark
with Python. Direct buildtools AST integration remains an option if broader
source checks justify the extra toolchain. Semgrep generic patterns and rules_lint alone
do not supply the missing Starlark or ownership semantics.

## Rule framework

Each registered rule is an independent object with `info: RuleInfo` and
`evaluate(context) -> Iterable[Finding]`. Its own module owns its ID, title, documentation
link, applicability, predicates, artifact qualifications, incomplete-coverage findings and records of reviewed sites.
Tests live beside the rule. No rule's implementation is placed in the CLI or tool adapters.

The [framework](../../tools/conventions/framework.py) validates unique IDs, invokes rules
against one context and attaches their metadata to findings. It sorts diagnostics for
stable output. A rule reports each finding once; a repeated finding is a rule defect and
aborts the run rather than being merged. `Finding.status` distinguishes `violation` from `not_checked`
for every rule. The [registry](../../tools/conventions/registry.py)
selects enabled rules, and the [CLI](../../tools/conventions/check.py) formats results and
chooses the exit status. Registration is explicit; no dynamic plugin discovery is required.

The [context](../../tools/conventions/context.py) exposes standard, read-only evidence tools:

| Access | Evidence |
|---|---|
| `context.workspace.files` | Git-owned, non-ignored files present in the working tree; `file_set` for membership |
| `context.workspace.documents` | Markdown under `docs/` and every README, excluding AGENTS.md |
| `context.workspace.text(path)` | A file's text, read once per run |
| `context.workspace.strings(path)` | String literals of a BUILD, MODULE.bazel or `.bzl` file, without comments |
| `context.workspace.owner(path)` | The nearest module directory of any file |
| `context.workspace.modules` | BUILD files grouped under their nearest module, with `packages` |
| `context.workspace.has_build(directory)` | Whether a BUILD file makes the directory a package |
| `context.workspace.godot_configurations` | Every `project.godot` file |
| `context.workspace.typed_directories(kind)` | The project or add-on directories of a typed root (`projects`, `addons`) of every consumer module, measured from its module root, with their files; `typed_directory(path)` resolves one path |
| `context.starlark.calls(module)` | Parsed source calls, attributes, locations and literal names |
| `context.starlark.module_name(module)` | The name a module declares in its MODULE.bazel |
| `context.bazel.rules(module)` | Loaded target identities, string/boolean attributes including defaults, and generator location; `Target.authored_inputs()` lists the labels a declaration chose |
| `context.bazel.inspect(module, labels)` | Cached rule, authored-file and generated-file facts for explicit labels, including local cross-module inputs |
| `context.declarations(module)` | Source calls joined to their evaluated targets, retaining macro fan-out |
| `context.is_local(label)` | Whether a label names a package of one of the workspace's modules |
| `context.sources(module, labels)` | Workspace path of each local label's defining target or source file |

Tools load evidence lazily, cache it per tool/context instance and return immutable records
and read-only attribute maps. The first `context.declarations` call loads the calls and
rules of every module concurrently, since each module is a separate Bazel workspace. The package-name rule only needs the workspace inventory.
The target-name and explicit-name rules share their declaration data, and the
documentation-label rule resolves labels against the same per-module query, so no query
runs twice. Missing/ambiguous source evidence and failed tools raise
`EvidenceError` and abort the audit; they are not converted into an empty
successful result.

To add a rule, create its module and adjacent regression tests, register its object, and
declare those sources in the existing Bazel package. A rule consumes available tools and
returns findings; it does not require a branch in the checker or a new report field. Add a tool
capability only when a rule needs a new kind of evidence, keeping retrieval independent
of the policy which consumes it. Tool protocols allow rule tests to use deterministic facts
without launching subprocesses; context tests exercise real parsing and evidence joins.

This small internal framework meets the need for independent rule evaluation and
shared evidence. [Pluggy](https://pluggy.readthedocs.io/en/stable/) provides hook specification,
registration and result collection, but the domain context and evidence adapters would
still be ours. An external plugin lifecycle is not needed. `rules_lint` remains
an integration option for a linter executable rather than the owner of rule predicates.

The [predicate draft](conventions-rules-draft.md) separates naming, placement,
production/test isolation and the agreed add-on/ordinary-project layouts into individual
review items. Its temporary keys are not stable
rule IDs; no proposed predicate overrides the current guidance.

## Existing sources and enforcement

[AGENTS.md](../../AGENTS.md) and area instructions provide orientation, work recipes and
review-only guidance. [Project layout](../../rules_godot/docs/public/project-layout.md) owns package, target and
test ownership; the [convention catalogue](../../rules_godot/docs/public/conventions.md) owns automated rules
and their coverage limits.

The existing enforcement has several owners:

- [Formatting](../../tools/format/BUILD.bazel) uses `rules_lint`'s `format_multirun`, Ruff
  and Buildifier, and only formats. [Buildifier configuration](../../.buildifier.json)
  selects the lint warnings the language checks report, documentation warnings included.
- [Language checks](../../tools/lint/lint.py) run every linter: pinned Ruff and ty, Buildifier's lint,
  jactionlint for the workflows and `hk validate`.
- The [convention checker](../../tools/conventions/check.py) runs the
  [catalogued rules](../../rules_godot/docs/public/conventions.md): naming, public-doc fixture references,
  example API references and documentation command labels resolved in their owning
  Bazel modules. It is not a full layout-policy checker.
- [API documentation checks](api-reference.md) use evaluated Bazel/Stardoc metadata and
  source inspection for inventories, ownership and descriptions.
- Bazel analysis, project/resource rules, sidecar checks and existing behavior/artifact
  tests already enforce parts of dependency, resource and runtime correctness.
- The [verification guideline](verification.md) owns when and where these checks run;
  [mise tasks](../../mise.toml), [hk's hooks](../../hk.pkl), the [lanes' work](../../tools/ci/work.py) and [CI](../../.github/workflows/ci.yml) implement that policy.

A passing existing check does not imply that all layout or naming conventions are enforced.

## Inventory to refine into atomic rules

This inventory records convention areas and candidate evidence, not additional requirements.
Some predicates have rules in the public catalogue; use that catalogue for their IDs
and automated coverage. Further predicates need explicit applicability and enforcement limits.

| Existing convention area | Current owner | Candidate evidence/check | Limit requiring care |
|---|---|---|---|
| English code/UI/documentation | Root working conventions | Review; optional spelling assistance | Names, localization and non-ASCII test inputs cannot be classified by a language heuristic alone. |
| `lower_snake_case` package segments and authored target names | Convention catalogue and layout guide | Filesystem inventory and Starlark syntax tree | Source filenames, generated targets, external APIs and intentional artifact/path fixtures differ. |
| Package-named clear main targets | Layout guide | Declared primary responsibility plus syntax/evaluated target metadata | Do not infer one main target from declaration order or require an aggregate in every package. |
| Short labels and explicit BUILD `name` arguments | Convention catalogue and layout guide | Existing Buildifier rewrites plus syntax checks where coverage is missing | Documentation strings, source labels and generated calls need their own scope. |
| Resource/project/delivery target placement | Layout guide | File/configuration ownership and declared operation scope | A local check can use root configuration; context does not determine physical placement. |
| Cohesive package boundaries and narrow visibility | Layout guide | Visibility metadata; dependency evidence for review | Cohesion, useful reuse and descriptive names need judgment; no fixed package count. |
| Acyclic target dependencies | Layout guide | Bazel analysis | Package dependencies may legitimately run both ways. Do not add a package-cycle prohibition. |
| Production independent of tests/resources/frameworks | Layout guide: test ownership | Configured dependency/resource closures and Bazel's `testonly` analysis | Bazel catches declared `testonly` edges; unmarked test resources need additional ownership evidence. |
| Implementation-owned native unit tests | Layout guide: test ownership | Dependency closure excluding consuming Godot projects | Test categories cannot be derived from file extension or extension use. |
| Unit versus real-operating-system integration suites | Layout guide: test ownership | Review category; then check declared location and execution tags | Classify behavior first. Do not turn the tag set into a universal operating-system policy. |
| Public rules and focused examples | Example guidance | Syntax/visibility checks for public entrypoints; review focus | Existing text checks are partial. No new consumer-probe or coverage-matrix examples. |
| Project configuration, application content and tests | Layout guide | Project-aware filesystem/resource inventory | Add-on test roots have needed unit/integration packages; omit empty symmetry directories. |
| Scene/component ownership and descriptive names | Layout guide | Reference/ownership evidence for review | Directory names cannot establish scene responsibility or naming quality. |
| Paired authored sidecars and stable resource identity | Resource APIs and layout guide | Existing analysis checks, sidecar targets and focused regression tests | Distinguish missing, undeclared and changed sidecars; preserve import options and UIDs. |
| Deliberate library outputs, symbols and resource paths | Layout guide | Evaluated extension metadata and artifact/behavior tests | Renaming a target or source directory can affect outputs. A label rename is not automatically a safe fix. |
| Formatting and Starlark/Python documentation style | Root source guidance | Existing Buildifier, Ruff, ty and API checks | Aiming for readable lines and useful explanations is partly review-only. |
| Public API ownership and private implementation boundaries | API maintenance guidance | Existing API inventories, visibility and reference checks | Reuse established checks rather than restating their contracts in a new linter. |
| Public documentation audience and runnable examples | Documentation guidance | Existing module-aware label checks; review descriptions | Resolving a label does not prove the documented workflow or support claim. |
| Generated documents kept in templates | Root template guidance | Syntax/target-input inspection plus review | Optional repeated blocks are a legitimate special case. |
| Export behavior derived from Godot facts/profiles | Root exporter guidance | Probe/profile and artifact tests; source-backed review | This is not provable from a filename or regular expression. |
| Justified exceptions and suppressions | Root working/check conventions | Structured cross-references and review of reasons/removal conditions | Preserve current owner-local exception policy; no blanket test-tree waiver. |
| Meaningful tests and appropriate validation | [Verification guideline](verification.md) | Existing test execution and reviewer assessment | Check counts, document counts and mirrored implementation tests are not quality evidence. |

For every inventory entry, distinguish a fully checked predicate, a checked subset and a
review obligation. Existing behavior preservation or incremental reuse guarantees may need
execution tests even when related structural rules are lintable.

## Existing tool options

### Buildifier, buildtools and Buildozer

[Buildifier 10.1.0](https://github.com/bazel-contrib/buildtools/blob/v10.1.0/buildifier/README.md)
already supplies formatting and named lint warnings. Its
[label rewrite](https://github.com/bazel-contrib/buildtools/blob/v10.1.0/build/rewrite.go)
removes redundant package/target suffixes in recognized label attributes. First measure
that existing coverage rather than implementing a second short-label normalizer.

The stock configuration selects warning categories. Repository-specific semantic rules
are not supplied as rule files through that configuration; the
[warning registries](https://github.com/bazel-contrib/buildtools/blob/v10.1.0/warn/warn.go)
are implemented in Go. The
[buildtools parser](https://github.com/bazel-contrib/buildtools/blob/v10.1.0/build/lex.go)
provides BUILD/module/Starlark syntax trees and is a candidate for custom source checks.
That would still require project-owned checking logic and a packaging/dependency decision.

[Buildozer](https://github.com/bazel-contrib/buildtools/blob/v10.1.0/buildozer/README.md)
can inspect and rewrite BUILD syntax. It does not evaluate macros; its documentation
explicitly distinguishes source-level operations from Bazel queries. Consider it for safe
mechanical edits, not as proof of configured dependencies or an automatic renaming
of evaluated targets.

### Aspect rules_lint

The repository already depends on `aspect_rules_lint` 2.9.0. Its
[custom-linter guide](https://github.com/aspect-build/rules_lint/blob/v2.9.0/lint/README.md)
explains how to adapt an executable linter through actions, aspects and report outputs.
It is a suitable integration candidate, not an implementation of our convention semantics.

Its [runner documentation](https://github.com/aspect-build/rules_lint/blob/v2.9.0/docs/linting.md)
describes Aspect CLI and vanilla-Bazel integration. Using this library does not by itself
require adopting Aspect CLI or hosted workflows. Compare its value against the existing
mise/hk commands; whole-repository discovery may remain a workspace-level command.

### Bazel graph and project evidence

Use [query](https://bazel.build/query/guide) for evaluated targets and structural dependency
questions. Use [cquery](https://bazel.build/query/cquery) when `select()` and configuration
matter: ordinary query includes possible branches, while cquery reflects analysis for the
chosen configuration. Aspects/provider metadata may supply Godot resource ownership.
Runtime behavior and invalidation still require the appropriate existing tests.

A source parser, graph checker and execution test answer different questions. They may
share rule IDs and reporting without pretending that one generic matcher proves all three.

### Generic rule engines

Semgrep is worth comparing if a small source-pattern proof is useful. Its current
[supported-language list](https://docs.semgrep.dev/supported-languages) does not list
Starlark. [Generic matching](https://docs.semgrep.dev/writing-rules/generic-pattern-matching)
can work without a language parser, but that does not establish faithful BUILD/macro
semantics. Do not choose it or use Python parsing as a Starlark substitute without a
representative experiment. No Semgrep dependency is selected or installed here.

### Provisional direction

Keep existing language/API tools; investigate buildtools for custom syntax checks and
Bazel for graph facts. Evaluate rules_lint as integration/reporting infrastructure. Start
with the thinnest useful additions to the existing commands rather than selecting a new
all-purpose framework before knowing the rule predicates.

Before selection, compare correct handling of macros/generated targets, `select()`, source
locations, module ownership, diagnostics and doc links, exceptions, safe fixes, local/CI
runtime, dependencies and ease of reuse outside this repository. A prototype must include
both a genuine violation and a valid case that a naive heuristic would reject.

## Catalogue and documentation design candidates

The public Project Layout should become an orientation guide: the concepts, the map of
examples, useful development paths and how consumers apply the conventions themselves.
Detailed rules need a single canonical owner, with rationale, valid/invalid examples,
applicability, exceptions and limits. Project Layout can reference stable IDs and links
without copying every rule's full text. Existing public instructions remain authoritative
until that restructuring is reviewed and implemented.

The user selected flat stable IDs on 2026-11-01: `RG001`, `RG002`, and so on. Categories
remain metadata; IDs do not encode section order or a mutable filesystem path. The first
allocations are in the current catalogue; the remaining N/P/I/L references are temporary
review keys.
Retired IDs stay retired, and changed/split rules need explicit successor links.

Compare these layouts before committing to one:

| Candidate | Benefit | Tradeoff |
|---|---|---|
| Public rule documents plus implementation/tests and a small shared index | Fits current public/internal separation; supports shared checker backends | Bidirectional documentation/check links must be validated. |
| Rule-owned directories containing prose, metadata and check tests | Strong physical adjacency | Needs a clear derivation of the public documentation and avoids duplicating shared checker logic. |
| Machine-readable catalogue generating detailed docs | One structured catalogue and mechanical cross-links | Long rationale/examples can become awkward; avoid turning all prose into schema fields. |

The first was the initial suggested fit. The user explicitly deferred the storage decision
on 2026-11-01. All three structures remain comparison candidates; no directory/API contract
or physical colocation choice has been adopted.

Keep policy approval, checker coverage and rollout severity as separate fields. Suggested
minimum metadata: stable ID, title, authoritative documentation, rationale, applicability,
checker backend/entrypoint, tests, exact automated subset, review-only remainder, current
severity, fix safety and scoped exception references. An accepted rule can be manual;
a partial checker must describe what it actually checks. Temporary exceptions continue to
live beside their owning rule in AGENTS.md with reason/removal condition until a replacement
policy is explicitly agreed.

A future consistency check could verify unique IDs, valid documentation/check references,
known severities and no falsely advertised automation; diagnostics should include the ID,
location, explanation and canonical doc link. Documentation generation should consume the
same metadata used for diagnostics. Avoid parallel handwritten lists of enabled checks.

## Applying conventions to regression projects

Apply applicable conventions to the regression module `tests/` as well as to examples. Example-specific layout rules need explicit applicability; a regression
fixture is not automatically an example add-on. Neither ignore the whole test tree nor
rewrite intentionally broken inputs merely to make lint green.

Useful first audit cases:

- [shared math resources](../../rules_godot/godot/private/tests/pack_membership/fixtures/project_with_pack_variants/BUILD.bazel) have a single
  resource target named `math`: assess whether the main-entry convention should apply.
- [C ABI fixture](../../rules_godot/godot/extension/tests/fixtures/c_abi/BUILD.bazel) names its extension
  `hello`, which determines its library outputs: identify the tested identity before any fix.
- [dSYM fixtures](../../rules_godot/godot/platforms/private/tests/desktop_package/fixtures/macos_apps_with_dsyms/BUILD.bazel) deliberately use nested output
  target names; the [feature-selected libraries fixture](../../godot/extension/tests/fixtures/feature_selected_libraries/BUILD.bazel)
  includes shared library filename targets. Classify these precise cases rather than exempting every
  fixture target or banning every slash/dot in test data.

An intentionally invalid fixture for a convention should assert the expected rule ID and
location. A fixture invalid for a different behavior needs a narrow, justified treatment.
Unexpected findings should remain visible and lead to a rule clarification, code fix or
explicit scoped exception. Report-only discovery can precede blocking enforcement; do not
silently weaken a rule, introduce global suppression or force a sweeping migration.
