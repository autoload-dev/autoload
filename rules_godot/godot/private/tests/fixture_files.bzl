"""Files with fixed content that tests and their fixtures declare in place of real inputs."""

load("@bazel_skylib//rules:write_file.bzl", "write_file")

def _fixture_file_impl(name, visibility, out, content):
    write_file(
        name = name,
        out = out,
        content = [content],
        tags = ["manual"],
        visibility = visibility,
    )

fixture_file = macro(
    doc = """
    Declare a file with fixed content, built only where a test or fixture names it.

    Without `content` it is a stand-in, such as a library, signing file or archive whose
    path analysis reads and that no action opens.
    """,
    implementation = _fixture_file_impl,
    attrs = {
        "out": attr.string(
            doc = "The file's path below the package.",
            mandatory = True,
            configurable = False,
        ),
        "content": attr.string(
            doc = "The file's text; a stand-in note by default.",
            default = "Analysis-only stand-in; never read or loaded.",
            configurable = False,
        ),
    },
)
