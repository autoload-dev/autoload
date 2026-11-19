"""
Let shell defaults yield to the files a consumer supplies for the same slot.

An application's shell files and shell assets are defaults. A consumer file for the same
slot reaches the platform rule unchanged, and the default steps aside: an Android resource
with the same type, name and configuration qualifiers, a top-level Info.plist key.
"""

import argparse
import plistlib
import shutil
from collections.abc import Iterable
from pathlib import Path
from xml.etree import ElementTree

_DENSITIES = {"ldpi", "mdpi", "tvdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi", "nodpi"}


def resource_key(path: Path) -> str:
    """
    The resource directory and name of an Android resource file, as <directory>/<name>.

    Android adds the version qualifier that a density qualifier implies, so
    mipmap-xxxhdpi/icon.png and mipmap-xxxhdpi-v4/icon.webp define one resource.
    """
    qualifiers = path.parent.name.split("-")
    versioned = any(q.startswith("v") and q[1:].isdigit() for q in qualifiers[1:])
    if not versioned:
        if "anydpi" in qualifiers:
            qualifiers.append("v21")
        elif _DENSITIES.intersection(qualifiers[1:]):
            qualifiers.append("v4")
    return "-".join(qualifiers) + "/" + path.name.split(".", 1)[0]


def defined_styles(paths: Iterable[Path]) -> set[str]:
    """The names of the styles that Android value resource files define."""
    names = set()
    for path in paths:
        for element in ElementTree.parse(path).getroot():
            if element.tag == "style" or (
                element.tag == "item" and element.get("type") == "style"
            ):
                names.add(element.get("name", ""))
    return names


def without_styles(text: str, names: set[str]) -> str:
    """A values file the shell writes, without the named styles."""
    root = ElementTree.fromstring(text)
    removed = [style for style in root.findall("style") if style.get("name") in names]
    if not removed:
        return text
    for style in removed:
        root.remove(style)
    ElementTree.indent(root, space="    ")
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        + ElementTree.tostring(root, encoding="unicode")
        + "\n"
    )


def plist_keys(paths: Iterable[Path]) -> dict[str, Path]:
    """The top-level keys of Info.plist fragments, with the first fragment setting each."""
    keys: dict[str, Path] = {}
    for path in paths:
        # rules_apple also takes binary fragments, so this parser is not the strict
        # XML one that checks the generated Info.plist.
        with path.open("rb") as stream:
            fragment = plistlib.load(stream)
        if not isinstance(fragment, dict):
            raise TypeError(f"{path} is not a property list dictionary")
        for key in fragment:
            keys.setdefault(key, path)
    return keys


def check_owned(keys: dict[str, Path], owned: dict[str, str]) -> None:
    """Reject override keys that rules_godot or the platform rule owns, naming the owner."""
    for key in sorted(keys):
        if key in owned:
            raise ValueError(
                f"{keys[key]} sets {key}, which belongs to {owned[key]}; "
                "set it there instead"
            )


def without_plist_keys(text: str, keys: Iterable[str]) -> str:
    """An Info.plist without the given top-level keys."""
    data = plistlib.loads(text.encode("utf-8"))
    for key in keys:
        data.pop(key, None)
    return plistlib.dumps(data, sort_keys=False).decode("utf-8")


def yield_plist_keys(
    text: str, fragments: list[str], overrides: Iterable[Path], owned: dict[str, str]
) -> tuple[str, list[str], set[str]]:
    """
    Leave the keys of the application's Info.plist fragments to them.

    The shell's Info.plist and the add-ons' fragments lose every top-level key an
    override sets; an override setting an owned key fails.

    Returns:
        The shell's Info.plist and the add-ons' fragments without those keys, and the
        keys.
    """
    keys = plist_keys(overrides)
    check_owned(keys, owned)
    if not keys:
        return text, fragments, set()
    return (
        without_plist_keys(text, keys),
        [without_plist_keys(fragment, keys) for fragment in fragments],
        set(keys),
    )


def copy_resources(source: Path, output: Path, overrides: Iterable[Path]) -> None:
    """Copy a tree of Android resources without those the overrides define."""
    omitted = {resource_key(path) for path in overrides}
    output.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if path.is_dir() or resource_key(relative) in omitted:
            continue
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["android-resources"])
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--override", type=Path, action="append", default=[])
    args = parser.parse_args()
    copy_resources(args.input, args.output, args.override)


if __name__ == "__main__":
    main()
