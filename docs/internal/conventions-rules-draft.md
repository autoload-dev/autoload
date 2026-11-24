# Rule predicates: naming, placement and test isolation

**Baseline:** 2026-11-01, repository `f5c6e66`, Bazel 9.3.0 and Buildifier 10.1.0.
**Authority:** This is a review draft derived from existing guidance. N1–N6, P1–P3,
I1–I5 and L1–L12 are working references, not allocated stable diagnostic IDs or newly enabled rules.
Existing AGENTS.md files and public guidance remain authoritative.

**Implemented subset:** N1, N2 and N3 correspond to
[RG001, RG002 and RG003](../../rules_godot/docs/public/conventions.md); the sections below name
the further subsets that RG007 to RG012 implement. That catalogue owns their current automated
predicates and limitations; the remaining references below remain review drafts.

The broader [inventory and tool comparison](conventions.md) covers other convention areas.
The layout section below explicitly captures the already selected add-on and ordinary-project
conventions; their omission from the first focused draft was a coverage gap.
This draft separates policy meaning, a possible automated predicate and the part requiring
review. It does not choose a rule registry format, primary-target marker or new framework.

## Shared terms and checking contract

- **Owned package:** a repository-maintained Bazel package, identified within its nearest
  module. Vendor/external ownership must be distinguished from source location.
- **Authored declaration:** a target-defining call supplied by maintainers. Calls can use
  computed names; targets expanded by macros are not all separate authored declarations.
- **Primary entry:** the useful entry point elected from the package's responsibility.
  The first declaration, only public target or largest dependency closure is not proof.
- **Production root:** a reusable or runnable product composition, including production-under-test
  inside a regression fixture. Living under `tests/` does not make its resources test-only.
- **Test-owned seed:** a suite, assertion helper, fixture data or test target exclusively owned by
  tests. Production code used by a test is not thereby test-owned.
- **Context:** the settings, classes, extension types, plugins and autoloads necessary for an
  operation. It can come from another package without transferring operation ownership.

Checkers must report module/configuration scope and distinguish violation, compliant,
not-applicable and insufficient-evidence/not-checked outcomes. Rule approval, check coverage
and rollout severity are independent. An unresolved ownership classification is not a pass.
Raw query results are structural evidence; configured resource/provider facts are needed
where target platform choices matter. Existing Bazel analysis remains the authority for target
cycles and Bazel's `testonly` edges.

No blanket fixture waiver follows from this draft. A fixed locator in a test is evidence of
migration impact, not by itself evidence that the spelling is the behavior under test.

## Naming predicates

### N1 — Package segments use lower snake case

