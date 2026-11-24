#!/usr/bin/env bash
# Set up a fresh clone: install the repository's two tools, then its hooks and Android SDK.
#
#   ./bootstrap.sh                     everything
#   ./bootstrap.sh --android=false     everything but the Android SDK packages
#   ./bootstrap.sh --tools-only        only Bazelisk and the Aspect CLI, as CI uses it
#
# Bazelisk (`bazel`) runs the Bazel of .bazelversion, and the Aspect CLI's launcher (`aspect`)
# the Aspect CLI of .aspect/version.axl; everything else comes through them. Both are placed
# in BIN_DIR (default ~/.local/bin), verified by the checksums of their GitHub releases; an
# installed copy that matches is kept. Other arguments go to `aspect bootstrap`, which installs
# the pre-push hook and the missing pinned Android SDK and NDK packages. Safe to repeat.
set -euo pipefail

BAZELISK_VERSION=1.29.0
ASPECT_VERSION=2026.47.12

# The release assets and their SHA-256 checksums per platform: Bazelisk's, then the launcher's.
assets() {
    case "$1" in
        Darwin-arm64)
            echo bazelisk-darwin-arm64 cee851f726789227d5561004e9904a52be45c3efb56f8b38b6993d6adbaa0409
            echo aspect-launcher-aarch64-apple-darwin d395dd7ccaeeb77bff93f56b92cfb579211478d35295f37af50da8614bdfe422
            ;;
        Linux-x86_64)
            echo bazelisk-linux-amd64 5a408715e932c0250d28bd84555f12edbf70117de42f9181691c736eacc4a992
            echo aspect-launcher-x86_64-unknown-linux-musl a49be533dc38314bbc9d578a9a7c537a5ec10d2a5e296ed5a909d43c4b68a237
            ;;
        Linux-aarch64 | Linux-arm64)
            echo bazelisk-linux-arm64 e20e8b0f4f240091b7a55bf17b9398bd4f40ee70ae0208dff95dd4c445fb4010
            echo aspect-launcher-aarch64-unknown-linux-musl 8d79895d8e3066c173324b7288d3839f842ceead766393ae559ed3e6d549d8b7
            ;;
        *) return 1 ;;
    esac
}

tools_only=false
arguments=()
for argument in "$@"; do
    case "$argument" in
        --tools-only) tools_only=true ;;
        -h | --help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) arguments+=("$argument") ;;
    esac
done

note() { printf 'bootstrap: %s\n' "$*" >&2; }
fail() { note "$*"; exit 1; }

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
        { rm -f "$download"; fail "could not download $url"; }
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
read -r launcher launcher_sha256 <<<"$(sed -n 2p <<<"$pins")"

BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
mkdir -p "$BIN_DIR"
check_host
install bazel "https://github.com/bazelbuild/bazelisk/releases/download/v$BAZELISK_VERSION/$bazelisk" "$bazelisk_sha256"
install aspect "https://github.com/aspect-build/aspect-cli/releases/download/v$ASPECT_VERSION/$launcher" "$launcher_sha256"

if [[ "$tools_only" == true ]]; then
    exit 0
fi
check_path bazel
check_path aspect
cd "$(dirname "${BASH_SOURCE[0]}")"
PATH="$BIN_DIR:$PATH" exec aspect bootstrap "${arguments[@]+"${arguments[@]}"}"
