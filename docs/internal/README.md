# Internal reference

These are long-lived resources for contributors and agents that cover the whole repository:
verification, conventions, releasing, the glossary and the agent setup. The ruleset's own
references, from its design principles to its architecture and Godot pipeline catalogue, are in
the [ruleset's internal reference](../../rules_godot/docs/internal/README.md).
Use the [public guides](../../rules_godot/docs/public/README.md) for supported consumer workflows.

| Resource | Purpose | Review when |
|---|---|---|
| [Glossary](glossary.md) | The terms code, documentation and conversation use, and the terms to avoid | Naming a concept, field, attribute or target |
| [Verification policy](verification.md) | TDD, execution timing, evidence reuse and completion | Making or reviewing a change |
| [Verification architecture](verification-architecture.md) | Test kinds, placement, boundaries, coverage and altitude | Adding a test or reviewing a change's tests |
| [Verification hosts](verification-platforms.md) | Representative matrix, the host jobs CI runs and the Apple hosts | Operating-system, build or toolchain behavior changes or review readiness |
| [Verification recipes and fixtures](verification-recipes.md) | Environment setup, API regeneration, runtime acceptance and fixture commands | The specific operation or fixture is needed |
| [Repository conventions](conventions.md) | The convention rules: their names, applicability, automated coverage and limits | Convention meanings or checker behavior changes |
| [Releasing](releasing.md) | Tagging a release, the release archive and publishing to the Bazel Central Registry | Release or registry automation changes |
| [Gazelle for Godot](gazelle.md) | What the Godot language of Gazelle declares, the attributes it owns, its directives and design | A Godot project's BUILD declarations or the language change |
| [Code Health](code-health.md) | How the hooks score maintainability, accept findings and find refactoring targets | A Code Health hook fails or before refactoring an area |
| [Agent setup](agent-setup.md) | What Claude Code and Codex load, their hooks and worktrees, and Entire | Agent configuration, hooks or worktrees change |
