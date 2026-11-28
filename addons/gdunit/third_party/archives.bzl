"""The module's third-party archives, which MODULE.bazel fetches through `archives`."""

load(":archive.bzl", "archives_extension", "github_archive")

ARCHIVES = {
    # GdUnit4 at a commit of its main branch; its add-on directory becomes //gdunit.
    "gdunit4": github_archive(
        owner = "godot-gdunit-labs",
        repository = "gdUnit4",
        version = "0127a55f4543dfc24746f6e5c7ba6f94105d51f2",
        urls = ["https://github.com/godot-gdunit-labs/gdUnit4/archive/{version}.tar.gz"],
        strip_prefix = "gdUnit4-{version}",
        sha256 = "3b112b67f7cb85e59f3814ea81473e64b9ddfad351073ce89d496da749a6d1fe",
        build_file = Label("//third_party:gdunit4.BUILD.bazel"),
    ),
}

archives = archives_extension(ARCHIVES)
