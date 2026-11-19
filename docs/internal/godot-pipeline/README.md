# Godot Pipeline Input, Output and Dependency Catalogue

**Date:** 2026-11-01. **Status:** Independently reviewed for the stated scope; no remaining correctness or
completeness findings at the documented class/operation boundary.
This is a durable, repository-wide reference for Godot processing and ruleset design.
It describes source-backed mechanisms and current ruleset boundaries independently of
individual specifications; it does not select a replacement public API.

The repository-wide [capability overview](../capability-overview.md) and
[capability matrix](../capabilities.md) define user outcomes and track their coverage.
Use this catalogue as dependency evidence when specifying those capabilities.
Review it when the underlying engine, plugin or toolchain semantics materially change.

## Scope and baseline

- Repository baseline: `506d045ec401effdcb93986dfa0ca2064dbfd78a`.
- Godot: 4.7.2-stable, commit `ed1daf0bf001b61586d9930840f2f1394092c079`.
  A cached official macOS executable reported `4.7.2.stable.official.ed1daf0bf`.
- Bazel: 9.3.0. GdUnit: `0127a55f4543dfc24746f6e5c7ba6f94105d51f2`.
- Application and toolchain boundaries: existing Linux/macOS/Android/iOS workflows,
  rules_android 0.8.0, rules_apple 5.3.1, existing engine, toolchain and engine profile
  declarations.
- Engine/source patches, modules and actual tool binaries are inputs. A stock version string
  does not establish identity with a source-built engine. The optional next-minor probe is not a
  second researched Godot baseline. [S01](evidence.md#s01)

Coverage is by relevant artifact/operation classes, not every possible filename or setting.
Arbitrary extension code can add dependencies and outputs. Those open boundaries are
catalogued explicitly; this is not a proof of universal plugin hermeticity or new support
for every upstream export option.

The catalogue contains **50 artifact classes, 21 operations and 25 explicit dependency edges**,
with source/conditionality evidence and an independent coverage review.

## Reading order

1. [Artifacts](artifacts.md): sources, generated intermediates, delivered products and state.
2. [Operations](operations.md): reads, writes, phase boundaries and current Bazel ownership.
3. [Dependencies](dependencies.md): edges, conditionality, reuse and invalidation.
4. [Evidence](evidence.md): pinned sources, focused probes, review and remaining questions.

Artifacts use stable `ART-*` IDs; operations use `OP-*` IDs. These are research identifiers,
not proposed Starlark symbols. Artifact classes can be both input and output across invocations.
A mutable file read before an operation and its updated version after it are distinct states,
so the class-level diagrams do not represent an action cycle.

## Evidence and edge notation

| Mark | Meaning |
|---|---|
| F | Established by inspected pinned upstream source |
| R | Established by current repository source; may be wrapper policy rather than engine necessity |
| E | Observed in a bounded experiment; only its stated case is established |
| I | Inference or modelling obligation derived from the facts, not a measured implementation result |
| U | Open or deliberately unbounded dependency/coverage question |
| D / C | Direct read / conditional read when the documented facility or phase is active |

Every operation also depends on its implementation/tool files, arguments, relevant configuration
and execution platform. Optional inputs are not universally required; an absent cache is a
valid cold state, and cache existence does not establish compatibility.

## Four different dependency graphs

- **Resource references:** paths, UIDs, dynamic loads, inheritance and resource relationships.
- **Configured targets/aspects:** Bazel labels, configurations, dependencies and action owners.
- **Actions:** actual declared input Files, tools, arguments and output artifacts.
- **Execution validity:** all influences on a test/run result, including relevant external state.

A scanner can select resource content without narrowing an already declared action input set.
PCK-byte identity alone does not establish unchanged native code or a valid previous live test.
A shared project configuration does not imply identical resource membership or initialization.
[Dependencies](dependencies.md) keeps these distinctions visible.

## Findings that change earlier assumptions

- Generated path UIDs can depend on project name, logical path, source content and collision
  registry state. Existing authored UIDs are separate inputs.
- Import dependencies include importer options/defaults/version, group members, post-import
  scripts, enabled extension editor libraries, and conditionally editor settings/external tools.
- The current import configuration removes all literal resource-reference-valued settings as well as
  autoload/main-scene settings. This is a ruleset restriction, not a universal Godot guarantee.
- Import results, filesystem scan metadata, class/UID/group/extension state, export
  customization caches and renderer caches have different roles.
- Script checks can execute autoloads/static initialization. They are not intrinsically pure
  parser invocations.
- Additional pack mounting changes resource lookup/class/UID state; it does not automatically
  activate new project settings, autoloads or GDExtensions.
- Current wrapper per-import-unit capture is narrower than arbitrary plugin output, and
  current source/export actions still have broad project dependencies.
- Automatic cross-operation import sharing is a design question. Configured aspects and
  explicit dependencies suggest possible mechanisms; their suitability for real Godot imports
  remains an inference, not a required public godot_imports API.

## Maintaining this reference

Preserve the named version/commit baseline and distinguish upstream facts from wrapper
policy and untested conditions. Update the catalogue when those mechanisms change; do not
turn it into a feature task log. Experimental recipes and evidence remain useful independently
of temporary logs.

The [open questions](evidence.md#open-questions-and-coverage-limits), including the importer
contract, group boundaries and automatic context propagation, are domain/design constraints.
Specifications may cite them, but their implementation choices and progress live separately.
