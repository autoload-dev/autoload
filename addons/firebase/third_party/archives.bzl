"""The module's third-party archives, which MODULE.bazel fetches through `archives`."""

load(":archive.bzl", "archives_extension", "github_archive")

ARCHIVES = {
    # iOS: Firebase's official binary distribution, static XCFrameworks. No SwiftPM, so a
    # consuming root module needs no Swift package setup of its own.
    "firebase_ios": github_archive(
        owner = "firebase",
        repository = "firebase-ios-sdk",
        version = "13.2.0",
        urls = [
            "https://github.com/firebase/firebase-ios-sdk/releases/download/{version}/Firebase.zip",
        ],
        strip_prefix = "Firebase",
        sha256 = "528356de371830b3bbd0c32dbb649c080c8d36a6ef3d057590739eff6deaefcb",
        build_file = Label("//third_party:firebase_ios.BUILD.bazel"),
    ),
}

archives = archives_extension(ARCHIVES)
