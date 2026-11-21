"""Assign evaluated Starlark identities to public reference entrypoints."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from tools.docs.coverage import CATEGORIES, ModuleInfo
from tools.ruleset import strip_repo

EXPORT_CATEGORIES = {**CATEGORIES, "starlark_other_symbol_info": "name"}


def normalize_label(label: str) -> str:
    return strip_repo(label)


@dataclass(frozen=True)
class Export:
    module: str
    name: str
    identity: tuple[str, str, str]


def exports(module_label: str, metadata: ModuleInfo) -> dict[str, Export]:
    result = {}
    for category, name_field in EXPORT_CATEGORIES.items():
        for item in getattr(metadata, category):
            name = getattr(item, name_field)
            origin = getattr(item, "origin_key", None)
            origin_file = (
                normalize_label(origin.file) if origin and origin.file else module_label
            )
            origin_name = origin.name if origin and origin.name else name
            result[name] = Export(
                module_label, name, (category, origin_file, origin_name)
            )
    return result


def assign_surface(
    inventory: dict[str, Any], metadata: dict[str, ModuleInfo]
) -> dict[tuple[str, str, str], Export]:
    """
    Assign primary owners from the complete extraction.

    Each module's coverage test checks its documentation; this checks ownership. Evaluated origin identity catches duplicate public
    exports and cross-repository modules even under different names.
    """
    errors = []
    all_exports: dict[str, dict[str, Export]] = {}
    for label, module in metadata.items():
        all_exports[label] = exports(label, module)

    owners: dict[tuple[str, str, str], Export] = {}
    for label, entry in inventory["PUBLIC_APIS"].items():
        selected = entry["symbols"]
        if len(selected) != len(set(selected)):
            errors.append(f"{label}: duplicate primary symbol selection")
        for name in selected:
            export = all_exports.get(label, {}).get(name)
            if export is None:
                errors.append(f"{label}%{name}: primary symbol does not exist")
                continue
            if export.identity in owners:
                previous = owners[export.identity]
                errors.append(
                    f"{label}%{name}: duplicate primary reference; already owned by {previous.module}%{previous.name}"
                )
            else:
                owners[export.identity] = export

    for label, entry in inventory["PUBLIC_APIS"].items():
        for export in all_exports[label].values():
            if export.identity[1] in inventory["CROSS_REPOSITORY_MODULES"]:
                errors.append(
                    f"{label}%{export.name}: cross-repository module leaked through a public entrypoint; remove the export"
                )
            elif export.name not in entry["symbols"]:
                owner = owners.get(export.identity)
                if owner:
                    errors.append(
                        f"{label}%{export.name}: additional public load path; use {owner.module}%{owner.name}"
                    )
                else:
                    errors.append(
                        f"{label}%{export.name}: public export has no primary reference; assign an owner in PUBLIC_APIS"
                    )
    if errors:
        raise ValueError("\n".join(errors))
    return owners


def validate_rendered(markdown: str, expected: Iterable[str], location: str) -> None:
    """Require exactly the selected API anchors, not just a successful renderer."""
    anchors = re.findall(r'<a id="([^"\n]+)"></a>', markdown)
    expected = set(expected)
    for name in sorted(expected):
        if anchors.count(name) != 1:
            raise ValueError(
                f"{location}%{name}: primary API must appear exactly once in rendered reference"
            )
    # Recognize Stardoc API anchors paired with their headings. Ordinary
    # Markdown sections in module descriptions are not additional API entries.
    pairs = re.findall(r'<a id="([^"\n]+)"></a>\s*\n## ([^\n]+)', markdown)
    headings = [anchor for anchor, heading in pairs if anchor == heading]
    if set(headings) != expected or len(headings) != len(expected):
        raise ValueError(
            f"{location}: rendered API set differs from the assigned primary symbols"
        )
