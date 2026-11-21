#!/usr/bin/env bash
# Prints the module a release tag `<module>-v<version>` releases, one `key=value` per line:
# name, version, root (its directory), bcr (whether it is published to the Bazel Central
# Registry) and test (its release test command), from release_modules.json.
set -o errexit -o nounset -o pipefail

TAG=$1
TABLE="$(dirname "$0")/release_modules.json"

if [[ ! "$TAG" =~ ^([a-z][a-z0-9_]*)-v([0-9]+\.[0-9]+\.[0-9]+.*)$ ]]; then
    echo "Release tags are named <module>-v<version>, not $TAG" >&2
    exit 1
fi
NAME=${BASH_REMATCH[1]}
VERSION=${BASH_REMATCH[2]}
if ! jq --exit-status --arg name "$NAME" 'has($name)' "$TABLE" > /dev/null; then
    echo "$NAME is not a module of $TABLE" >&2
    exit 1
fi

echo "name=$NAME"
echo "version=$VERSION"
jq --raw-output --arg name "$NAME" '.[$name] | "root=\(.root)\nbcr=\(.bcr)\ntest=\(.test)"' "$TABLE"
