# Code Health

Code Health measures maintainability from 10.0 (optimal) down to 1.0. `tools/code_health`
scores every language here, Starlark and GDScript included, with the CodeScene CLI `cs`,
pinned in `multitool.lock.json` and built by `aspect code-health`.

## The hooks

The pre-commit hook reviews the staged change, the pre-push hook the branch against its merge
base with `origin/main`. A hook fails when
a file declines (its score falls, or a new file scores below 9.0) or when CodeScene cannot
score a file, and prints every new finding with its function and lines. Intermediate states
need no review; run `aspect code-health` whenever an early look helps, such as before
committing a larger change.

When a hook fails, refactor the declined file until it no longer declines. Accept a finding
only deliberately, in the code: the failing output prints the directive for each new
finding, `# @codescene(disable:"<rule>")` (`//` in C-like languages, one line per rule), to
put above the function's definition with a comment that gives the reason. There is no other
way to acknowledge a decline.

## Survey and scoring

`aspect code-health --survey` reports the whole checkout: languages, hotspots (commits × (10 −
score)) and the lowest scores. It is no gate; use it to choose what to improve, such as
before working in an area. Refactor in small structural steps and review the files again with
`aspect code-health -- --only <path>...` until the targeted findings are gone.

`aspect code-health --history` reports how often the change's files changed, by default in the
last six months: per file its commits, the files it changed with most often, and which of its
[regions](conventions.md#region-headers-named-in-head) changed together. It needs Git alone and
follows renames; `-- --only <path>...` reports given files and `-- --since all` the whole
history.

Starlark and GDScript are scored as translated Python: documentation strings and `doc` values
do not count, and Bazel macros are exempt from the argument count, since their parameters
mirror rule attributes.

## Setup

Set `CS_ACCESS_TOKEN` to a CodeScene personal access token kept outside the repository, such
as in the macOS keychain, read by your own shell or user-level configuration; with a
CodeScene account, `cs auth login` works instead. Without either, the hook passes with a note
and `aspect code-health` reports the gap.

## Readable files

Code Health scores what CodeScene measures, such as long or complex functions. How a file is
organized, so that a reader finds a topic quickly, is reviewed by the
[`code-health` skill](#the-code-health-skill) and partly checked by linters and convention
rules. Long files are fine; a file is split by its dependencies, never by its length alone.

1. **A head with an overview.** A Python, Starlark or Markdown file starts with its purpose; if
   it has regions, its head names them after `Sections:` (ruff D100, buildifier
   `module-docstring`, rumdl MD041,
   [region-headers-named-in-head](conventions.md#region-headers-named-in-head)). Tests need no
   docstring.
2. **Named regions.** A file with several topics divides into regions, each starting with a
   region header and declaring at least two names
   ([region-headers-named-in-head](conventions.md#region-headers-named-in-head)); a file with
   one topic has none.
3. **Grouped by topic, not by kind.** What the whole file needs stands above the first region;
   what one region needs stands in it. There is no block of all constants or all helpers.
4. **One reading direction, short distances.** A definition stands before its first caller and
   close to it, so a region ends with its entry point
   ([definitions-before-callers](conventions.md#definitions-before-callers) for Python;
   Starlark requires it on its top level).
5. **Files of one kind share one layout.** BUILD files: `load`, `package()`, `exports_files`,
   the main target, its parts, tests last. `MODULE.bazel`: `module()`, `bazel_dep`s,
   extensions by ecosystem, development dependencies and overrides last. GDScript follows the
   code order of Godot's style guide (gdlint `class-definitions-order` up to the variables).
6. **Split by dependencies.** A part becomes a file of its own when it has dependencies, users
   or a change rhythm of its own, which `aspect code-health --history` shows. A region is no
   substitute for a split that is due.

The rules follow what research supports: navigation follows cues and dependencies rather than
linear reading, the order of definitions matters less than their distance, and size alone
predicts defects poorly while low cohesion and co-change predict them well.

## The code-health skill

`/code-health` ([.agents/skills/code-health](../../.agents/skills/code-health/SKILL.md)) reviews
the Code Health of a change: by default the diff since the merge base with `origin/main`, or
the files it is given. Like `/simplify`, it lets subagents produce findings and decides
itself: it deduplicates and sorts them, applies those it selects and names the reasons for the
rest. Its subagents review the structure (rules 1 to 3), the order and layout (rules 4 and 5),
the boundaries with the change history (rule 6), and CodeScene's findings. It runs before every
pull request, between `/simplify` and `/code-review`.
