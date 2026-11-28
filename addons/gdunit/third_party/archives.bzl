"""The module's third-party archives, which MODULE.bazel fetches through `archives`."""

load(":archive.bzl", "archives_extension", "github_archive")

ARCHIVES = {
    # GdUnit4's release; its add-on directory becomes //gdunit.
    "gdunit4": github_archive(
        owner = "godot-gdunit-labs",
        repository = "gdUnit4",
        version = "6.2.2",
        urls = [
            "https://github.com/godot-gdunit-labs/gdUnit4/archive/refs/tags/v{version}.tar.gz",
        ],
        strip_prefix = "gdUnit4-{version}",
        sha256 = "53ba53c23328d8f30205acc2f7ffe3d663773847d09b8f48edab1df6a5950571",
        build_file = Label("//third_party:gdunit4.BUILD.bazel"),
    ),
}

archives = archives_extension(ARCHIVES)
