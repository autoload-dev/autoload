"""Merge the extension descriptors of a pack's platform slices into one."""

import argparse
import json
from pathlib import Path

from tools.project.statements import statement_groups

# A descriptor's values by section and key.
Entries = dict[tuple[str, str], str]


def _entries(platform_slice: str, text: str) -> Entries:
    """The values a platform slice's descriptor sets."""
    entries = {}
    for group, section, key in statement_groups(text):
        if key is None:
            continue
        if section is None:
            raise ValueError(f"Descriptor of {platform_slice} has an unsectioned key")
        identity = (section, key)
        value = group.split("=", 1)[1].strip()
        if identity in entries:
            raise ValueError(f"Descriptor of {platform_slice} repeats {identity}")
        entries[identity] = value
    return entries


def _configuration(entries: Entries) -> Entries:
    """The entries that every platform slice must share: all but the libraries and dependencies."""
    return {
        key: value
        for key, value in entries.items()
        if key[0] not in {"libraries", "dependencies"}
    }


def _add(merged: Entries, entries: Entries, platform_slice: str) -> None:
    """Add a slice's entries to the merged ones, which must hold the same value for a key."""
    for identity, value in entries.items():
        if merged.get(identity, value) != value:
            raise ValueError(f"Descriptor {identity} conflicts at {platform_slice}")
        merged[identity] = value


def _descriptor(entries: Entries) -> str:
    """The text of a descriptor, its sections and keys in order."""
    lines = []
    for section in sorted({key[0] for key in entries}):
        lines += [f"[{section}]"]
        lines += [
            f"{key}={value}"
            for (group, key), value in sorted(entries.items())
            if group == section
        ]
        lines += [""]
    return "\n".join(lines)


def merge_descriptors(descriptors: list[tuple[str, str]]) -> str:
    """Union the descriptors' entries, requiring identical configuration and overlap."""
    merged: Entries = {}
    configuration = None
    for platform_slice, text in descriptors:
        entries = _entries(platform_slice, text)
        controls = _configuration(entries)
        if configuration is not None and controls != configuration:
            raise ValueError(f"Descriptor configuration differs at {platform_slice}")
        configuration = controls
        _add(merged, entries, platform_slice)
    return _descriptor(merged)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    for descriptor in manifest["descriptors"].values():
        output = Path(descriptor["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            merge_descriptors(
                [
                    (platform_slice, Path(source).read_text())
                    for platform_slice, source in descriptor["sources"].items()
                ]
            )
        )


if __name__ == "__main__":
    main()
