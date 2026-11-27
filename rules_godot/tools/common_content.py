"""Merge the extension descriptors of a pack's platform slices into one."""

import argparse
import json
from pathlib import Path

from tools.project_statements import statement_groups


def merge_descriptors(descriptors: list[tuple[str, str]]) -> str:
    """Union the descriptors' entries, requiring identical configuration and overlap."""
    merged: dict[tuple[str, str], str] = {}
    configuration = None
    for platform_slice, text in descriptors:
        entries = {}
        for group, section, key in statement_groups(text):
            if key is not None:
                if section is None:
                    raise ValueError(
                        f"Descriptor of {platform_slice} has an unsectioned key"
                    )
                identity = (section, key)
                value = group.split("=", 1)[1].strip()
                if identity in entries:
                    raise ValueError(f"Descriptor of {platform_slice} repeats {identity}")
                entries[identity] = value
        controls = {
            key: value
            for key, value in entries.items()
            if key[0] not in {"libraries", "dependencies"}
        }
        if configuration is not None and controls != configuration:
            raise ValueError(f"Descriptor configuration differs at {platform_slice}")
        configuration = controls
        for identity, value in entries.items():
            if identity in merged and merged[identity] != value:
                raise ValueError(f"Descriptor {identity} conflicts at {platform_slice}")
            merged[identity] = value
    lines = []
    for section in sorted({key[0] for key in merged}):
        lines += [f"[{section}]"]
        lines += [
            f"{key}={value}"
            for (group, key), value in sorted(merged.items())
            if group == section
        ]
        lines += [""]
    return "\n".join(lines)


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
