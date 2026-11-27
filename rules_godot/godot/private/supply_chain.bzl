"""
Package metadata of the repositories the ruleset's repository rules create.

SBOM and license tools read a target's package metadata (bazel-contrib/supply-chain): a
repository that writes it in REPO.bazel gives it to every one of its targets, wherever they
end up, such as a runtime in an exported application.

Sections: Package URLs, Repository metadata.
"""

load("@package_metadata//purl:purl.bzl", "purl")

visibility("//godot/...")

# ==== Package URLs ============================================================

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

def _checksum(sha256, integrity):
    """The package URL checksum of a SHA-256 digest or a Subresource Integrity digest."""
    if sha256:
        return "sha256:" + sha256
    if integrity:
        algorithm, _, digest = integrity.partition("-")
        return "%s:%s" % (algorithm, _base64_hex(digest))
    return ""

def source_purl(name, version = "", sha256 = "", integrity = ""):
    """
    The package URL of software the ruleset downloads by digest, such as a Godot archive.

    The digest identifies it as the package URL's checksum, so that an upstream release
    and a fork of the same version differ.

    Args:
        name: The package's name, such as godot or godot-cpp.
        version: Its version, such as 4.7.2; empty where none is known.
        sha256: The hexadecimal SHA-256 digest of its archive, or empty.
        integrity: The Subresource Integrity digest of its archive, such as `sha512-<base64>`,
            where it has no sha256; or empty.

    Returns:
        A generic package URL.
    """
    builder = purl.builder().type("generic").name(name)
    if version:
        builder.version(version)
    checksum = _checksum(sha256, integrity)
    if checksum:
        builder.add_qualifier("checksum", checksum)
    return builder.build()

# ==== Repository metadata =====================================================

# The package that holds the metadata, apart from the packages the repository generates.
_PACKAGE = "_package_metadata"

_BUILD = """\
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
"""

def write_package_metadata(repository_ctx, package_url, license_text = None):
    """
    Give every target of a repository the package metadata of MIT-licensed software.

    Writes REPO.bazel, which no repository of the ruleset writes otherwise, and the package
    `_package_metadata`, which holds the metadata and a copy of the license text as LICENSE.

    Args:
        repository_ctx: Repository rule context.
        package_url: The software's package URL, such as source_purl's.
        license_text: Path of the software's license text, or None.
    """
    repository_ctx.file(
        "REPO.bazel",
        'repo(default_package_metadata = ["//%s:package_metadata"])\n' % _PACKAGE,
        executable = False,
    )
    if license_text:
        repository_ctx.file(_PACKAGE + "/LICENSE", repository_ctx.read(license_text), executable = False)
    repository_ctx.file(_PACKAGE + "/BUILD.bazel", _BUILD.format(
        license_bzl = repr(str(Label("@package_metadata//licenses/rules:license.bzl"))),
        package_metadata_bzl = repr(str(Label("@package_metadata//rules:package_metadata.bzl"))),
        purl = repr(package_url),
        kind = repr(str(Label("@package_metadata//licenses/spdx:MIT"))),
        text = '    text = "LICENSE",\n' if license_text else "",
    ), executable = False)
