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
`rules_godot/docs/public/`. Maintainer references that cover the whole repository, such as
verification, conventions, releasing and the glossary, are in [docs/internal/](docs/internal/README.md);
those of the ruleset alone, such as its architecture and the
[design principles](rules_godot/docs/internal/principles.md), are in
[rules_godot/docs/internal/](rules_godot/docs/internal/README.md).

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
./bootstrap.sh                            # once per clone: install bazel and aspect, the Git hooks and Android SDK packages
aspect pre-commit                         # what the pre-commit hook runs: format and stage, lock files, Code Health of the staged change
aspect pre-push                           # what the pre-push hook runs: format, lint, generated files, conventions, tests, API docs, Code Health
aspect format                             # format and lint Starlark in changed files (--scope=all for the whole tree)
aspect lint                               # lint the current module's Python with Ruff and ty
aspect generate                           # regenerate lock files
aspect work docs                          # after changing the ruleset's public API
aspect code-health                        # Code Health of the change since origin/main; the pre-push hook runs it too
aspect code-health --survey               # Code Health of the whole checkout, to find refactoring targets
RULES_GODOT_BAZEL_FLAGS=--config=buildbuddy aspect work <name>  # offload a large task to BuildBuddy
```

A checkout needs only Bazelisk (`bazel`) and the Aspect CLI (`aspect`), which
`./bootstrap.sh` installs. `aspect help` lists the tasks. Use `aspect exec --` before direct
commands that need the repository environment (the Android variables, Bazel's Python as
`python3`). For missing prerequisites, read [toolchain
setup](docs/internal/verification-recipes.md#toolchains). For the lanes and review
readiness, read [lanes](docs/internal/verification-platforms.md). BuildBuddy is a regular
option for builds and tests; choose between local and remote runs with [when remote
execution pays off](docs/internal/verification-recipes.md#when-remote-execution-pays-off).
For its configs, Bazel flags per task and a personal `user.bazelrc`, read [remote
execution](docs/internal/verification-recipes.md#remote-execution-with-buildbuddy).

<a id="worktrees"></a>

# Worktrees

This section is the one description of how worktrees reuse Bazel's state; the scripts and
configuration it names link here. Worktrees come from the Aspect CLI's pool under
`~/.aspect/worktrees`, whose slots keep their path, so a new worktree starts with a warm Bazel
server and output base. Claude Code's worktrees (`claude --worktree`, subagents with worktree
isolation) take a slot through the `WorktreeCreate` and `WorktreeRemove` hooks in
`.claude/settings.json` ([tools/claude/worktree.sh](tools/claude/worktree.sh)), on a branch
`claude/<name>` from `origin`'s default branch. By hand, `aspect worktree add <branch>
--create=origin/main` takes a slot, `aspect worktree release <branch>` gives it back with its
Bazel state, and `aspect worktree list` shows who holds which.

Codex creates its worktrees itself, each at a new path, and has no hook that replaces that,
so they recycle the Bazel state rather than the path. Codex's `SessionStart` hook in
[.codex/hooks.json](.codex/hooks.json), in the CLI as in the app, leases a Bazel slot under
`~/.aspect/bazel-slots` for a session in a linked worktree, and [tools/bazel](tools/bazel)
then gives every module the slot's output base for it: a new worktree reuses the fetched
repositories and the action cache of an earlier one, though not its analysis. The slots'
output bases lie under Bazel's output user root with hash names like any other, so `aspect
output-bases` lists them and `aspect gc` collects them by the same rules. `SessionEnd` stops
the worktree's Bazel servers and gives the slot back; a slot whose worktree is gone counts as
free ([tools/codex/worktree.sh](tools/codex/worktree.sh)). Codex reads a linked worktree's
project hooks from the main checkout and runs a new or changed hook only once it is
approved in Codex.

<a id="bazel-package-boundaries"></a>

# Design and review decisions

rules_godot and the add-on modules are released but early, with few users: breaking changes
are fine, so add no compatibility shims, aliases or migration layers.

When weighing design options, look at how mature Bazel rulesets solve the problem, especially
those of aspect-build, and read their code rather than guessing.

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

# Issues, pull requests and CI changes

- GitHub Issues stay conceptual unless the user asks otherwise: the goal, the problem and its
  context, without attribute names, rule shapes or implementation steps.
- Several dependent pull requests of one feature form one `gh stack`; a green,
  self-contained lower layer may merge alone. Push each branch from its own checkout, which
  the pre-push hook requires.
- Validate and debug CI changes in a temporary job that runs only what the change needs, and
  remove it afterwards; do not run the whole CI for every attempt.
- Claude Code only: before every pull request, follow-ups included, run `/simplify` and apply
  its cleanups, then `/code-review` and fix its findings, running the relevant tests after each.

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

Code Health measures maintainability from 10.0 (optimal) down to 1.0; aim for 10.0. The
glossary, conventions and design decisions above still decide naming, structure and package
boundaries. In this repository `tools/code_health` is the one way to measure it: it scores
every language here, Starlark and GDScript included, with the CodeScene CLI `cs`, pinned in
`multitool.lock.json` and built by `aspect code-health`. Do not use the CodeHealth MCP tools or
the CodeScene plugin skills here; the Git hooks and `aspect code-health` below replace them.

- **The hooks check; work freely in between.** The pre-commit hook (`aspect pre-commit`)
  reviews the staged change, the pre-push hook (`aspect pre-push`) the branch against its
  merge base with `origin/main`. It fails when a file declines (its
  score falls, or a new file scores below 9.0) or when CodeScene cannot score a file, and
  prints every new finding with its function and lines. Intermediate states need no review;
  run `aspect code-health` whenever an early look helps, such as before committing a larger
  change.
- **When a hook fails,** refactor the declined file until it no longer declines. Accept a
  finding only deliberately, in the code: the failing output prints the directive for each
  new finding, `# @codescene(disable:"<rule>")` (`//` in C-like languages, one line per
  rule), to put above the function's definition with a comment that gives the reason. There
  is no other way to acknowledge a decline.
- **Find refactoring targets with the survey.** `aspect code-health --survey` reports the
  whole checkout: languages, hotspots (commits × (10 − score)) and the lowest scores. It is
  no gate; use it to choose what to improve, such as before working in an area. Refactor in
  small structural steps and review the files again with `aspect code-health -- --only
  <path>...` until the targeted findings are gone.
- **Starlark and GDScript** are scored as translated Python: documentation strings and `doc`
  values do not count, and Bazel macros are exempt from the argument count, since their
  parameters mirror rule attributes.
- **Setup:** set `CS_ACCESS_TOKEN` to a CodeScene personal access token kept outside the
  repository, such as in the macOS keychain, read by your own shell or user-level
  configuration; with a CodeScene account, `cs auth login` works instead. Without either,
  the hook passes with a note and `aspect code-health` reports the gap.

<!-- entire-agent:begin -->
Read .entire/agent-guide.md for this repository's workflow, source inspection, and verification guidance.
@.entire/agent-guide.md
<!-- entire-agent:end -->
