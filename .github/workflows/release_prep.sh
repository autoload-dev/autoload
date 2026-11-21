#!/usr/bin/env bash
# Builds the release archive of the module a tag `<module>-v<version>` releases and prints
# the release notes, called by bazel-contrib's release_ruleset workflow with the tag.
set -o errexit -o nounset -o pipefail

TAG=$1
MODULE="$("$(dirname "$0")/release_module.sh" "$TAG")"
field() { sed -n "s/^$1=//p" <<< "$MODULE"; }
NAME="$(field name)"
VERSION="$(field version)"
ROOT="$(field root)"
PREFIX="${NAME}-${VERSION}"
ARCHIVE="${PREFIX}.tar.gz"

# The archive holds the module's directory at its root. .gitattributes files keep
# development-only directories out of it; a module below the root takes the repository's
# license along.
if [ "$ROOT" = . ]; then
    git archive --format=tar --prefix="${PREFIX}/" "${TAG}" | gzip > "$ARCHIVE"
else
    git archive --format=tar --prefix="${PREFIX}/" --add-file=LICENSE "${TAG}:${ROOT}" \
        | gzip > "$ARCHIVE"
fi

if [ "$NAME" = autoload_rules_godot ]; then
    # The API documentation the registry renders: the curated Stardoc metadata of the public
    # entrypoints (docs/internal/api-reference.md), not every starlark_doc_extract output.
    # See https://github.com/bazelbuild/bazel-central-registry/blob/main/docs/stardoc.md
    DOCS_TARGET=//docs/public/api:bcr_docs
    bazel build "$DOCS_TARGET" >&2
    BAZEL_BIN="$(bazel info bazel-bin 2>/dev/null)"
    bazel cquery --output=files "$DOCS_TARGET" 2>/dev/null \
        | sed "s#^bazel-out/[^/]*/bin/##" \
        | tar --create --gzip --directory "$BAZEL_BIN" --file "${PREFIX}.docs.tar.gz" --files-from -
fi

SETUP=""
if [ "$NAME" = autoload_rules_godot ]; then
    SETUP='
godot_engines = use_extension("@autoload_rules_godot//godot:extensions.bzl", "godot_engines")
godot_engines.prebuilt(name = "godot", version = "4.7.2")
use_repo(godot_engines, "godot")
register_toolchains("@godot//toolchains:all")'
fi

cat << NOTES
## Bzlmod

Add to your \`MODULE.bazel\` file:

\`\`\`starlark
bazel_dep(name = "${NAME}", version = "${VERSION}")${SETUP}
\`\`\`

See the module's README for its setup:
https://github.com/${GITHUB_REPOSITORY:-autoload-dev/rules_godot}/blob/${TAG}/${ROOT}/README.md
NOTES
