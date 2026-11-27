# Agent setup

The repository works with Claude Code and Codex from one set of instructions: the
`AGENTS.md` files. This page describes what each agent loads, which files configure them,
how their worktrees reuse Bazel's state and what Entire records.

## Instructions and skills

Both agents read the root [AGENTS.md](../../AGENTS.md) at the start of a session and an
area's `AGENTS.md` when they work there. Claude Code reads `AGENTS.md` only while no
`CLAUDE.md` exists in the working directory or above it, so the repository keeps none; rules
for Claude Code alone stay in `AGENTS.md`, marked as such.

Skills live once, in `.agents/skills/`, where Codex finds them. Claude Code finds project
skills only in `.claude/skills/`, which holds a link to each skill directory. The conventions
check enforces both ([RG017](conventions.md#rg017) and [RG018](conventions.md#rg018)); the
[file lint](verification-recipes.md#the-file-lint) checks the links in these files.

| File | Owner | Purpose |
|---|---|---|
| `AGENTS.md`, `*/AGENTS.md` | Repository | Instructions for every agent |
| `.agents/skills/<name>/`, `.claude/skills/<name>` (link) | Repository | Skills, loaded on demand |
| `.claude/settings.json` | Entire, except `WorktreeCreate` and `WorktreeRemove` | Claude Code's hooks |
| `.codex/hooks.json` | Entire, except the `tools/codex/worktree.sh` hooks | Codex's hooks |
| `.codex/environments/environment.toml` | Repository | The Codex app's environment: `./bootstrap.sh --tools-only` |

<a id="worktrees"></a>

## Worktrees

Worktrees come from the Aspect CLI's pool under `~/.aspect/worktrees`, whose slots keep their
path, so a new worktree starts with a warm Bazel server and output base. Claude Code's
worktrees (`claude --worktree`, subagents with worktree isolation) take a slot through the
`WorktreeCreate` and `WorktreeRemove` hooks in `.claude/settings.json`
([tools/claude/worktree.sh](../../tools/claude/worktree.sh)), on a branch `claude/<name>` from
`origin`'s default branch. By hand, `aspect worktree add <branch> --create=origin/main` takes
a slot, `aspect worktree release <branch>` gives it back with its Bazel state, and `aspect
worktree list` shows who holds which.

Codex creates its worktrees itself, each at a new path, and has no hook that replaces that,
so they recycle the Bazel state rather than the path. Codex's `SessionStart` hook in
`.codex/hooks.json`, in the CLI as in the app, leases a Bazel slot under
`~/.aspect/bazel-slots` for a session in a linked worktree, and [tools/bazel](../../tools/bazel)
then gives every module the slot's output base for it: a new worktree reuses the fetched
repositories and the action cache of an earlier one, though not its analysis. The slots'
output bases lie under Bazel's output user root with hash names like any other, so `aspect
output-bases` lists them and `aspect gc` collects them by the same rules. `SessionEnd` stops
the worktree's Bazel servers and gives the slot back; a slot whose worktree is gone counts as
free ([tools/codex/worktree.sh](../../tools/codex/worktree.sh)). Codex reads a linked
worktree's project hooks from the main checkout and runs a new or changed hook only once it
is approved in Codex.

## Entire

[Entire](https://docs.entire.io) records Claude Code's and Codex's sessions and links them to
commits as checkpoints, which it pushes to the private repository
`autoload-dev/autoload-checkpoints`. The repository uses it for that alone: no Entire skills,
agents or guides. Its settings are in `.entire/settings.json`; `entire agent add` writes its
hooks into the two hook files and keeps the repository's own beside them, so do not edit
Entire's entries by hand.

Entire is optional and installed per person, outside the repository. Its agent hooks above,
and the Git hooks `entire enable` installs in a clone, do nothing without it, so a session
is then not recorded; `aspect doctor` warns about that. With
`absolute_git_hook_path` in `.entire/settings.local.json`, the Git hooks name the binary by
its path, which an update of Entire leaves stale; `entire configure --force` writes them
again.
