"""Read what Godot decided for an export and fill shell file templates."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tools import template as template_file

TEMPLATES = Path(__file__).parent / "templates"
_HEX = "0123456789abcdef"


class Facts:
    """What Godot reported for an export: its options, settings and versions."""

    def __init__(self, data: Mapping[str, Any]) -> None:
        self.options: dict[str, Any] = data["options"]
        self.settings: dict[str, Any] = data["settings"]
        self.versions: dict[str, str] = data["versions"]
        self.name_translations: dict[str, str | None] = data["name_translations"]

    def option(self, name: str) -> Any:
        """Return an export option's value, its default when the pack sets none."""
        if name not in self.options:
            raise ValueError(f"Godot's exporter has no export option {name}")
        return self.options[name]

    def text(self, name: str) -> str:
        """Return a string export option without surrounding whitespace."""
        return str(self.option(name) or "").strip()

    def setting(self, name: str) -> Any:
        """Return a project setting with the export's feature overrides."""
        return self.settings.get(name)

    def orientation(self, table: list) -> Any:
        """Return the entry of a table for the project's handheld orientation."""
        value = self.setting("display/window/handheld/orientation")
        return table[value if isinstance(value, int) and 0 <= value < len(table) else 0]


def release_value(facts: Facts, values: Mapping[str, Any], option: str, flag: Any) -> Any:
    """
    Return an option the pack sets, else a release build setting, else Godot's value.

    The build settings --@autoload_rules_godot//godot:app_version and build_number set
    what a pack's own export options leave unset. Godot's value of a version
    option falls back to the project's application/config/version.
    """
    if option in values["explicit"] or not flag:
        return (
            facts.versions[option] if option in facts.versions else facts.option(option)
        )
    return flag


def xml(value: object) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")


def color_html(color: list[float]) -> str:
    """Return a Color's red, green and blue as Godot's Color.to_html(false) writes them."""
    return "".join(
        _HEX[value // 16] + _HEX[value % 16]
        for value in (
            max(0, min(255, int(component * 255 + 0.5))) for component in color[:3]
        )
    )


def fill(template: str, values: Mapping[str, str]) -> str:
    """Fill a template file of templates/ with values."""
    return template_file.fill(TEMPLATES / template, values)


def set_off(lines: list[str]) -> str:
    """Return lines as a block followed by an empty line, or nothing."""
    return "\n".join(lines) + "\n" if lines else ""
