"""
Print the module that a release tag `<module>-v<version>` releases, one `key=value` per line.

- name and version: from the tag;
- root: the module's directory, `rules_godot` for autoload_rules_godot and
  `addons/<directory>` for
  the add-on module `autoload_<directory>` (RG015);
- bcr: whether the Bazel Central Registry gets the release, which its templates in
  .bcr/<root>/ decide;
- test: the command that tests the release in a checkout of the tag.

No table lists the modules: a new add-on module is releasable as soon as it exists.
Run it from the repository root: `python3 -m tools.ci.release_module <tag>`.
"""

import re
import sys
from pathlib import Path

from tools.addons.modules import ROOT, module_attributes, module_path

TAG = re.compile(r"([a-z][a-z0-9_]*)-v([0-9]+\.[0-9]+\.[0-9]+.*)")
RULESET = "autoload_rules_godot"
RULESET_ROOT = Path("rules_godot")
# The ruleset's release test: the registry's test module, as its presubmit.yml runs it. Its
# own //... builds engines and mobile packages.
RULESET_TEST = "cd rules_godot/e2e/smoke && bazel test //..."


def module_root(name: str, root: Path = ROOT) -> Path:
    """The directory of the module the name declares, relative to the repository."""
    directory = (
        RULESET_ROOT if name == RULESET else module_path(name.removeprefix("autoload_"))
    )
    manifest = root / directory / "MODULE.bazel"
    if (
        not manifest.is_file()
        or module_attributes(manifest.read_text()).get("name") != name
    ):
        raise ValueError(f"No module of this repository is named {name}")
    return directory


def describe(tag: str, root: Path = ROOT) -> dict[str, str]:
    match = TAG.fullmatch(tag)
    if not match:
        raise ValueError(f"Release tags are named <module>-v<version>, not {tag}")
    name, version = match.groups()
    directory = module_root(name, root)
    test = (
        RULESET_TEST
        if name == RULESET
        else f"python3 -m tools.addons.lanes host {directory.name}"
    )
    return {
        "name": name,
        "version": version,
        "root": directory.as_posix(),
        "bcr": str(
            (root / ".bcr" / directory / "metadata.template.json").is_file()
        ).lower(),
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
