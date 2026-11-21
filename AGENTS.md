# Working in rules_godot

This repository provides Bazel rules for Godot projects, extensions and application
packaging. `godot/` owns the rules and `tools/` the build tools, each with white-box tests in
`tests/` subpackages. `examples/`
and `tests/` are independent consumer modules: the examples and the ruleset regressions, run
from their own directory. Where a test goes and which form it takes is owned by the
[verification architecture](docs/internal/verification-architecture.md). Public guides are in `docs/public/`, and maintainer references and the
[design principles](docs/internal/principles.md) in `docs/internal/`.

Keep ideas and follow-ups that are not yet planned in [ideas.md](docs/internal/ideas.md).
Agents may propose an entry, with a short reason, but must wait for the user's approval
before adding it. An explicit request to capture items supplies that approval; discovering
an issue while working does not. Check existing entries first to avoid duplicates.
Follow the file's entry format, and remove an entry once a change delivers it.
Implementation needs its own approval. Do not propose, create or maintain GitHub Issues.

Read linked sections when their stated condition applies; links are not a request to load
every referenced document. For examples, read [example guidance](examples/AGENTS.md).
For documentation and every README, read [documentation guidance](docs/AGENTS.md).
For ruleset regression work under `tests/`, read [the test-area map](tests/AGENTS.md).

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
hk check                                  # selected checks for uncommitted changes
hk check --plan --from-ref origin/main     # preview selection for the whole branch
hk check --from-ref origin/main            # check branch changes, including committed work
mise run format                           # when Python/Starlark/Bazel formatting is needed
RULES_GODOT_BAZEL_FLAGS=--config=buildbuddy mise run <task>  # offload a large task to BuildBuddy
```

`mise tasks` lists available workflows. Use `mise exec --` before direct commands if mise is
not active in your shell. For missing prerequisites, read [toolchain setup](docs/internal/verification-recipes.md#toolchains).
For affected lanes or review readiness, read [selection and lanes](docs/internal/verification-platforms.md).
BuildBuddy is a regular option for builds and tests; choose between local and remote runs
with [when remote execution pays off](docs/internal/verification-recipes.md#when-remote-execution-pays-off).
For its configs, Bazel flags per task and a personal `user.bazelrc`, read
[remote execution](docs/internal/verification-recipes.md#remote-execution-with-buildbuddy).

<a id="bazel-package-boundaries"></a>

# Design and review decisions

When adding or moving packages, targets or Godot tests, use the relevant
[layout section](docs/public/project-layout.md): [package boundaries](docs/public/project-layout.md#build-files-and-package-boundaries),
[target ownership](docs/public/project-layout.md#target-ownership-and-project-context) or
[test ownership](docs/public/project-layout.md#test-ownership). Choose boundaries for meaningful
responsibilities, dependencies, reuse or visibility; neither directory count nor coverage
counts are design goals. Naming/layout checks do not make those choices for you.

When a convention check reports a finding or incomplete coverage, consult the named rule in
[the catalogue](docs/public/conventions.md). Fix findings in source. Reserve `# noqa`,
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

- **Safeguard every change.** After changing a file, run `code_health_review` on it. Before
  suggesting a commit, run `pre_commit_code_health_safeguard`; before a pull request,
  `analyze_change_set` against `origin/main`. If either reports a regression, inspect the
  file with `code_health_review` and refactor until it is resolved, or name the accepted risk.
- **Refactor guided by Code Health.** Record a baseline with `code_health_review` and
  `code_health_score`, fix the highest-leverage findings in 3–5 small structural steps, and
  re-run the review after each step. Stop when the targeted findings are substantially
  reduced and the score measurably improved; cosmetic edits are not progress.
- **Starlark, GDScript and whole-repository scans.** The MCP tools reject Starlark (`.bzl`)
  and GDScript (`.gd`). `mise run code-health -- --only <path>...` reviews any files like
  `code_health_review`, those included: it feeds them to the same CodeScene CLI as Python
  and exempts Bazel macros from the argument count, since their parameters mirror rule
  attributes. Without `--only` it reports the whole checkout with hotspots; add
  `--compare origin/main` for per-file deltas. It needs the CodeHealth MCP server to have
  run once and a configured CodeScene token; report the gap when either is missing.

<!-- entire-agent:begin -->
Read .entire/agent-guide.md for this repository's workflow, source inspection, and verification guidance.
@.entire/agent-guide.md
<!-- entire-agent:end -->
