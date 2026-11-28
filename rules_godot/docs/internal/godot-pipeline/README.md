# Godot Pipeline Input, Output and Dependency Catalogue

**Date:** 2026-11-01.
This is a durable reference for Godot processing. It records the source-backed mechanisms of
Godot's pipeline as researched at the baseline below. Facts about the ruleset (tag R) describe
the baseline commit, not the present code; check the files they cite before relying on them.

The [capability matrix](../capabilities.md) lists the user outcomes the ruleset supports.
Review this catalogue when the underlying engine, plugin or toolchain semantics materially
change.

## Scope and baseline

- Repository baseline: `506d045ec401effdcb93986dfa0ca2064dbfd78a`.
- Godot: 4.7.2-stable, commit `ed1daf0bf001b61586d9930840f2f1394092c079`.
  A cached official macOS executable reported `4.7.2.stable.official.ed1daf0bf`.
- Bazel: 9.3.0. GdUnit: 6.2.2, commit `0127a55f4543dfc24746f6e5c7ba6f94105d51f2`.
- Application and toolchain boundaries: the Linux, macOS, Android and iOS workflows,
  rules_android 0.8.0, rules_apple 5.3.1, and the engine, toolchain and engine profile
  declarations.
- Engine/source patches, modules and actual tool binaries are inputs. A stock version string
  does not establish identity with a source-built engine. The optional next-minor probe is not a
  second researched Godot baseline. [S01](evidence.md#s01)

Coverage is by relevant artifact/operation classes, not every possible filename or setting.
Arbitrary extension code can add dependencies and outputs; this is not a proof of universal
plugin hermeticity or support for every upstream export option.

The catalogue contains **50 artifact classes, 21 operations and 25 explicit dependency edges**,
with source/conditionality evidence.

## Reading order

1. [Artifacts](artifacts.md): sources, generated intermediates, delivered products and state.
2. [Operations](operations.md): reads, writes, phase boundaries and Bazel ownership.
3. [Dependencies](dependencies.md): edges, conditionality, reuse and invalidation.
4. [Evidence](evidence.md): pinned sources and focused probes.

Artifacts use stable `ART-*` IDs; operations use `OP-*` IDs. These are research identifiers,
not proposed Starlark symbols. Artifact classes can be both input and output across invocations.
A mutable file read before an operation and its updated version after it are distinct states,
so the class-level diagrams do not represent an action cycle.

## Evidence and edge notation

| Mark | Meaning |
|---|---|
| F | Established by inspected pinned upstream source |
| R | Established by the repository source at the baseline commit; may be wrapper policy rather than engine necessity |
| E | Observed in a bounded experiment; only its stated case is established |
| I | Inference or modelling obligation derived from the facts, not a measured implementation result |
| U | Deliberately unbounded dependency or coverage |
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

## Key findings

- Generated path UIDs can depend on project name, logical path, source content and collision
  registry state. Existing authored UIDs are separate inputs.
- Import dependencies include importer options/defaults/version, group members, post-import
  scripts, enabled extension editor libraries, and conditionally editor settings/external tools.
- Import results, filesystem scan metadata, class/UID/group/extension state, export
  customization caches and renderer caches have different roles.
- Script checks can execute autoloads/static initialization. They are not intrinsically pure
  parser invocations.
- Additional pack mounting changes resource lookup/class/UID state; it does not automatically
  activate new project settings, autoloads or GDExtensions.

## Maintaining this reference

Preserve the named version/commit baseline and distinguish upstream facts from wrapper
policy and untested conditions. Update the catalogue when those mechanisms change; do not
turn it into a feature task log. Experimental recipes and evidence remain useful independently
of temporary logs.
