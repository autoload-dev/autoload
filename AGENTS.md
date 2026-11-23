# Working in Autoload

This repository is the Autoload monorepo: tooling and support for the Godot ecosystem. Each
component lives in its own directory with its own Bazel module and releases:
`rules_godot/` holds the Bazel rules for Godot projects, extensions and application packaging,
and `addons/` the Godot add-on modules. The root module holds only the repository's own
tooling in `tools/`: the lanes' work, add-on scaffolding, setup checks, formatting, linting and
the conventions check. A component's builds never load files from the root's `tools/`; only
the ruleset's own maintenance tools may use them, through a development dependency on the root
module (`rules_godot/MODULE.bazel`).

In `rules_godot/`, `godot/` owns the rules and `tools/` the build tools, each with white-box
tests in `tests/` subpackages. `rules_godot/examples/` and `rules_godot/tests/` are
independent consumer modules: the examples and the ruleset regressions, run from their own
directory. Where a test goes and which form it takes is owned by the
[verification architecture](docs/internal/verification-architecture.md). Public guides are in
`rules_godot/docs/public/`, and maintainer references and the
[design principles](docs/internal/principles.md) in `docs/internal/`.

Keep ideas and follow-ups that are not yet planned in [ideas.md](docs/internal/ideas.md).
Agents may propose an entry, with a short reason, but must wait for the user's approval
before adding it. An explicit request to capture items supplies that approval; discovering
an issue while working does not. Check existing entries first to avoid duplicates.
Follow the file's entry format, and remove an entry once a change delivers it.
Implementation needs its own approval. Do not propose, create or maintain GitHub Issues.

Read linked sections when their stated condition applies; links are not a request to load
every referenced document. For examples, read [example guidance](rules_godot/examples/AGENTS.md).
For documentation and every README, read [documentation guidance](docs/AGENTS.md).
For ruleset regression work under `tests/`, read [the test-area map](rules_godot/tests/AGENTS.md).
For the add-on modules under `addons/`, read [add-on guidance](addons/AGENTS.md).

Use English for code, game/example UI, documentation, commits and pull requests.
Use the terms of the [glossary](docs/internal/glossary.md) in code, documentation and
conversation, and follow its naming rules when naming fields, attributes and targets.
Never print the complete environment, tokens or credentials; read only needed non-secret values.
Report conflicting instructions or scope changes before implementation. Record temporary
exceptions beside their owning rule, with the reason and removal condition; remove them when
that condition is met.

# Checks

For implementation and review, follow the short [verification policy](docs/internal/verification.md),
including TDD and evidence reuse. Commands below are entry points, not a checklist for every turn.
From the repository root:

```sh
mise run setup                            # once per clone: install hooks
hk check                                  # lint, setup, conventions, API docs and tooling tests
mise run format                           # when Python/Starlark/Bazel formatting is needed
mise run api-docs                         # after changing the ruleset's public API
mise run code-health                      # Code Health of the change since origin/main; also run before each push
RULES_GODOT_BAZEL_FLAGS=--config=buildbuddy mise run <task>  # offload a large task to BuildBuddy
```

