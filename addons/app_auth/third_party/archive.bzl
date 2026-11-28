"""
Declare a module's third-party archives, each with its version once.

Shared file of the add-on modules with third-party archives (tools/addons/new.py). The
module's `third_party/archives.bzl` declares its archives with `github_archive` and exports
the extension that fetches them. Each archive's build file takes its package URL from the
same declaration, so its URLs and its package URL carry one version.
"""

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")
load("@package_metadata//purl:purl.bzl", "purl")

# What stands for the archive's version in its URLs and strip_prefix.
_VERSION = "{version}"

def github_archive(*, owner, repository, version, urls, strip_prefix = "", **attrs):
    """
    Declare the archive of a GitHub project at one version.

    Args:
        owner: The project's owner on GitHub, such as firebase.
        repository: The project's repository, such as firebase-ios-sdk.
        version: The release tag or commit the archive holds.
        urls: The download URLs. Each must contain `{version}`, which version replaces.
        strip_prefix: The archive's top-level directory; version replaces `{version}`.
        **attrs: The other attributes of its http_archive, such as build_file, with its
            sha256 or integrity, which pins it.

    Returns:
        A struct with the archive's version, its package URL `purl` and the `attrs` of
        its http_archive.
    """
    project = owner + "/" + repository
    if not version:
        fail("%s: the archive declares no version" % project)
    unversioned = [url for url in urls if _VERSION not in url]
    if unversioned:
        fail("%s: the URL %s does not name {version}" % (project, unversioned[0]))
    if "sha256" not in attrs and "integrity" not in attrs:
        fail("%s: the archive declares no sha256 or integrity" % project)
    return struct(
        version = version,
        purl = (
            purl.builder()
                .type("github")
                .namespace(owner)
                .name(repository)
                .version(version)
                .build()
        ),
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

        # github_archive requires a digest of every archive.
        return module_ctx.extension_metadata(reproducible = True)

    return module_extension(
        doc = "Fetches the module's third-party archives.",
        implementation = _fetch,
    )
