# Internal reference

These are long-lived resources for contributors and agents that cover the whole repository:
verification, conventions, releasing, the glossary and the agent setup. The ruleset's own
references, from its design principles to its architecture and Godot pipeline research, are in
the [ruleset's internal reference](../../rules_godot/docs/internal/README.md).
Use the [public guides](../../rules_godot/docs/public/README.md) for supported consumer workflows.

| Resource | Purpose | Review when |
|---|---|---|
| [Glossary](glossary.md) | The terms code, documentation and conversation use, and the terms to avoid | Naming a concept, field, attribute or target |
| [Verification policy](verification.md) | TDD, execution timing, evidence reuse and completion | Making or reviewing a change |
| [Verification architecture](verification-architecture.md) | Test kinds, placement, boundaries, coverage and altitude | Adding a test or reviewing a change's tests |
| [Verification lanes](verification-platforms.md) | Representative matrix, the lanes CI runs and the Apple lanes | Operating-system, build or toolchain behavior changes or review readiness |
| [Verification recipes and fixtures](verification-recipes.md) | Environment setup, API regeneration, runtime acceptance and fixture commands | The specific operation or fixture is needed |
| [Convention inventory and enforcement design](conventions.md) | Existing policy sources, automation limits, framework research and catalogue candidates | Convention meanings or checker architecture changes |
| [Releasing](releasing.md) | Tagging a release, the release archive and publishing to the Bazel Central Registry | Release or registry automation changes |
| [Code Health](code-health.md) | How the hooks score maintainability, accept findings and find refactoring targets | A Code Health hook fails or before refactoring an area |
| [Agent setup](agent-setup.md) | What Claude Code and Codex load, their hooks and worktrees, and Entire | Agent configuration, hooks or worktrees change |
| [Ruleset internal reference](../../rules_godot/docs/internal/README.md) | The ruleset's own principles, capabilities, architecture, Godot pipeline research, export inventories, Android shell, BUILD maintenance and API reference maintenance | Working on the ruleset |

Changes may refer to these resources and own their own scope, tasks and progress. The
references do not depend on those changes or mirror their completion state.
Research baseline dates and source provenance remain explicit; routine CI runs do not make
a new reference revision necessary.
