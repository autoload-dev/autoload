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

def _is_base64(text):
    """Whether text is non-empty and holds base64 digits only, without padding."""
    return bool(text) and not [character for character in text.elems() if character not in _BASE64]

def _checksum(sha256, integrity):
    """
    The package URL checksum of a SHA-256 or Subresource Integrity digest, or empty.

    Empty for none, and for an integrity that is not one base64 digest.
    """
    if sha256:
        return "sha256:" + sha256
    algorithm, _, digest = integrity.partition("-")
    if not algorithm or not _is_base64(digest.rstrip("=")):
        return ""
    return "%s:%s" % (algorithm, _base64_hex(digest))

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

# The label of the metadata, for a package of a repository that only some packages carry.
PACKAGE_METADATA = "//%s:package_metadata" % _PACKAGE

def write_package_metadata(repository_ctx, package_url, license_text = None, repository_wide = True):
    """
    Declare the package metadata of MIT-licensed software in a repository.

    Writes the package `_package_metadata`, which holds the metadata and a copy of the
    license text as LICENSE, and REPO.bazel, which no repository of the ruleset writes
    otherwise and which gives every target of the repository the metadata.

    Args:
        repository_ctx: Repository rule context.
        package_url: The software's package URL, such as source_purl's.
        license_text: Path of the software's license text, or None; a missing file leaves
            the license without text.
        repository_wide: Whether REPO.bazel gives the metadata to every target; otherwise
            the packages that hold the software name PACKAGE_METADATA themselves.
    """
    if repository_wide:
        repository_ctx.file(
            "REPO.bazel",
            "repo(default_package_metadata = [%r])\n" % PACKAGE_METADATA,
            executable = False,
        )
    if license_text and not repository_ctx.path(license_text).exists:
        license_text = None
    if license_text:
        repository_ctx.file(
            _PACKAGE + "/LICENSE",
            repository_ctx.read(license_text),
            executable = False,
        )
    repository_ctx.file(_PACKAGE + "/BUILD.bazel", _BUILD.format(
        license_bzl = repr(str(Label("@package_metadata//licenses/rules:license.bzl"))),
        package_metadata_bzl = repr(str(Label("@package_metadata//rules:package_metadata.bzl"))),
        purl = repr(package_url),
        kind = repr(str(Label("@package_metadata//licenses/spdx:MIT"))),
        text = '    text = "LICENSE",\n' if license_text else "",
    ), executable = False)
