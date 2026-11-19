#!/usr/bin/env bash
# Build metadata BuildBuddy shows for an invocation under --config=buildbuddy: the
# repository, commit, branch and whether the checkout has uncommitted changes. Keys
# without the STABLE_ prefix are volatile, so they never invalidate a cached action.
set -euo pipefail

if ! git rev-parse --git-dir >/dev/null 2>&1; then
    exit 0
fi
# Credentials embedded in the remote URL stay out of the metadata.
repo_url="$(git config --get remote.origin.url | sed -E 's#^([a-z+]+://)[^@/]*@#\1#' || true)"
echo "REPO_URL ${repo_url}"
echo "COMMIT_SHA $(git rev-parse HEAD)"
echo "GIT_BRANCH $(git branch --show-current)"
if git diff-index --quiet HEAD --; then
    echo "GIT_TREE_STATUS Clean"
else
    echo "GIT_TREE_STATUS Modified"
fi
