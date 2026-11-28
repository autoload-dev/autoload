"""
The third-party archives a module brings, each declared once by its version.

Shared file of the add-on modules with third-party archives (tools/addons/new.py): the
module's `third_party/archives.bzl` declares its archives with `github_archive` and exports
the extension that fetches them, and each archive's build file builds its package metadata
from the same declaration, so the archive's URLs and its package URL carry one version.
"""

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")
load("@package_metadata//purl:purl.bzl", "purl")

# What stands for the archive's version in its URLs and strip_prefix.
_VERSION = "{version}"

def github_archive(*, owner, repository, version, urls, strip_prefix = "", **attrs):
    """
    The archive of a GitHub project at one version.

    Args:
        owner: The project's owner on GitHub, such as firebase.
        repository: The project's repository, such as firebase-ios-sdk.
        version: The release tag or commit the archive holds.
        urls: Its download URLs, where `{version}` stands for version; each one names it.
        strip_prefix: Its top-level directory, where `{version}` stands for version.
        **attrs: The other attributes of its http_archive, such as sha256 and build_file.

    Returns:
        A struct with the archive's version, its package URL `purl` and the `attrs` of
        its http_archive.
    """
    unversioned = [url for url in urls if _VERSION not in url]
    if unversioned:
        fail("%s/%s: the URL %s does not name {version}" % (owner, repository, unversioned[0]))
    return struct(
        version = version,
        purl = purl.builder().type("github").namespace(owner).name(repository).version(version).build(),
        attrs = attrs | {
            "urls": [url.replace(_VERSION, version) for url in urls],
            "strip_prefix": strip_prefix.replace(_VERSION, version),
        },
    )

def archives_extension(archives):
    """
    The module extension that fetches the archives.

    Args:
        archives: The archives, `github_archive` structs by their repositories' names.

    Returns:
        A module extension, which the module's `third_party/archives.bzl` exports.
    """

    def _fetch(module_ctx):
        for name, archive in archives.items():
            http_archive(name = name, **archive.attrs)

        # Every archive is pinned by its digest.
        return module_ctx.extension_metadata(reproducible = True)

    return module_extension(
        doc = "Fetches the module's third-party archives.",
        implementation = _fetch,
    )
