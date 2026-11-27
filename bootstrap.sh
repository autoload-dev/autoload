#!/usr/bin/env bash
# Set up a fresh clone: install the repository's two tools, then its hooks and Android SDK.
#
#   ./bootstrap.sh                     everything
#   ./bootstrap.sh --android=false     everything but the Android SDK packages
#   ./bootstrap.sh --tools-only        only Bazelisk and the Aspect CLI, as CI uses it
#
# Bazelisk (`bazel`) runs the Bazel of .bazelversion, and the Aspect CLI's launcher (`aspect`),
# of the release .aspect/version.axl names, its Aspect CLI; everything else comes through them.
# Both are placed in BIN_DIR (default ~/.local/bin), verified by the checksums of their GitHub
# releases; an installed copy that matches is kept. Other arguments go to `aspect bootstrap`,
# which installs the pre-commit and pre-push hooks and the missing pinned Android SDK and NDK
# packages, then runs `aspect doctor` to name what the setup still lacks. Safe to repeat.
set -euo pipefail

BAZELISK_VERSION=1.29.0

# Each platform's Bazelisk asset with its SHA-256 checksum, then its Aspect launcher asset.
assets() {
    case "$1" in
        Darwin-arm64)
            echo bazelisk-darwin-arm64 cee851f726789227d5561004e9904a52be45c3efb56f8b38b6993d6adbaa0409
            echo aspect-launcher-aarch64-apple-darwin
            ;;
        Linux-x86_64)
            echo bazelisk-linux-amd64 5a408715e932c0250d28bd84555f12edbf70117de42f9181691c736eacc4a992
            echo aspect-launcher-x86_64-unknown-linux-musl
            ;;
        Linux-aarch64 | Linux-arm64)
            echo bazelisk-linux-arm64 e20e8b0f4f240091b7a55bf17b9398bd4f40ee70ae0208dff95dd4c445fb4010
            echo aspect-launcher-aarch64-unknown-linux-musl
            ;;
        *) return 1 ;;
    esac
}

tools_only=false
arguments=()
for argument in "$@"; do
    case "$argument" in
        --tools-only) tools_only=true ;;
        -h | --help)
            awk 'NR > 1 && !/^#/ { exit } NR > 1 { sub(/^# ?/, ""); print }' "$0"
            exit 0
            ;;
        *) arguments+=("$argument") ;;
    esac
done

note() { printf 'bootstrap: %s\n' "$*" >&2; }
fail() {
    note "$*"
    exit 1
}

sha256() {
    if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1
}

# Place one pinned binary as BIN_DIR/<name>, unless a verified copy is already there.
install() {
    local name="$1" url="$2" checksum="$3" target="$BIN_DIR/$1"
    if [[ -x "$target" && "$(sha256 "$target")" == "$checksum" ]]; then
        note "$name: $target is the pinned version"
        return
    fi
    local download
    download="$(mktemp "$BIN_DIR/.$name.XXXXXX")"
    curl -fsSL --retry 3 --connect-timeout 10 --max-time 300 -o "$download" "$url" ||
        {
            rm -f "$download"
            fail "could not download $url"
        }
    if [[ "$(sha256 "$download")" != "$checksum" ]]; then
        rm -f "$download"
        fail "$url does not match its pinned checksum"
    fi
    chmod +x "$download"
    mv -f "$download" "$target"
    note "$name: installed $target"
}

# Whether `name` on PATH is the copy in BIN_DIR; warn about what a shell would run instead.
check_path() {
    local name="$1" found
    found="$(command -v "$name" || true)"
    if [[ -z "$found" ]]; then
        note "$BIN_DIR is not on PATH: add it to your shell's PATH to run \`$name\`"
    elif [[ "$found" != "$BIN_DIR/$name" ]]; then
        note "\`$name\` runs $found, which comes before $BIN_DIR on PATH"
    fi
}

# What Bazel cannot provide: Git, curl and a C/C++ compiler of the host.
check_host() {
    command -v git >/dev/null || fail "Git is missing"
    command -v curl >/dev/null || fail "curl is missing"
    if [[ "$(uname -s)" == Darwin ]]; then
        xcode-select -p >/dev/null 2>&1 ||
            note "no Xcode or Command Line Tools: install them with \`xcode-select --install\`"
    elif ! command -v cc >/dev/null; then
        note "no C/C++ compiler: install clang or gcc with the system's package manager"
    fi
}

platform="$(uname -s)-$(uname -m)"
pins="$(assets "$platform")" || fail "no pinned tools for $platform"
read -r bazelisk bazelisk_sha256 <<<"$(sed -n 1p <<<"$pins")"
launcher="$(sed -n 2p <<<"$pins")"

# The Aspect CLI's one pin is .aspect/version.axl; the launcher comes from the same release,
# verified by the checksum the release publishes beside it.
cd "$(dirname "${BASH_SOURCE[0]}")"
aspect_version="$(sed -n 's/^version("\([^"]*\)").*/\1/p' .aspect/version.axl)"
[[ -n "$aspect_version" ]] || fail "no version(\"...\") in .aspect/version.axl"
aspect_release="https://github.com/aspect-build/aspect-cli/releases/download/v$aspect_version"
launcher_sha256="$(curl -fsSL --retry 3 "$aspect_release/$launcher.sha256" | cut -d' ' -f1)" ||
    fail "could not read the launcher's checksum from $aspect_release"

BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
mkdir -p "$BIN_DIR"
check_host
install bazel "https://github.com/bazelbuild/bazelisk/releases/download/v$BAZELISK_VERSION/$bazelisk" "$bazelisk_sha256"
install aspect "$aspect_release/$launcher" "$launcher_sha256"

if [[ "$tools_only" == true ]]; then
    exit 0
fi
check_path bazel
check_path aspect
# The hooks `aspect bootstrap` installs run this launcher by its path.
export AUTOLOAD_ASPECT_LAUNCHER="$BIN_DIR/aspect"
PATH="$BIN_DIR:$PATH" exec aspect bootstrap "${arguments[@]+"${arguments[@]}"}"
