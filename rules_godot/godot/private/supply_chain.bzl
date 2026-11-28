"""
Package metadata of the repositories the ruleset's repository rules create.

SBOM and license tools read a target's package metadata (bazel-contrib/supply-chain): a
repository that writes it in REPO.bazel gives it to every one of its targets, wherever they
end up, such as a runtime in an exported application.

Sections: Package URLs, Repository metadata.
"""

load("@package_metadata//purl:purl.bzl", "purl")
load(":copyright.bzl", "bundled_libraries", "words_of")

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

# SBOM tools give each target of a build graph one package, the first of its package
# metadata, so each bundled library has a target of its own that carries its metadata, and
# the targets that hold the software depend on them through BUNDLED_PACKAGES. The targets
# carry no files. The package's own targets carry no metadata.
_HEADER = """\
load({license_bzl}, "license")
load({license_kind_bzl}, "license_kind")
load({package_metadata_bzl}, "package_metadata")

package(default_package_metadata = [])

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

filegroup(
    name = "bundled_packages",
    srcs = {packages},
    visibility = ["//visibility:public"],
)
"""

# A bundled library: the target that carries its package metadata, the metadata and its
# license, whose text is the library's part of COPYRIGHT.txt.
_LIBRARY = """
filegroup(
    name = "{name}",
    package_metadata = [":{name}_metadata"],
)

package_metadata(
    name = "{name}_metadata",
    attributes = [":{name}_license"],
    purl = {purl},
)

license(
    name = "{name}_license",
    kind = {kind},
    text = "{name}.txt",
)
"""

# Temporary exception: the license rule of package_metadata 0.0.15 takes one license kind,
# not an SPDX expression, so a library under several licenses gets a kind whose identifier
# is the expression, which the SPDX tools write as its declared license verbatim. Remove it
# once a package_metadata release on the registry has license(expression = ...). A license
# on no SPDX list is a LicenseRef kind, which needs a license_kind of its own anyway.
_LICENSE_KIND = """
license_kind(
    name = "{name}_kind",
    full_name = {full_name},
    identifier = {identifier},
)
"""

# The label of the metadata, for a package of a repository that only some packages carry.
PACKAGE_METADATA = "//%s:package_metadata" % _PACKAGE

# The label of the targets that carry the metadata of the libraries the software bundles,
# for the targets that hold the software; without any, it is empty.
BUNDLED_PACKAGES = "//%s:bundled_packages" % _PACKAGE

def _target_name(name, taken):
    """A target name of a library's name, lower case with underscores, unique among taken."""
    words = words_of("".join([character if character.isalnum() else " " for character in name.lower().elems()]))
    base = "_".join(words)
    target = base
    for number in range(2, len(taken) + 2):
        if target not in taken:
            break
        target = "%s_%d" % (base, number)
    taken[target] = True
    return target

def _library(repository_ctx, library, name):
    """Write the license text of a library Godot bundles and return its declarations."""
    repository_ctx.file("%s/%s.txt" % (_PACKAGE, name), library.text, executable = False)
    if " " not in library.spdx and not library.spdx.startswith("LicenseRef-"):
        kind = repr(str(Label("@package_metadata//licenses/spdx:" + library.spdx)))
        kind_declaration = ""
    else:
        kind = repr(":%s_kind" % name)
        kind_declaration = _LICENSE_KIND.format(
            name = name,
            full_name = repr(library.license),
            identifier = repr(library.spdx),
        )
    return _LIBRARY.format(
        name = name,
        purl = repr(purl.builder().type("generic").namespace("godot").name(library.name).build()),
        kind = kind,
    ) + kind_declaration

def _libraries(repository_ctx, copyright):
    """The declarations of the libraries a COPYRIGHT.txt lists and their target names."""
    if not copyright or not repository_ctx.path(copyright).exists:
        return [], []
    declarations = []
    taken = {}
    for library in bundled_libraries(repository_ctx.read(copyright)):
        declarations.append(_library(repository_ctx, library, _target_name(library.name, taken)))
    return declarations, list(taken)

def write_package_metadata(repository_ctx, package_url, license_text = None, copyright = None):
    """
    Declare the package metadata of MIT-licensed software for every target of a repository.

    Writes the metadata package, as write_metadata_package does, and REPO.bazel, which no
    repository of the ruleset writes otherwise and which gives every target of the
    repository the metadata.

    Args:
        repository_ctx: Repository rule context.
        package_url: The software's package URL, such as source_purl's.
        license_text: Path of the software's license text, or None.
        copyright: Path or label of the COPYRIGHT.txt of the Godot the software is, or None.
    """
    repository_ctx.file(
        "REPO.bazel",
        "repo(default_package_metadata = [%r])\n" % PACKAGE_METADATA,
        executable = False,
    )
    write_metadata_package(repository_ctx, package_url, license_text, copyright)

def write_metadata_package(repository_ctx, package_url, license_text = None, copyright = None):
    """
    Declare the package metadata of MIT-licensed software in a repository's own package.

    Writes the package `_package_metadata`, which holds the metadata and a copy of the
    license text as LICENSE; the packages that hold the software name PACKAGE_METADATA. With
    a Godot COPYRIGHT.txt, each library it lists is a package of its own, which the targets
    that name BUNDLED_PACKAGES carry.

    Args:
        repository_ctx: Repository rule context.
        package_url: The software's package URL, such as source_purl's.
        license_text: Path of the software's license text, or None; a missing file leaves
            the license without text.
        copyright: Path or label of the COPYRIGHT.txt of the Godot whose libraries the
            software bundles, or None; a missing file names none.
    """
    if license_text and not repository_ctx.path(license_text).exists:
        license_text = None
    if license_text:
        repository_ctx.file(
            _PACKAGE + "/LICENSE",
            repository_ctx.read(license_text),
            executable = False,
        )
    libraries, names = _libraries(repository_ctx, copyright)
    build = _HEADER.format(
        license_bzl = repr(str(Label("@package_metadata//licenses/rules:license.bzl"))),
        license_kind_bzl = repr(str(Label("@package_metadata//licenses/rules:license_kind.bzl"))),
        package_metadata_bzl = repr(str(Label("@package_metadata//rules:package_metadata.bzl"))),
        packages = repr([":" + name for name in names]),
        purl = repr(package_url),
        kind = repr(str(Label("@package_metadata//licenses/spdx:MIT"))),
        text = '    text = "LICENSE",\n' if license_text else "",
    )
    repository_ctx.file(_PACKAGE + "/BUILD.bazel", build + "".join(libraries), executable = False)
