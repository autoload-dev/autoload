#!/usr/bin/env bash
# The setup and cleanup scripts of Codex's worktrees (.codex/environments/environment.toml).
# Codex creates each worktree itself, at a new path, so its Bazel servers would start cold
# and leave their output bases behind. Instead, a worktree leases a Bazel slot: a directory
# that keeps one output base per module and passes from worktree to worktree, so a new one
# reuses the fetched repositories and the action cache of an earlier one. tools/bazel reads
# the lease from .bazel-slot.
#
#   worktree.sh setup     lease a slot for the worktree; the warmest free one, else a new one
#   worktree.sh cleanup   stop the worktree's Bazel servers and give its slot back
#
# The worktree is CODEX_WORKTREE_PATH, else the one the current directory is in. Slots live in
# ~/.aspect/bazel-slots/<repository>/, beside the Aspect CLI's worktree pool; a lease whose
# worktree is gone counts as free.
set -euo pipefail

# The pinned Bazelisk where bootstrap.sh places it: an app's scripts may run with a short PATH.
export PATH="$HOME/.local/bin:$PATH"

worktree="${CODEX_WORKTREE_PATH:-$(git rev-parse --show-toplevel)}"
worktree="$(cd "$worktree" && pwd -P)"
cd "$worktree"

note() { printf 'worktree.sh: %s\n' "$*" >&2; }

# The repository as its origin names it, such as github.com/autoload-dev/autoload.
repository() {
    local origin
    origin="$(git remote get-url origin)"
    origin="${origin%.git}"
    origin="${origin#*://}"
    origin="${origin#*@}"
    echo "${origin/://}"
}

pool="$HOME/.aspect/bazel-slots/$(repository)"
mkdir -p "$pool"

# Hold the pool's lock until the script exits; a lock older than a minute was abandoned.
lock() {
    local tries=0
    until mkdir "$pool/.lock" 2>/dev/null; do
        if [[ -n "$(find "$pool/.lock" -maxdepth 0 -mmin +1 2>/dev/null)" ]]; then
            rmdir "$pool/.lock" 2>/dev/null || true
        fi
        ((tries++ < 300)) || { note "the slot pool stays locked: $pool/.lock"; exit 1; }
        sleep 0.1
    done
    trap 'rmdir "$pool/.lock" 2>/dev/null || true' EXIT
}

# Whether a slot is free: no lease, or a lease for a worktree that no longer exists.
free() {
    local holder
    [[ -f "$1/lease" ]] || return 0
    holder="$(<"$1/lease")"
    [[ "$holder" != "$worktree" ]] && ! git -C "$holder" rev-parse --git-dir >/dev/null 2>&1
}

# Stop the Bazel servers whose output bases are in a slot, through the pid each server records;
# Bazel ends on the signal, and the next build in the slot must not meet it.
stop_servers() {
    local pid_file pid
    for pid_file in "$1"/*/server/server.pid.txt; do
        [[ -f "$pid_file" ]] || continue
        pid="$(<"$pid_file")"
        kill "$pid" 2>/dev/null || continue
        for _ in {1..100}; do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
    done
}

setup() {
    if [[ -f .bazel-slot ]] && [[ "$(cat "$(<.bazel-slot)/lease" 2>/dev/null)" == "$worktree" ]]; then
        note "already holds $(<.bazel-slot)"
        return
    fi
    lock
    local slot="" candidate
    # The most recently used free slot holds the newest Bazel state.
    while read -r candidate; do
        [[ -n "$candidate" ]] && free "$candidate" && { slot="$candidate"; break; }
    done < <(ls -1dt "$pool"/slot-* 2>/dev/null)
    if [[ -z "$slot" ]]; then
        local index=1
        while [[ -e "$pool/slot-$index" ]]; do ((index++)); done
        slot="$pool/slot-$index"
        mkdir -p "$slot"
    else
        stop_servers "$slot"
    fi
    echo "$worktree" >"$slot/lease"
    touch "$slot"
    echo "$slot" >.bazel-slot
    note "leased $slot"
}

cleanup() {
    [[ -f .bazel-slot ]] || { note "holds no Bazel slot"; return; }
    local slot
    slot="$(<.bazel-slot)"
    stop_servers "$slot"
    lock
    if [[ "$(cat "$slot/lease" 2>/dev/null)" == "$worktree" ]]; then
        rm -f "$slot/lease"
        touch "$slot"
    fi
    rm -f .bazel-slot
    note "gave back $slot"
}

case "${1:-}" in
    setup) setup ;;
    cleanup) cleanup ;;
    *) echo "usage: worktree.sh setup|cleanup" >&2; exit 2 ;;
esac
