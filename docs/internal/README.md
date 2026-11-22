# Internal reference

These are long-lived resources for contributors and agents. They describe user outcomes,
architecture and source-backed domain mechanisms independently of any single change.
Use the [public guides](../../rules_godot/docs/public/README.md) for supported consumer workflows.

| Resource | Purpose | Review when |
|---|---|---|
| [Design principles](principles.md) | Product goal, the principles that govern designs and reviews, and the design checks | Product direction or a principle changes |
| [Ideas and to-dos](ideas.md) | Candidate work that is not yet planned | Capturing or delivering an idea |
| [Capability overview](capability-overview.md) | Compact map of foundations, shared operations and quality goals | Product outcomes materially change |
| [Capability matrix](capabilities.md) | Goal rationale, scope decisions, stable outcome/reference IDs and evidence-qualified coverage | Actual support or intended scope materially changes |
| [Godot pipeline catalogue](godot-pipeline/README.md) | Inputs, outputs, operations, dependencies and their source evidence | Engine/plugin/toolchain semantics change |
| [Android shell](android-shell.md) | How the Android shell follows Godot's Gradle export, its remaining differences and the review of a new Godot version | Changing the Android shell or pinning a Godot source |
| [Export option inventory](export-option-inventory.md) | Reviewed disposition of every built-in exporter option and how to compare a new Godot version | Adding a Godot minor or changing owned/rejected export options |
| [Export-plugin hook inventory](export-plugin-hook-inventory.md) | Reviewed disposition and Bazel declaration that replaces every `EditorExportPlugin` hook | Adding a Godot minor or porting an add-on's export plugin |
| [Glossary](glossary.md) | The terms code, documentation and conversation use, and the terms to avoid | Naming a concept, field, attribute or target |
| [Architecture](architecture.md) | Ruleset layers and reuse boundaries | Implementation architecture changes |
| [Verification policy](verification.md) | TDD, execution timing, evidence reuse and completion | Making or reviewing a change |
| [Verification architecture](verification-architecture.md) | Test kinds, placement, boundaries, coverage and altitude | Adding a test or reviewing a change's tests |
| [Verification selection and lanes](verification-platforms.md) | Representative matrix, changed-path selection and Apple lanes on pull requests | Operating-system, build or toolchain behavior changes or review readiness |
| [Verification recipes and fixtures](verification-recipes.md) | Environment setup, API regeneration, runtime acceptance and fixture commands | The specific operation or fixture is needed |
| [Repository development](development.md) | BUILD and resource-graph maintenance | Contributor workflows change |
| [Convention inventory and enforcement design](conventions.md) | Existing policy sources, automation limits, framework research and catalogue candidates | Convention meanings or checker architecture changes |
| [API reference maintenance](api-reference.md) | Public API inventory, generation and documentation checks | Public surface or reference tooling changes |
| [Releasing](releasing.md) | Tagging a release, the release archive and publishing to the Bazel Central Registry | Release or registry automation changes |

Changes may refer to these resources and own their own scope, tasks and progress. The
references do not depend on those changes or mirror their completion state.
Research baseline dates and source provenance remain explicit; routine CI runs do not make
a new reference revision necessary.
