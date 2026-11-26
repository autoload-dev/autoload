#!/usr/bin/env bash
# Fail a push unless the checkout holds the pushed commits without other
# changes. The pre-push hook's checks (`aspect pre-push`) read the working tree,
# not the pushed commits. Reads Git's pre-push lines on stdin and prints the
# pushed branches' commits on the remote, which `aspect pre-push` counts the
# changes from, read from AUTOLOAD_REMOTE_TIPS (tools/ci/changes.py).
set -euo pipefail

fail() {
  echo "pre-push: $1" >&2
  exit 1
}

head_tree="$(git rev-parse 'HEAD^{tree}')"
tips=()
while read -r _local_ref local_sha remote_ref remote_sha; do
  [[ "$local_sha" =~ ^0+$ ]] && continue # branch deletion
  [[ "$remote_ref" == refs/heads/* ]] || continue # tags and other refs
  if [[ "$(git rev-parse "$local_sha^{tree}")" != "$head_tree" ]]; then
    fail "the checks run on the checkout; check out the pushed commit ${local_sha:0:12} first."
  fi
  tips+=("$remote_sha")
done
if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  fail "commit or stash local changes first; the checks would include them."
fi
echo "${tips[*]:-}"
