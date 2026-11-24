#!/usr/bin/env bash
# Codex's session hooks (.codex/hooks.json), which lease a Bazel slot for a session in a Codex
# worktree (docs/internal/agent-setup.md, "Worktrees"): one output base per module, which
# tools/bazel uses while .bazel-slot names them.
#
#   worktree.sh session-start   reads the hook's {"cwd"} on stdin; leases a slot for its
#                               worktree, the warmest free one, else a new one
#   worktree.sh session-end     reads {"cwd"}; stops the worktree's Bazel servers and gives
#                               its slot back, which the next session leases again
#   worktree.sh setup|cleanup   the same for the worktree the current directory is in
#
# Only a linked worktree outside the Aspect CLI's worktree pool leases a slot. The leases live
# in ~/.aspect/bazel-slots/<repository>/, the output bases under Bazel's output user root, where
# `aspect gc` collects them; a lease whose worktree is gone counts as free. A hook
# never fails its session: without a slot, Bazel only starts cold.
set -euo pipefail

# The tools where bootstrap.sh placed them, beside the launcher `aspect bootstrap` recorded: an
# app's hooks may run with a short PATH.
launcher="$(git config aspect.launcher || true)"
[[ -z "$launcher" ]] || export PATH="${launcher%/*}:$PATH"

mode="${1:-}"
if [[ "$mode" == session-* ]]; then
    input="$(cat)"
    cwd="$(sed -n 's/.*"cwd"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' <<<"$input" | head -n 1)"
    worktree="$(git -C "${cwd:-.}" rev-parse --show-toplevel 2>/dev/null)" || exit 0
    # A main checkout's Git directory is its common one; a linked worktree's is not.
    [[ "$(git -C "$worktree" rev-parse --absolute-git-dir)" != \
        "$(git -C "$worktree" rev-parse --path-format=absolute --git-common-dir)" ]] || exit 0
    worktree="$(cd "$worktree" && pwd -P)"
    aspect_pool="$(cd ~/.aspect/worktrees 2>/dev/null && pwd -P || true)"
    [[ -z "$aspect_pool" || "$worktree" != "$aspect_pool"/* ]] || exit 0
    # Hand the work to the plain modes, and keep the session going whatever they do.
    script="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/$(basename "${BASH_SOURCE[0]}")"
    plain="${mode#session-}"
    plain="${plain/start/setup}"
    plain="${plain/end/cleanup}"
    (cd "$worktree" && "$script" "$plain" </dev/null >&2) || echo "worktree.sh: $plain failed" >&2
    exit 0
fi

worktree="$(git rev-parse --show-toplevel)"
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

# Bazel's output user root, where `aspect gc` and `aspect output-bases` find output bases.
output_user_root() {
    if [[ "$(uname -s)" == Darwin ]]; then
        echo "$HOME/Library/Caches/bazel/_bazel_$USER"
    else
        echo "${XDG_CACHE_HOME:-$HOME/.cache}/bazel/_bazel_$USER"
    fi
}

# 32 hexadecimal digits of a text's SHA-256, the length of Bazel's output base names.
hash32() {
    local sum
    if command -v sha256sum >/dev/null; then sum="$(printf '%s' "$1" | sha256sum)"
    else sum="$(printf '%s' "$1" | shasum -a 256)"; fi
    [[ "$sum" =~ ^[0-9a-f]{64} ]] || { note "cannot hash: no sha256sum or shasum"; exit 1; }
    echo "${sum:0:32}"
}

# A slot's output base for one module: named like Bazel's own, by a hash, under the output user
# root, so `aspect gc` keeps, idles out and removes it as it does every other.
output_base() {
    echo "$(output_user_root)/$(hash32 "bazel-slot:$1:$2")"
}

# Stop the Bazel servers of a slot's output bases, through the pid each server records; Bazel
# ends on the signal, and the next build in the slot must not meet it.
stop_servers() {
    local base pid_file pid
    [[ -f "$1/bases" ]] || return 0
    while read -r base; do
        pid_file="$base/server/server.pid.txt"
        [[ -f "$pid_file" ]] || continue
        pid="$(<"$pid_file")"
        kill "$pid" 2>/dev/null || continue
        for _ in {1..100}; do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
    done <"$1/bases"
}

# The slot a lease file names: the first line of .bazel-slot.
leased_slot() {
    sed -n '1s/^slot //p' .bazel-slot 2>/dev/null
}

setup() {
    if [[ -f .bazel-slot ]] && [[ "$(cat "$(leased_slot)/lease" 2>/dev/null)" == "$worktree" ]]; then
        note "already holds $(leased_slot)"
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
    # The slot, then each module of the worktree with its output base, which tools/bazel reads.
    local module
    {
        echo "slot $slot"
        git ls-files -- MODULE.bazel '*/MODULE.bazel' | while read -r module; do
            module="$(dirname "$module")"
            echo "$module $(output_base "$slot" "$module")"
        done
    } >.bazel-slot
    # Every output base the slot has had, whose servers a later lease stops.
    touch "$slot/bases"
    sed -n '2,$s/^[^ ]* //p' .bazel-slot | sort -u - "$slot/bases" >"$slot/bases.new"
    mv "$slot/bases.new" "$slot/bases"
    note "leased $slot"
}

cleanup() {
    [[ -f .bazel-slot ]] || { note "holds no Bazel slot"; return; }
    local slot
    slot="$(leased_slot)"
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
