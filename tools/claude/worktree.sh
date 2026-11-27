#!/usr/bin/env bash
# Claude Code's WorktreeCreate and WorktreeRemove hooks (.claude/settings.json), which take
# Claude's worktrees from the Aspect CLI's worktree pool (docs/internal/agent-setup.md,
# "Worktrees").
#
#   worktree.sh create   reads {"name", "session_id", "cwd"} on stdin; leases a slot on a new
#                        branch claude/<name> from origin's default branch, as Claude's own
#                        worktrees start, and prints its directory last on stdout
#   worktree.sh remove   reads {"worktree_path", "cwd"} on stdin; ends the lease, keeping the
#                        slot and the branch; refuses a worktree that holds uncommitted work
set -euo pipefail

input="$(cat)"

# One string field of the hook's JSON input; the fields used here hold no quotes.
field() {
    sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" <<<"$input" | head -n 1
}

cd "$(field cwd)"

# The Aspect CLI on PATH, else the launcher `aspect bootstrap` recorded: an app's hooks may run
# with a shorter PATH than a shell.
aspect="$(command -v aspect || git config aspect.launcher || true)"
[[ -x "$aspect" ]] || {
    echo "worktree.sh: the Aspect CLI is missing; run ./bootstrap.sh" >&2
    exit 1
}
export DO_NOT_TRACK=1
case "${1:-}" in
    create)
        name="$(field name)"
        [[ "$name" =~ ^[A-Za-z0-9._-]+$ ]] || {
            echo "worktree.sh: unexpected name '$name'" >&2
            exit 1
        }
        session="$(field session_id)"
        # The hook runs in the main checkout, whose HEAD may be anything; origin's default
        # branch is what a new task starts from.
        base="$(git rev-parse --abbrev-ref origin/HEAD 2>/dev/null || echo HEAD)"
        # A released worktree keeps its branch, which a worktree of the same name takes up again.
        create=("--create=$base")
        git show-ref --verify --quiet "refs/heads/claude/$name" && create=()
        exec "$aspect" worktree add "claude/$name" ${create[@]+"${create[@]}"} --output=path \
            --agent-kind=claude-code ${session:+"--agent-id=$session"}
        ;;
    remove)
        path="$(field worktree_path)"
        [[ -n "$path" ]] || {
            echo "worktree.sh: no worktree_path in the input" >&2
            exit 1
        }
        # From the main checkout, not from inside the worktree that goes away.
        cd "$(git -C "$path" rev-parse --path-format=absolute --git-common-dir)/.."
        session="$(field session_id)"
        exec "$aspect" worktree release "$path" \
            --agent-kind=claude-code ${session:+"--agent-id=$session"}
        ;;
    *)
        echo "usage: worktree.sh create|remove < hook-input.json" >&2
        exit 2
        ;;
esac
