#!/usr/bin/env bash
# Builds the release archive and prints the release notes, called by bazel-contrib's
# release_ruleset workflow with the tag being released.
set -o errexit -o nounset -o pipefail

TAG=$1
# The prefix matches the one of GitHub's source archives, so strip_prefix stays the same
# for users who switch between a release archive and a source archive.
PREFIX="rules_godot-${TAG:1}"
ARCHIVE="rules_godot-$TAG.tar.gz"

# .gitattributes keeps development-only directories out of the archive.
git archive --format=tar --prefix="${PREFIX}/" "${TAG}" | gzip > "$ARCHIVE"

# The API documentation the registry renders: the curated Stardoc metadata of the public
# entrypoints (docs/internal/api-reference.md), not every starlark_doc_extract output.
# See https://github.com/bazelbuild/bazel-central-registry/blob/main/docs/stardoc.md
DOCS_TARGET=//docs/public/api:bcr_docs
bazel build "$DOCS_TARGET" >&2
BAZEL_BIN="$(bazel info bazel-bin 2>/dev/null)"
bazel cquery --output=files "$DOCS_TARGET" 2>/dev/null \
    | sed "s#^bazel-out/[^/]*/bin/##" \
    | tar --create --gzip --directory "$BAZEL_BIN" --file "${ARCHIVE%.tar.gz}.docs.tar.gz" --files-from -

cat << NOTES
## Bzlmod

Add to your \`MODULE.bazel\` file:

\`\`\`starlark
bazel_dep(name = "autoload_rules_godot", version = "${TAG:1}")

godot_engines = use_extension("@autoload_rules_godot//godot:extensions.bzl", "godot_engines")
godot_engines.prebuilt(name = "godot", version = "4.7.2")
use_repo(godot_engines, "godot")
register_toolchains("@godot//toolchains:all")
\`\`\`
NOTES
