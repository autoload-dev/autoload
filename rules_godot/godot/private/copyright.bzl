"""
The libraries Godot bundles, as its COPYRIGHT.txt lists them.

COPYRIGHT.txt follows the machine-readable Debian copyright format 1.0: a header paragraph,
one `Files` paragraph per group of files with its Comment, Copyright and License fields, and
one stand-alone `License` paragraph per license short name with the license's text. Godot
lists every library under `thirdparty/` and every file of another license, whether a build
compiles it or not.

Sections: Paragraphs, Licenses, Bundled libraries.
"""

visibility("//godot/...")

# ==== Paragraphs ==============================================================

def _paragraphs(text):
    """The paragraphs of a Debian copyright file: lists of lines, split at blank lines."""
    paragraphs = []
    lines = []
    for line in text.split("\n"):
        if line.strip():
            lines.append(line)
        elif lines:
            paragraphs.append(lines)
            lines = []
    if lines:
        paragraphs.append(lines)
    return paragraphs

def _fields(lines):
    """
    The fields of a paragraph, each a list of its first line's value and its continuation lines.

    A continuation line starts with whitespace; it keeps its text without the leading space.
    """
    fields = {}
    values = None
    for line in lines:
        if line[0] in " \t" and values != None:
            values.append(line.strip())
        else:
            key, _, value = line.partition(":")
            values = [value.strip()]
            fields[key.strip()] = values
    return fields

# ==== Licenses ================================================================

# The SPDX identifier of each of Godot's license short names on an SPDX list: Godot writes
# Debian short names, and SPDX identifiers where Debian has none. Where they differ, the
# comment gives the evidence. Any other short name, such as glslang's combination of
# licenses or the Wide Open License (WOL), is on no SPDX list and becomes a LicenseRef.
_SPDX = {
    "Apache-2.0": "Apache-2.0",
    "BSL-1.0": "BSL-1.0",
    "CC-BY-4.0": "CC-BY-4.0",
    "CC0-1.0": "CC0-1.0",
    "FTL": "FTL",
    "IJG": "IJG",
    "MIT-0": "MIT-0",
    "MPL-2.0": "MPL-2.0",
    "OFL-1.1": "OFL-1.1",
    "Unlicense": "Unlicense",
    "Zlib": "Zlib",
    # Debian's name of the MIT license.
    "Expat": "MIT",
    "BSD-2-clause": "BSD-2-Clause",
    "BSD-3-clause": "BSD-3-Clause",
    # The text Godot gives is HarfBuzz's "Old MIT" license, which the SPDX list names
    # MIT-Modern-Variant and cites HarfBuzz for.
    "HarfBuzz": "MIT-Modern-Variant",
    # The text Godot gives is ICU's "COPYRIGHT AND PERMISSION NOTICE (ICU 58 and later)"
    # with the Unicode terms of use, the SPDX list's Unicode-DFS-2016.
    "Unicode": "Unicode-DFS-2016",
    # The text Godot gives for the Mesa Wayland protocol is the permission notice without the
    # MIT clause of SPDX's X11: the SPDX list's HPND-sell-variant.
    "X11": "HPND-sell-variant",
}

_OPERATORS = {"and": "AND", "or": "OR"}

def words_of(text):
    """The words of text, split at spaces and tabs."""
    return [word for word in text.replace("\t", " ").split(" ") if word]

def _reference(text):
    """A LicenseRef of text: its letters, digits, dots and dashes, other characters as dashes."""
    return "LicenseRef-" + "".join([
        character if character.isalnum() or character in ".-" else "-"
        for character in text.elems()
    ])

def spdx_license(license):
    """
    The SPDX license expression of a License field's first line, such as `Expat and Zlib`.

    The field joins short names with `and` and `or`, as SPDX joins identifiers with AND and
    OR. An expression with a short name on no SPDX list becomes one LicenseRef of the whole
    field, since only the expression's text can describe it.

    Args:
        license: The License field's first line.

    Returns:
        The SPDX expression, such as `MIT AND Zlib` or `LicenseRef-Expat-and-WOL`.
    """
    words = words_of(license)
    identifiers = [_OPERATORS.get(word) or _SPDX.get(word) for word in words]
    if None in identifiers:
        return _reference("-".join(words))
    return " ".join(identifiers)

def _license_names(license):
    """The short names of a License field's first line, without its operators."""
    return [word for word in words_of(license) if word not in _OPERATORS]

# ==== Bundled libraries =======================================================

def _library_name(fields):
    """The name of a Files paragraph's library: its Comment, or its first file pattern."""
    comment = fields.get("Comment")
    return comment[0] if comment and comment[0] else fields["Files"][0].split(" ")[0]

def _files_by_library(paragraphs):
    """The Files paragraphs but Godot's own by library name: structs of their licenses and texts."""
    libraries = {}
    for lines, fields in paragraphs:
        if "Files" not in fields or fields["Files"] == ["*"]:
            continue
        library = libraries.setdefault(
            _library_name(fields),
            struct(licenses = [], paragraphs = []),
        )
        if fields["License"][0] not in library.licenses:
            library.licenses.append(fields["License"][0])
        library.paragraphs.append("\n".join(lines))
    return libraries

def _grouped(expression, operator, count):
    """An expression in parentheses where it joins others with AND but holds operator itself."""
    return "(%s)" % expression if count > 1 and operator in expression else expression

def _short_names(licenses):
    """The distinct short names of License fields, in order."""
    return {name: True for license in licenses for name in _license_names(license)}.keys()

def _joined_spdx(licenses):
    """The SPDX expression of the License fields that together license one library."""
    parts = [spdx_license(license) for license in licenses]
    if [part for part in parts if part.startswith("LicenseRef-")]:
        return _reference("-and-".join(["-".join(words_of(license)) for license in licenses]))
    return " AND ".join([_grouped(part, " OR ", len(parts)) for part in parts])

def _library(name, library, license_texts):
    """A library of its Files paragraphs, with the texts of the licenses they name."""
    spdx = _joined_spdx(library.licenses)
    return struct(
        name = name,
        license = " and ".join([
            _grouped(part, " or ", len(library.licenses))
            for part in library.licenses
        ]),
        spdx = spdx,
        kind = spdx if spdx in _SPDX.values() else None,
        text = "\n\n".join(library.paragraphs + [
            license_texts[short_name]
            for short_name in _short_names(library.licenses)
            if short_name in license_texts
        ]) + "\n",
    )

def bundled_libraries(text):
    """
    The libraries and other third-party files a Godot COPYRIGHT.txt lists.

    Each Files paragraph but Godot's own, `Files: *`, names one; paragraphs of the same
    Comment, such as the Bullet code in several modules, form one library. A library's
    license joins its paragraphs' distinct licenses with `and`.

    Args:
        text: The content of COPYRIGHT.txt.

    Returns:
        The libraries in the file's order: structs of name, license (Godot's License
        field, such as `Expat and Zlib`), spdx (its SPDX expression), kind (the SPDX
        identifier of a single license on the SPDX list, or None) and text (the library's
        paragraphs and the texts of its licenses, as COPYRIGHT.txt has them).
    """
    paragraphs = [(lines, _fields(lines)) for lines in _paragraphs(text)]
    license_texts = {
        fields["License"][0]: "\n".join(lines)
        for lines, fields in paragraphs
        if "License" in fields and "Files" not in fields
    }
    return [
        _library(name, library, license_texts)
        for name, library in _files_by_library(paragraphs).items()
    ]
