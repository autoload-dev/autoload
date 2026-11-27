#!/usr/bin/env bash
# Builds the release archive of the module a tag `<module>-v<version>` releases and prints
# the release notes, called by bazel-contrib's release_ruleset workflow with the tag.
set -o errexit -o nounset -o pipefail

TAG=$1
MODULE="$(cd "$(dirname "$0")/../.." && python3 -m tools.ci.release_module "$TAG")"
field() { sed -n "s/^$1=//p" <<< "$MODULE"; }
NAME="$(field name)"
VERSION="$(field version)"
ROOT="$(field root)"
PREFIX="${NAME}-${VERSION}"
REPOSITORY="${GITHUB_REPOSITORY:-autoload-dev/autoload}"
ARCHIVE="${PREFIX}.tar.gz"

# The archive holds the module's directory at its root and the repository's license. The
# module's .gitattributes keeps development-only directories out of it.
git archive --format=tar --prefix="${PREFIX}/" --add-file=LICENSE "${TAG}:${ROOT}" \
    | gzip > "$ARCHIVE"

# The ruleset's API documentation and the setup its release notes show.
SETUP=""
if [ "$NAME" = autoload_rules_godot ]; then
    # The API documentation the registry renders: the Stardoc metadata of the public
    # entrypoints (rules_godot/BUILD.bazel).
    # See https://github.com/bazelbuild/bazel-central-registry/blob/main/docs/stardoc.md
    DOCS_TARGET=//:bcr_docs
    # The ruleset's own module builds it; the release files stay at the root.
    OUTPUT="$PWD"
    pushd "$(dirname "$0")/../../rules_godot" > /dev/null
    bazel build "$DOCS_TARGET" >&2
    BAZEL_BIN="$(bazel info bazel-bin 2>/dev/null)"
    bazel cquery --output=files "$DOCS_TARGET" 2>/dev/null \
        | sed "s#^bazel-out/[^/]*/bin/##" \
        | tar --create --gzip --directory "$BAZEL_BIN" --file "${OUTPUT}/${PREFIX}.docs.tar.gz" \
            --files-from -
    popd > /dev/null
    SETUP='
godot_engines = use_extension("@autoload_rules_godot//godot:extensions.bzl", "godot_engines")
godot_engines.engine(name = "godot", default = True, version = "4.7.2")
'
fi
# A module that is not on the Bazel Central Registry resolves from this release's archive.
if [ "$(field bcr)" != true ]; then
    INTEGRITY="sha256-$(openssl dgst -sha256 -binary "$ARCHIVE" | openssl base64 -A)"
    SETUP="${SETUP}
archive_override(
    module_name = \"${NAME}\",
    integrity = \"${INTEGRITY}\",
    strip_prefix = \"${PREFIX}\",
    urls = [\"https://github.com/${REPOSITORY}/releases/download/${TAG}/${ARCHIVE}\"],
)"
fi

cat << NOTES
## Bzlmod

Add to your \`MODULE.bazel\` file:

\`\`\`starlark
bazel_dep(name = "${NAME}", version = "${VERSION}")${SETUP}
\`\`\`

See the module's README for its setup:
https://github.com/${REPOSITORY}/blob/${TAG}/${ROOT}/README.md
NOTES
