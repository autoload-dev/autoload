"""Test which packages an SPDX document names, with their licenses."""

load("@rules_python//python:defs.bzl", "py_test")

def spdx_packages_test(name, spdx, packages, tags = [], **kwargs):
    """
    Test that an SPDX document names each package with its declared license.

    The document, such as a supply_chain_tools `spdx` target's, reads the package metadata of
    a target's graph from analysis and builds none of the target's outputs, so the test is
    tagged analysis_only.

    Args:
        name: Name of the test.
        spdx: The SPDX JSON document.
        packages: The declared SPDX license of each package, by its package URL without the
            version, such as `{"pkg:bazel/sqlite3": "blessing"}`.
        tags: Tags of the test besides analysis_only.
        **kwargs: Attributes of the py_test, such as size.
    """
    py_test(
        name = name,
        srcs = [Label(":inspect_spdx.py")],
        main = Label(":inspect_spdx.py"),
        # Bazel splits args as a shell does; a license expression has spaces.
        args = ["$(rootpath %s)" % spdx] + [
            "'%s=%s'" % (purl, packages[purl])
            for purl in sorted(packages)
        ],
        data = [spdx],
        tags = tags + ["analysis_only"],
        **kwargs
    )
