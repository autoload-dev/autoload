"""The module's third-party archives, which MODULE.bazel fetches through `archives`."""

load(":archive.bzl", "archives_extension", "github_archive")

ARCHIVES = {
    # AppAuth for iOS and macOS, built from its release's Objective-C sources; only Apple
    # builds fetch it.
    "appauth": github_archive(
        owner = "openid",
        repository = "AppAuth-iOS",
        version = "3.0.0",
        urls = [
            "https://github.com/openid/AppAuth-iOS/archive/refs/tags/{version}.tar.gz",
        ],
        strip_prefix = "AppAuth-iOS-{version}",
        sha256 = "908fc7ff2b7dd26e65e0e9ef6603e313de28855b4dc3071543f04238255f6df9",
        build_file = Label("//third_party:appauth.BUILD.bazel"),
    ),
}

archives = archives_extension(ARCHIVES)
