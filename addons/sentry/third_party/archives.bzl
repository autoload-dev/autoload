"""The module's third-party archives, which MODULE.bazel fetches through `archives`."""

load(":archive.bzl", "archives_extension", "github_archive")

ARCHIVES = {
    # Sentry for Godot's release: its prebuilt GDExtension libraries, Godot Android
    # plugin, iOS frameworks and GDScript user-feedback UI.
    "sentry_godot": github_archive(
        owner = "getsentry",
        repository = "sentry-godot",
        version = "2.5.1",
        urls = [
            "https://github.com/getsentry/sentry-godot/releases/download/{version}/sentry-godot-{version}%2Bd30e663.zip",
        ],
        strip_prefix = "addons/sentry",
        sha256 = "b639df4d50c4f00f6e57f26fc126640fa4a29a74050970cbfc0ecc85e5d0b460",
        build_file = Label("//third_party:sentry_godot.BUILD.bazel"),
    ),
}

archives = archives_extension(ARCHIVES)