`mise tasks` lists available workflows. Use `mise exec --` before direct commands if mise is
not active in your shell. For missing prerequisites, read [toolchain setup](docs/internal/verification-recipes.md#toolchains).
For the lanes and review readiness, read [lanes](docs/internal/verification-platforms.md).
BuildBuddy is a regular option for builds and tests; choose between local and remote runs
with [when remote execution pays off](docs/internal/verification-recipes.md#when-remote-execution-pays-off).
For its configs, Bazel flags per task and a personal `user.bazelrc`, read
[remote execution](docs/internal/verification-recipes.md#remote-execution-with-buildbuddy).

<a id="bazel-package-boundaries"></a>

# Design and review decisions

When adding or moving packages, targets or Godot tests, use the relevant
[layout section](rules_godot/docs/public/project-layout.md): [package boundaries](rules_godot/docs/public/project-layout.md#build-files-and-package-boundaries),
[target ownership](rules_godot/docs/public/project-layout.md#target-ownership-and-project-context) or
[test ownership](rules_godot/docs/public/project-layout.md#test-ownership). Choose boundaries for meaningful
responsibilities, dependencies, reuse or visibility; neither directory count nor coverage
counts are design goals. Naming/layout checks do not make those choices for you.

When a convention check reports a finding or incomplete coverage, consult the named rule in
[the catalogue](rules_godot/docs/public/conventions.md). Fix findings in source. Reserve `# noqa`,
`# ty: ignore` and `# buildifier: disable=...` for intentional exceptions with a reason.
Computed macro names need a recorded decision in the owning rule, not an assumption that a
passing run checked them.

For convention-checker changes, read [the rule framework](docs/internal/conventions.md#rule-framework).
Rules own their metadata, applicability, predicates, exceptions and adjacent regression tests;
shared evidence tools and the checker remain independent of individual rules. Use rule IDs for
selection, diagnostics and references to specific rules; use descriptive names in navigation
and general task descriptions.

For public Bazel API or documentation-checker changes, use the
[bazel-api-docs skill](.agents/skills/bazel-api-docs/SKILL.md).

# Source and generation conventions

Formatters handle routine source layout. In Starlark, keep long calls and collections easy to
scan, aiming for about 90 columns without splitting labels or URLs. Put `doc` first among named
arguments. For Python/Starlark multiline docstrings and API `doc` strings, put triple quotes on
separate lines and align prose with the closing quotes; retain indentation for lists and fields.
Keep short docstrings on one line. Generated source templates and multiline data retain their
required layout.

For generated documents, keep `*.tpl` files beside their generator. Use Bazel template actions
or replace the same `{NAME}` placeholders in a build-time tool. Short optional/repeated blocks
may be produced in code; a placeholder alone on its line stands for such a block.

When changing exporters, obtain export options, defaults and project settings from Godot's
shell probe (`tools/action/shell.gd`), not copies in Starlark or Python. Keep remaining per-minor tables
and constants in `godot/private/engine/profiles.bzl` and pass them to build tools as data.

# Code Health (CodeScene)

The CodeHealth MCP server measures maintainability as Code Health, from 10.0 (optimal) down
to 1.0. Treat it as the measure for maintainability and aim for 10.0; the glossary,
conventions and design decisions above still decide naming, structure and package
boundaries. Call the matching CodeHealth MCP tool instead of guessing.

- **Safeguard every change.** After changing a file, run `code_health_review` on it, or
  `mise run code-health -- --only <path>...` for Starlark and GDScript. Before a pull request,
  run `mise run code-health`: it reviews the files changed since the merge base with
  `origin/main`, untracked ones included, prints each file's score before and after with
  every new finding's function and lines, and fails when a file declines: its score falls,
  or a new file scores below 9.0. It also fails when CodeScene cannot score a file, such as
  with an expired token. The pre-push hook runs it too, and passes with a note on a machine
  without the CodeScene CLI or token. If it reports a decline, refactor until it is resolved.
- **Accept a decline only in the code.** When a finding is deliberate, put
  `# @codescene(disable:"<rule>")` (`//` in C-like languages; one line per rule, or
  `disable-all`) directly above the function's definition, with a comment that gives the
  reason. A failing review prints the directive for each new finding. There is no other way
  to acknowledge a decline.
- **Refactor guided by Code Health.** Record a baseline with `code_health_review` and
  `code_health_score`, fix the highest-leverage findings in 3–5 small structural steps, and
  re-run the review after each step. Stop when the targeted findings are substantially
  reduced and the score measurably improved; cosmetic edits are not progress.
- **Starlark, GDScript and whole-repository scans.** The MCP tools reject Starlark (`.bzl`)
  and GDScript (`.gd`); `mise run code-health` scores them through the same CodeScene CLI as
  Python. Starlark documentation strings and `doc` values do not count, and Bazel macros are
  exempt from the argument count, since their parameters mirror rule attributes.
  `mise run code-health -- --survey` reports the whole checkout with its hotspots;
  `--base <ref>` reviews a change against another ref. It needs the CodeHealth MCP server to
  have run once and a configured CodeScene token; report the gap when either is missing.

<!-- entire-agent:begin -->
Read .entire/agent-guide.md for this repository's workflow, source inspection, and verification guidance.
@.entire/agent-guide.md
<!-- entire-agent:end -->
