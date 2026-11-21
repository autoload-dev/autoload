"""
Create an add-on module in addons/ from the template, or add an add-on to a module.

`python3 -m tools.addons.new <module> [--addon <addon>]` (`mise run addon:new`) writes
tools/addons/template/module/ to addons/<module>/ for a new module, and
tools/addons/template/addon/ to addons/<module>/<addon>/ for the add-on. The add-on is
named like the module unless --addon names it. In both trees, `{{token}}` in file names and
contents stands for a name derived from the two, and every file name ends in `.tmpl`. A new
module's examples then pin their Maven graph, which needs Bazel and the network.

`addons/.selftest` (gitignored) is the self-test's module (`mise run addon:template`): it is
regenerated from scratch each time.
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tools.addons.modules import ROOT, module_path
from tools.resource_uids import id_to_uid

TEMPLATE = Path(__file__).resolve().parent / "template"
# Every template file ends in it, so that no tool takes the templates for sources.
SUFFIX = ".tmpl"
NAME = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
TOKEN = re.compile(r"\{\{([a-z_]+)\}\}")
SELFTEST = ".selftest"


def words(name: str) -> list[str]:
    return [word.capitalize() for word in name.split("_")]


def uid(*seed: str) -> str:
    """A resource UID derived from its seed: the same module gets the same UIDs."""
    digest = hashlib.sha256("/".join(seed).encode()).digest()
    return id_to_uid(int.from_bytes(digest[:8]) >> 1)


@dataclass(frozen=True)
class Names:
    """The names the template derives from a module directory and an add-on directory."""

    directory: str
    addon_directory: str | None = None

    @property
    def module(self) -> str:
        return self.directory.removeprefix(".")

    @property
    def addon(self) -> str:
        return self.addon_directory or self.module

    def tokens(self, bazel_version: str) -> dict[str, str]:
        parts = [self.module] if self.addon == self.module else [self.module, self.addon]
        return {
            "module": self.module,
            "module_name": f"autoload_{self.module}",
            "addon": self.addon,
            # Unique across add-ons and applications, and never the add-on's own name.
            "extension": f"{self.module}_{self.addon}"
            if len(parts) > 1
            else f"{self.module}_extension",
            "class": "".join(word for part in parts for word in words(part)),
            "title": " ".join(word for part in parts for word in words(part)),
            "script_uid": uid(self.module, self.addon, "script"),
            "scene_uid": uid(self.module, self.addon, "scene"),
            "bazel_version": bazel_version,
        }


def render(text: str, tokens: dict[str, str]) -> str:
    return TOKEN.sub(lambda match: tokens.get(match[1], match[0]), text)


def template_files(tree: str) -> list[tuple[Path, str]]:
    """Each file of a template tree with its path in the generated tree, tokens unreplaced."""
    source = TEMPLATE / tree
    return [
        (path, path.relative_to(source).as_posix().removesuffix(SUFFIX))
        for path in sorted(source.rglob("*"))
        if path.is_file()
    ]


def copy_tree(tree: str, target: Path, tokens: dict[str, str]) -> list[Path]:
    """Copy one template tree with its tokens replaced; never overwrite a file."""
    written = []
    for path, relative in template_files(tree):
        destination = target / render(relative, tokens)
        if destination.exists():
            raise FileExistsError(f"{destination} exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(render(path.read_text(), tokens))
        written.append(destination)
    return written


def generate(directory: str, addon: str | None = None, root: Path = ROOT) -> list[Path]:
    """Write a new module with one add-on, or one add-on into an existing module."""
    names = Names(directory, addon)
    invalid = [name for name in (names.module, names.addon) if not NAME.fullmatch(name)]
    if invalid:
        raise ValueError(f"{invalid[0]}: use lower snake case, such as platform_paths")
    module = root / module_path(directory)
    tokens = names.tokens((root / ".bazelversion").read_text().strip())
    written = []
    if not (module / "MODULE.bazel").exists():
        written += copy_tree("module", module, tokens)
    return written + copy_tree("addon", module / names.addon, tokens)


def pin(directory: str, root: Path = ROOT) -> None:
    """Pin the examples' Maven graph, which starts from the template's empty lock file."""
    subprocess.run(
        ["bazel", "run", "@maven//:pin"],
        cwd=root / module_path(directory) / "examples",
        env={**os.environ, "REPIN": "1"},
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", help="the module's directory below addons/")
    parser.add_argument(
        "--addon", default="", help="the add-on's directory in the module"
    )
    parser.add_argument(
        "--no-pin",
        action="store_true",
        help="leave a new module's examples/maven_install.json unpinned",
    )
    args = parser.parse_args()
    if args.module == SELFTEST:
        shutil.rmtree(ROOT / module_path(SELFTEST), ignore_errors=True)
    written = generate(args.module, args.addon or None)
    for path in written:
        print(path.relative_to(ROOT))
    if any(path.name == "MODULE.bazel" for path in written) and not args.no_pin:
        pin(args.module)
    if args.module != SELFTEST:
        print(
            "\nNext: describe the module in the first paragraph of its README, run "
            "`mise run addons:generate` and verify it with "
            f"`mise run addon:host {args.module}`."
        )


if __name__ == "__main__":
    main()