**Meaning/scope:** Repository-owned package path segments follow the
[naming convention](../../rules_godot/docs/public/project-layout.md#package-and-target-names), across rules, tools,
examples and regression projects. Empty root packages have no segment to validate.

**Accepted predicate (2026-11-01):** Normal owned package segments match
`[a-z][a-z0-9]*(?:_[a-z0-9]+)*`: lowercase ASCII letter first, then lowercase letters/digits
with single underscores between words. Leading, trailing and repeated underscores are
excluded. N2 applies the same spelling to ordinary authored target names.

**Examples:** `native_c_addon` conforms; `native-c-addon` does not. An asset directory that
is not part of a Bazel package path is outside this predicate.

**Checking:** Filesystem/module inventory; no Starlark execution is needed. Review vendor
ownership and the existing special-case boundaries before making this blocking.

### N2 — Authored target names use lower snake case

**Meaning/scope:** Apply the same naming convention to authored targets, with the existing
source/artifact/external-identity qualifications. Source-file labels are not ordinary
rule names; generated target names do not establish the spelling of the authored call.

**Examples:** `counter_addon` conforms. An ordinary helper named `counter-addon` does not.
The generated `format.check` interface is not an authored declaration we should rename.

**Checking:** Parse target declarations and obtain evaluated names for computed declarations.
A source string containing a label or filename is not automatically a target declaration.
Native filename and nested-path cases require precise applicability evidence, not a whole
file/tree suppression. Renaming can change outputs and is not an automatic safe fix.

### N3 — Target declarations keep an explicit name

**Meaning/scope:** Maintainer-authored target declarations express `name` explicitly.
This does not require `name` on `load`, `package`, `exports_files` or arbitrary helpers.

**Examples:** `godot_resources(name = "main", ...)` and a target macro with `name = variant`
are explicit. A target-producing wrapper which infers its name does not satisfy RG003;
ordinary helpers which produce no evaluated rules are outside the automated check.

**Checking:** Syntax plus knowledge of target-producing calls. Unknown macros and name-bearing
`**kwargs` require source/context evidence; do not guess from capitalisation or a regex.
This checks declaration intent, not whether every expanded helper name is a literal.

### N4 — Elect a main entry only for a clear package responsibility

**Meaning/scope:** A clear useful primary entry is preferred. Equal sibling units or
scenario variants do not need an invented aggregate or default-target alias.

**Examples:** An add-on's reusable composition can be primary. The blue/red/data variants
of the pack-membership fixture (`godot/private/tests/pack_membership/fixtures/project_with_pack_variants`) need not be forced behind one new default target.

**Checking:** Review responsibility and actual consumers. Automated tools can surface
candidates and missing evidence; target counts and rule kind cannot settle this rule.
The representation of that reviewed decision in checker inputs remains open.

### N5 — An elected main entry matches the package basename

**Meaning/scope:** Once a non-root owned package has an elected main entry, its target name
matches the package's final segment. Secondary workflow names remain descriptive.

**Examples:** `//addons/sqlite:sqlite` has a matching main name; `check`, `edit` and `pack`
can remain secondary roles. The pack-membership project keeps its shared `math` resource beside the application sources.

**Checking:** Mechanical equality after N4 classification. Native symbols, file outputs,
logical paths and callers must be understood before any rename. A filename merely
hardcoded by a test is not an automatic permanent exemption. No extra alias is introduced
solely to abbreviate the label.

### N6 — Use canonical label spelling in actual references

**Meaning/scope:** Across packages, omit a redundant suffix for a matching main target;
within the owning package use ordinary relative labels. Declarations still follow N3.

**Examples:** Prefer `//addons/sqlite` to `//addons/sqlite:sqlite`; `:demo` is appropriate
inside the demo package. Text passed to an application is not necessarily a dependency.

**Checking:** Reuse Buildifier's existing label rewrites in recognized attributes. Inspect
unknown macro attributes before extending coverage. Documentation snippets and application
strings need separate semantic scope; do not globally replace label-looking text.

## Placement predicates

### P1 — Authored project workflows follow their composition owner

**Meaning/scope:** The normal authored project, editor and sidecar workflows live beside their
`project.godot`, as described in [target ownership](../../rules_godot/docs/public/project-layout.md#target-ownership-and-project-context).
Additional projects and editor views need a concrete development or test purpose.

**Examples:** SQLite's test-project entry and editor live at its test root. A private
`unit_project` generated by the GdUnit operation is not a misplaced authored project.

**Checking:** Relate authored calls, configuration ownership and project role. A cross-package
configuration label, shared default project file or generated helper is not enough to fail.
Operation scope and justified focused projects need review before path-based diagnostics.

### P2 — Local operations own their selected responsibility and required context

**Meaning/scope:** Runnable entries and packs may be local or project-wide according
to useful scope. They declare the configuration and resources needed for that operation.

**Examples:** Lichtpost's route/replay resources in `main/rules` are validated under the
root configuration through the production pack, which selects the production resource
closure; it requires no new package or local run/pack target for every resource group.

**Checking:** Compare declared scope to resource/configuration inputs. Syntax alone cannot
prove that autoloads/classes/extension types are sufficient, or that a global operation has
been placed usefully. Preserve behavior checks and review role; no root-only heuristic.

### P3 — Behavior test resources and test targets follow their test owner

**Meaning/scope:** Suites, assertion helpers, fixtures and behavior execution belong to
[their test responsibility](../../rules_godot/docs/public/project-layout.md#test-ownership), normally a dedicated test
package.

**Examples:** Example unit/integration packages own both suite resources and their test target.
A reusable consumer fixture mixing a product composition with its suites is a migration candidate.
A package whose sole responsibility is testing test adapter scenarios is not automatically an
incorrect layout just because it composes miniature projects.

**Checking:** Ownership/context audit followed by source/package checks for classified
roles. The exact physical-split obligation for reusable fixtures versus small contract-test
packages needs clarification. Do not silently accept every existing mixed BUILD file or
split every test directory mechanically. I1 remains mandatory in either arrangement.

## Production/test isolation predicates

### I1 — Production closures exclude test-owned targets and resources

**Implemented subset:** [RG012](../../rules_godot/docs/public/conventions.md#rg012) checks direct authored
workspace inputs of production-eligible declarations against test-scope locations.

**Meaning/scope:** For each identified production root, neither its target dependencies nor
its effective resource membership may consume test-owned seeds/frameworks. This includes
production-under-test inside regression fixtures, not just applications in `examples/`.

**Predicate candidate:** `closure(production_root) ∩ test_owned_seeds = empty`, with the
closure and membership evidence evaluated for the claimed configuration/module scope.

**Examples:** A production scene depends on its implementation resources, not a GdUnit suite.
Being in a scenario package of the regression module does not make the tested implementation a forbidden dependency.

**Checking:** Bazel's `testonly` checks cover marked edges; additional known ownership and
Godot resource facts cover unmarked resources. Do not infer test ownership from all
transitive dependencies of a test: that would incorrectly classify the code under test.
Missing role classification or configurations must remain visible as incomplete coverage.

### I2 — Mark exclusively test-owned resources as test-only

**Status:** Accepted by the user on 2026-11-01 and recorded in test-ownership guidance.
The obligation is established. Its operation-owned subset is implemented by
[RG007](../../rules_godot/docs/public/conventions.md#rg007): the targets generated by Godot checks and tests
must be effectively test-only. Classification and enforcement for separately declared
suites, assertion helpers and test data remain outside that automated subset.

**Meaning/scope:** Targets owning only suites, assertion helpers or test data must carry
an effective `testonly = True`, directly or through the package default. Test targets being
test-only is not sufficient protection for separately declared resource targets.

**Examples:** SQLite's unit package supplies a true default to suites and test target. The two
counter fixtures had true test targets but false suite-resource flags at the research baseline;
that contrast illustrates why marking only test targets is insufficient.

**Checking:** Read effective values rather than require a literal attribute on each target.
Do not mark a whole mixed fixture package true when its reusable implementation must remain
available to production-under-test. Unmarked exclusively test-owned resources are violations,
not automatic fixture exceptions. Baseline examples do not establish current flag values.

### I3 — Keep code under test reusable and production-eligible

**Meaning/scope:** A test consuming an implementation does not transfer ownership of that
implementation to tests. Helpers exclusively for assertions differ from shared runtime code.

**Examples:** The pack-membership fixture's `math` can remain a production resource consumed by both
packs and tests. Marking it test-only merely because a test of these resources uses it is incorrect.

**Checking:** Review ownership once; then preserve the classified role in graph checks.
An implementation intentionally exclusive to a negative fixture can have a different role;
file paths and reverse-dependency counts alone cannot determine it. This limits I2.

### I4 — Independent native unit tests do not need a consuming Godot project

**Meaning/scope:** Native implementation tests select their implementation/interface and
can execute without a demo/integration project or a GdUnit runtime. This is distinct from
deterministic Godot API tests, which legitimately load the extension through Godot.

**Examples:** Platform Paths' backend policy test selects the policy and interface; its
Godot API unit suite is not subject to the engine-independence predicate.

**Checking:** After category review, inspect relevant target/action/runtime inputs for
project/framework dependencies. A compiler toolchain dependency is not the same thing as
executing Godot. No language-extension or target-name heuristic establishes test category.

### I5 — Target dependencies stay acyclic; package edges may run both ways

**Meaning/scope:** Existing Bazel target-cycle restrictions apply. Project composition can
consume child suite resources while a child test target consumes the root configuration file.
These are distinct targets; package-level edges in both directions are not a violation.

**Checking:** Reuse Bazel analysis in the relevant configuration. An unconfigured query
can combine branches from different configurations; a new generic union-graph or package-
cycle rejection must not overrule valid configured target graphs. No duplicate cycle linter
is proposed. This rule must not force artificial shared-source packages.

## Project and add-on layout predicates

These conventions were already selected in the example/layout work. Their **meaning is
established** by the [example guidance](../../rules_godot/examples/AGENTS.md) and
[Project Layout](../../rules_godot/docs/public/project-layout.md); only decomposition, automated coverage and
fixture applicability are under review here. They are not new framework proposals.

Repository placement and project-internal structure have different scopes. For this
repository's example and regression projects and add-ons:

```text
{examples,tests}/
  addons/<addon_name>/             # reusable add-on implementation and entry
    demo/
      project.godot
      BUILD.bazel                 # project and project-wide workflows
      main/                       # application content
      tests/                      # exported-demo behavior checks
    tests/
      project.godot
      BUILD.bazel                 # test project and project-wide workflows
      unit/                       # only if deterministic API suites exist
      integration/                # only if real operating-system suites exist
  projects/<project_name>/
    project.godot
    BUILD.bazel
    main/
    tests/
```

An ordinary consumer project can live at its own workspace location:

```text
<project_root>/
  project.godot
  BUILD.bazel
  main/                           # application scenes, scripts and assets
  tests/                          # behavior suites, helpers and fixtures
```

These trees illustrate ownership, not required empty directories or one BUILD file per
shown directory. P1–P3 govern operation placement, N1–N6 target naming and I1–I5 dependency
boundaries. The add-on test root's `unit/` and `integration/` replace another nested `tests/`.

### L1 — Classify applications and add-ons through typed roots

**Implemented subset:** [RG009](../../rules_godot/docs/public/conventions.md#rg009) inventories both areas
and tells projects from add-ons by the projects/addons branch.

**Meaning/scope:** `{examples,tests}/{projects,addons}/<name>/` is the repository taxonomy.
Application cases own configuration and `main/`; all add-ons own separate `demo/` and
`tests/` projects. This repository-level structure does not constrain an unrelated consumer
workspace. Source language and extension use do not make a directory a project or an add-on.
Focused C++/provider fixture inputs stay with their owning test domain.

**Checking:** Shared inventory of project and add-on directories, BUILD files and authored Godot
configurations. No admission list selects individual add-ons or exempts a mobile module.

### L2 — Reusable add-on implementation stays independent of consumers

**Implemented subset:** [RG011](../../rules_godot/docs/public/conventions.md#rg011) checks the direct
authored implementation inputs against the demo, as Bazel resolves them; test inputs are
covered by [RG012](../../rules_godot/docs/public/conventions.md#rg012). Its catalogue entry owns coverage and limitations.

**Meaning/scope:** An add-on owns its reusable scripts/native code and composition. Its
implementation does not belong to its demo or tests, and does not depend on either.
Independent native unit tests stay with the implementation/backend.

**Examples:** SQLite's `database.cc` belongs to the add-on root. Platform Paths can share
an Apple backend across macOS/iOS and keep related Android languages in one integration.
A `native/` directory is useful grouping when warranted, not mandatory for every add-on.

**Checking:** Source ownership and dependencies; configured graph/resource evidence for
independence. Folder spelling alone cannot prove that implementation is reusable.

### L3 — Add-ons have separate demo and Godot test projects

**Implemented subset:** [RG010](../../rules_godot/docs/public/conventions.md#rg010) checks separate project
roots and BUILD ownership for every add-on under either typed add-on root.

**Meaning/scope:** `demo/` demonstrates normal add-on use; the add-on's `tests/` owns its
Godot test context. Each has its own root `project.godot` and composition/workflows.
Do not restore `integration_tests/tests/` nesting or an extra contract-only Godot project.

**Examples:** SQLite has `demo/` and `tests/`, despite having only deterministic unit suites.
A game can use production and test projects of one configuration; this rule does not require
separate configurations for every ordinary project or every test category.

**Checking:** Inspect every typed add-on automatically. C++/provider inputs used by focused tests
are not independent add-ons; classify them in their owning test domain instead of adding
empty projects or an add-on-specific exemption.

### L4 — Keep configuration at project root, application content under main

**Implemented subset:** [RG008](../../rules_godot/docs/public/conventions.md#rg008) checks the physical location
of declared application resource inputs. Its catalogue entry owns applicability and limits;
test-package placement and the remaining layout predicates stay separate.

**Meaning/scope:** An ordinary game/application or demo keeps its authored `project.godot`
at the project root. Its application scenes, scripts and exclusively owned assets live
under `main/`; behavior tests live under `tests/`. Reusable add-on implementation is not
copied into application ownership merely because the application consumes it.

**Examples:** Lichtpost's `main/game.tscn` is application content. A test-only add-on project
needs no empty `main/`; its suites are organized by L5. Project-root configuration/export
inputs are not misplaced application assets.

**Checking:** Project-aware source/resource ownership plus filesystem layout. Physical
locations and mounted `res://` paths are distinct facts: `prefix` and `resource_paths` select
logical paths explicitly. A fixture migration must review both, not perform a blind move.

### L5 — Categorize add-on Godot suites by behavior

**Meaning/scope:** Under the add-on test project's root, deterministic Godot API/contract
suites belong in `unit/`; real operating-system behavior suites and fixtures belong in
`integration/`. Each needed category owns its suite resources and executable in a BUILD
package. Loading an extension does not itself make a suite an integration test.

**Examples:** `PathContractTest` is a unit suite; `PlatformPathsTest` exercises real
operating-system behavior. SQLite needs `unit/` without an empty integration counterpart.
Preserve each test target's execution conditions/tags; no universal `external` tag is inferred
for all tests.

**Checking:** Review behavior/category, then check locations, ownership and declared inputs.
Names, languages and native dependencies cannot replace classification. P3 and N5 apply
once the category and its primary test target are established.

### L6 — Avoid empty symmetry and redundant single-scene nesting

**Meaning/scope:** Create only directories and packages with a useful responsibility. A
single-scene demo keeps its scene/script/assets directly in `demo/main/`; another directory
repeating the demo purpose is unnecessary. Keep descriptive filenames.

**Examples:** `demo/main/database_demo.tscn` conforms; a repeated
`demo/main/database_demo/database_demo.tscn` wrapper is redundant for that sole scene.
A project containing several independent scenes can justify separate component directories.

**Checking:** Filesystem candidates plus scene/ownership review. Do not reject every
single-child directory or every package with a small number of files.

### L7 — Keep a scene or component's exclusive files together

**Meaning/scope:** Keep a `.tscn`, its script and assets used exclusively by that scene or
component with their owner. Use descriptive scene/script filenames. Larger projects may
use independently meaningful scene/component directories.

**Examples:** A courier scene and its own script belong together; the sole demo scene can
use `main/` itself as that location. A generic filename is not automatically descriptive
merely because its directory has a useful name.

**Checking:** Reference/ownership evidence can identify likely separation or duplicate
ownership; exclusivity and naming quality require review. Do not require one package per
scene or assume that every script must have a scene.

### L8 — Give shared assets an explicit shared owner

**Meaning/scope:** Assets used by several scenes have a clearly named shared location and
resource owner. Consumers declare the appropriate dependency instead of copying shared
assets into each scene's private files.

**Examples:** Lichtpost's shared palette and UI resources have their own owners. A shared
helper can have a precise domain name; not every project needs the full `shared/palette/`
and `shared/ui/` example tree.

**Checking:** Source ownership, resource paths and consumer dependencies. Identical file
contents alone do not prove accidental duplication, and reuse frequency alone does not
settle the right owner.

### L9 — Compose components through small explicit interfaces

**Meaning/scope:** Extract meaningful UI/game components into their own scenes as useful.
Parent scenes compose and coordinate them through methods, signals and exported properties
rather than reaching through their internal node structure.

**Examples:** A HUD or dialog can expose its intended behavior through an interface.
Moving code into a separate scene while keeping deep parent-to-child node access does not
by itself meet the convention.

**Checking:** Primarily architectural review. Source/reference inspection can surface
candidates; a count of node paths or signals cannot prove component quality. Do not create
components solely to satisfy a directory or scene count.

### L10 — Separate reusable gameplay from level content

**Meaning/scope:** Reusable mechanics and components are independent of a particular level.
A level supplies its definition and specific assets, so another level can reuse the same
mechanics without copying/changing them just to substitute content.

**Examples:** Lichtpost's reusable run/mechanics consume level data. `levels/level_01/`
is a useful organization for its specific content, not a mandatory subdirectory in a
single-scene add-on demo. A Godot Resource is one suitable data representation, not a new
required API for every project.

**Checking:** Dependency/reference evidence and review; behavior tests where a concrete
coupling regression exists. File extensions cannot establish the mechanics/content boundary.

### L11 — Keep authored sidecars with their source and resource owner

**Meaning/scope:** Source `.uid` and asset `.import` files stay beside their sources and
are declared with them by the owning resource target. Layout changes preserve authored
UIDs and import options; logical path changes are deliberate.

**Examples:** A scene script and its UID move together. A sidecar introduced through a
later unrelated target does not repair the original resource's ownership.

**Checking:** Reuse existing resource-analysis and sidecar checks; compare identity/options
when migrating. Distinguish generated cache data, a missing sidecar and an authored but
undeclared sidecar. Do not implement another importer or infer paths from labels alone.

### L12 — Add BUILD boundaries for useful ownership, not directory symmetry

**Meaning/scope:** Introduce a package for coherent responsibility, independent dependencies,
reuse, visibility or test ownership. Related units can have separate resource targets in
one BUILD file; a grouping directory does not automatically need a package.

**Examples:** Several Lichtpost component directories share one BUILD while retaining
separate targets. Separate unit/integration ownership under L5 is a useful boundary;
artificial `tests/suites/` packages solely to avoid package-level cycles are not required.

**Checking:** Review ownership and dependency evidence. No fixed target/file/package count,
one-BUILD-per-directory rule or prohibition of bidirectional package edges follows. P3 and
I5 constrain test ownership and actual target dependencies without replacing this judgment.

## Accepted decisions and explicit deferral

On 2026-11-01 the user selected strict ordinary-name spelling under N1/N2 and mandatory
exclusive-test resource marking under I2. Stable IDs use a flat sequence: `RG001`, `RG002`,
and so on; categories are separate metadata. Final ID allocation to accepted catalogue
entries is pending, so N/P/I/L remain working references.

The user explicitly deferred how rule documentation, checker code and tests are physically
stored. No registry format or directory arrangement is selected by that decision.

## Decisions still needed

1. Define precise applicability evidence for authored/generated names, source labels and
   artifact contracts before blocking on N1/N2. The ordinary-name grammar is settled.
2. Decide how reviewed primary ownership becomes checker input for N4/N5, and how native
   identity conflicts are resolved without cosmetic aliases or unrequested rule APIs.
3. Clarify the physical test-package requirement for reusable consumer-like fixtures versus
   small adapter/analysis scenario packages under P3.
4. Plan I2 migration and precise fixture deviations. Mandatory test-only marking is settled;
   retain current owner-local exception policy until replaced deliberately.

Framework selection, catalogue storage and final ID allocation follow reviewed predicates
and representative experiments. The flat ID format is already selected.
Policy interpretation, actual coverage and migration status must remain separate.
