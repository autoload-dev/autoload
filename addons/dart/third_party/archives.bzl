"""The module's third-party archives, which MODULE.bazel fetches through `archives`."""

load(":archive.bzl", "archives_extension", "github_archive")

ARCHIVES = {
    # The Dart SDK's sources, which build the add-on's embedded runtime. Bazel loads the
    # runtime's source lists from .bzl copies of GN's *_sources.gni files. The patch drops
    # the embedder API's unused SecureSocket include, which needs BoringSSL, and corrects
    # the macOS version the runtime derives from Darwin 25 and newer, which it compares
    # with the deployment target before it starts an isolate.
    "dart_sdk_source": github_archive(
        owner = "dart-lang",
        repository = "sdk",
        version = "3.14.1",
        urls = [
            "https://github.com/dart-lang/sdk/archive/refs/tags/{version}.tar.gz",
        ],
        strip_prefix = "sdk-{version}",
        sha256 = "eb16c29569bc8ebe9e88add7387cbc2d7dcfb0e0edec855b8b758575c0a7c4cc",
        build_file = Label("//third_party:dart_sdk.BUILD.bazel"),
        patch_cmds = [
            "for f in $(find runtime -name '*_sources.gni'); do cp \"$f\" \"${f%.gni}.bzl\"; done",
        ],
        patch_strip = 1,
        patches = [Label("//third_party:dart_sdk.patch")],
    ),
}

archives = archives_extension(ARCHIVES)
