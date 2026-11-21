"""
Print the module that a release tag `<module>-v<version>` releases, one `key=value` per line.

- name and version: from the tag;
- root: the module's directory, `.` for autoload_rules_godot and `addons/<directory>` for an
  add-on module, the one whose MODULE.bazel declares the name;
- bcr: whether the Bazel Central Registry gets the release, which its templates in .bcr/
  (.bcr/addons/<directory>/ for an add-on) decide;
- test: the command that tests the release in a checkout of the tag.

No table lists the modules: a new add-on module is releasable as soon as it exists.
"""

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAG = re.compile(r"([a-z][a-z0-9_]*)-v([0-9]+\.[0-9]+\.[0-9]+.*)")
# The ruleset's release test: the registry's test module, as its presubmit.yml runs it. Its
# own //... builds engines and mobile packages.
RULESET_TEST = "cd e2e/smoke && bazel test //..."


def declared(module: Path) -> dict[str, str]:
    """The string attributes of a MODULE.bazel's module() call, such as its name."""
    for node in ast.walk(ast.parse((module / "MODULE.bazel").read_text())):
        match node:
            case ast.Call(func=ast.Name(id="module"), keywords=keywords):
                return {
                    keyword.arg: keyword.value.value
                    for keyword in keywords
                    if keyword.arg
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                }
    return {}


def module_root(name: str, root: Path = ROOT) -> str:
    """The directory of the module the name declares, relative to the repository."""
    candidates = [
        root,
        *sorted(path.parent for path in root.glob("addons/*/MODULE.bazel")),
    ]
    for directory in candidates:
        if declared(directory).get("name") == name:
            return directory.relative_to(root).as_posix() or "."
    raise ValueError(f"No module of this repository is named {name}")


def describe(tag: str, root: Path = ROOT) -> dict[str, str]:
    match = TAG.fullmatch(tag)
    if not match:
        raise ValueError(f"Release tags are named <module>-v<version>, not {tag}")
    name, version = match.groups()
    directory = module_root(name, root)
    templates = root / ".bcr" / ("" if directory == "." else directory)
    test = (
        RULESET_TEST
        if directory == "."
        else f"python3 -m tools.addons.lanes host {Path(directory).name}"
    )
    return {
        "name": name,
        "version": version,
        "root": directory,
        "bcr": str((templates / "metadata.template.json").is_file()).lower(),
        "test": test,
    }


def main() -> None:
    try:
        fields = describe(sys.argv[1])
    except ValueError as error:
        sys.exit(str(error))
    print("\n".join(f"{key}={value}" for key, value in fields.items()))


if __name__ == "__main__":
    main()
