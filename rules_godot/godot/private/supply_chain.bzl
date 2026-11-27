"""
Package metadata of the repositories the ruleset's repository rules create.

SBOM and license tools read a target's package metadata (bazel-contrib/supply-chain): a
repository that writes it in REPO.bazel gives it to every one of its targets, wherever they
end up, such as a runtime in an exported application.
"""

load("@package_metadata//purl:purl.bzl", "purl")

visibility("//godot/...")

_LICENSE_BZL = str(Label("@package_metadata//licenses/rules:license.bzl"))
_PACKAGE_METADATA_BZL = str(Label("@package_metadata//rules:package_metadata.bzl"))
_MIT = str(Label("@package_metadata//licenses/spdx:MIT"))

# The package that holds the metadata, apart from the packages the repository generates.
_PACKAGE = "_package_metadata"

_BASE64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_HEX = "0123456789abcdef"

def _base64_hex(text):
    """The hexadecimal digits of base64-encoded bytes."""
    bits = 0
    count = 0
    digits = []
    for character in text.rstrip("=").elems():
        bits = (bits << 6) | _BASE64.index(character)
        count += 6
        if count >= 8:
            count -= 8
            byte = (bits >> count) & 0xff
            digits.append(_HEX[byte >> 4] + _HEX[byte & 0xf])
    return "".join(digits)

def integrity_checksum(integrity):
    """
    The package URL checksum of a Subresource Integrity digest.

    Args:
        integrity: A digest such as `sha512-<base64>`.

    Returns:
        The checksum, such as `sha512:<hexadecimal>`.
    """
    algorithm, _, digest = integrity.partition("-")
    return "%s:%s" % (algorithm, _base64_hex(digest))

def source_purl(name, version = "", checksum = ""):
    """
    The package URL of software the ruleset downloads by digest, such as a Godot archive.

    The digest identifies it, so that an upstream release and a fork of the same version
    differ.

    Args:
        name: The package's name, such as godot or godot-cpp.
        version: Its version, such as 4.7.2; empty where none is known.
        checksum: Its digest as a package URL checksum, such as `sha256:<hexadecimal>`.

    Returns:
        A generic package URL.
    """
    builder = purl.builder().type("generic").name(name)
    if version:
        builder.version(version)
    if checksum:
        builder.add_qualifier("checksum", checksum)
    return builder.build()

def write_package_metadata(repository_ctx, package_url, license_text = None):
    """
    Give every target of a repository the package metadata of MIT-licensed software.

    Writes REPO.bazel, which no repository of the ruleset writes otherwise, and the package
    `_package_metadata`, which holds the metadata and a copy of the license text.

    Args:
        repository_ctx: Repository rule context.
        package_url: The software's package URL, such as source_purl's.
        license_text: Path of the software's license text, a string or a path, or None.
    """
    repository_ctx.file(
        "REPO.bazel",
        'repo(default_package_metadata = ["//%s:package_metadata"])\n' % _PACKAGE,
        executable = False,
    )
    text = ""
    if license_text:
        name = str(license_text).rpartition("/")[2]
        repository_ctx.file("%s/%s" % (_PACKAGE, name), repository_ctx.read(license_text), executable = False)
        text = "    text = %r,\n" % name
    repository_ctx.file("%s/BUILD.bazel" % _PACKAGE, """\
load({license_bzl}, "license")
load({package_metadata_bzl}, "package_metadata")

package_metadata(
    name = "package_metadata",
    attributes = [":license"],
    purl = {purl},
    visibility = ["//visibility:public"],
)

license(
    name = "license",
    kind = {kind},
{text})
""".format(
        license_bzl = repr(_LICENSE_BZL),
        package_metadata_bzl = repr(_PACKAGE_METADATA_BZL),
        purl = repr(package_url),
        kind = repr(_MIT),
        text = text,
    ), executable = False)
