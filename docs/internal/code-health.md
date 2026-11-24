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

Starlark and GDScript are scored as translated Python: documentation strings and `doc` values
do not count, and Bazel macros are exempt from the argument count, since their parameters
mirror rule attributes.

## Setup

Set `CS_ACCESS_TOKEN` to a CodeScene personal access token kept outside the repository, such
as in the macOS keychain, read by your own shell or user-level configuration; with a
CodeScene account, `cs auth login` works instead. Without either, the hook passes with a note
and `aspect code-health` reports the gap.
