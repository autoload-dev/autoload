---
name: code-health
description: Review and improve the Code Health of a change set, the diff since origin/main or given files, with subagents that report findings on readable file structure, reading order, file boundaries, plain-language comments and CodeScene's findings, then weigh them and apply the selected ones. Use before every pull request, between /simplify and /code-review, or when asked to review files' structure or Code Health.
---

# Code Health

Review a change set the way `/simplify` does: subagents only report findings, and you, the
main agent, deduplicate, sort and select them, apply the selected ones and name the reasons
for the rest. Change structure and comments only: order, regions, heads, splits and merges of
files, the wording of comments, and refactorings of CodeScene's findings. Never change
behavior.

The rules are in [readable files](../../../docs/internal/code-health.md#readable-files); the
region header and the reading order are
[region-headers-named-in-head](../../../docs/internal/conventions.md#region-headers-named-in-head)
and
[definitions-before-callers](../../../docs/internal/conventions.md#definitions-before-callers).

## 1. Prepare

1. Run `aspect code-health --history`, or with `-- --only <path>...` for given files. Its
   files are the change set: by default the change since the merge base with `origin/main`,
   untracked files included. Leave out generated files, lock files and fixtures that
   exercise unusual forms. Per file it gives the commits, the files it changes with and which
   regions changed together.
2. Run `aspect code-health` (`-- --only <path>...` for given files) for CodeScene's findings
   and declined files. If CodeScene is unavailable, say so and leave out its subagent.
3. Run
   `bazel run //tools/conventions -- --rule region-headers-named-in-head --rule definitions-before-callers`
   and the lint check of Python:
   `aspect exec -- bazel build --config=lint --target_pattern_file=root.targets` in the root
   and `aspect exec -- bazel build --config=lint //...` in `rules_godot/`, and the file lint
   of GDScript, Markdown and the other files without targets: `bazel run //tools/lint:files`
   (`-- <path>...` for given files). Their findings are fixed directly; the subagents do not
   repeat them.
4. Choose each file's scope. A file in the busiest quarter of the history, or with five or
   more commits, is reviewed whole; other files only where the change touches them.

## 2. Review with subagents

Start the five subagents in one message, so they run in parallel, and set each one's model
and reasoning effort yourself: the Sonnet model in Claude Code, the Sol model in Codex, with
the effort the table gives. Give each the files with their scope, the history report and its
rules. Each returns findings only and edits nothing. A finding names its file, line, rule, a
concrete proposal, the reason, and whether a hook or check would fail without it.

| Subagent | Reviews | Effort |
|---|---|---|
| Structure | Rules 1 to 3 of [readable files](../../../docs/internal/code-health.md#readable-files): heads, regions, grouping by topic. Where the current order mixes topics, propose moving declarations into the region of their topic, as long as each helper stays above its first caller; do not cut regions around a poor order. | medium |
| Order and layout | Rules 4 and 5: helpers close above their first caller, the layout of the file's kind, GDScript's method order, which gdlint does not check. | medium |
| Boundaries | Rule 6 with the history: regions that change apart, files that always change together, a region that hides a split that is due. | high |
| Comments | Rule 7 and [comments](../../../docs/internal/code-health.md#comments): heads, docstrings, `doc` strings and comments in scope, BUILD files included. For each one that is hard to follow, says what the code already says, or no longer matches the code, a rewritten text about as long as the original, or its removal. | medium |
| CodeScene | Each new finding of a declined file, and the findings of files in scope: a refactoring that removes it; its directive only with a reason. | high |

Without subagents, as in an agent that cannot start them, run the five reviews yourself, one
after the other.

## 3. Weigh and apply

1. Merge findings that concern the same place or mechanism.
2. Sort them: what makes a hook or check fail first (a declined file,
   region-headers-named-in-head, definitions-before-callers), then by the file's commits, most
   first.
3. Resolve conflicts. When regions and a split are both proposed for one file, take the
   smaller change unless the history shows the parts change apart.
4. Select. Leave out what changes behavior, undoes a cleanup of `/simplify`, or restructures
   much of a rarely changed file the change barely touches. Take a rewritten comment only
   when it keeps the meaning and is not longer than needed.
5. Apply the selected findings. Then run the tests of the changed files,
   `bazel run //tools/conventions` and `aspect code-health`.

## 4. Report

List what you applied and, for each finding you left out, the reason in one line.
