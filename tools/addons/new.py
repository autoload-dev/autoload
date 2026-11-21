"""
Create an add-on module in addons/ from the template, or add an add-on to a module.

`python3 -m tools.addons.new <module> [--addon <addon>]` (`mise run addon:new`) writes
tools/addons/template/module/ to addons/<module>/ for a new module, and
tools/addons/template/addon/ to addons/<module>/<addon>/ for the add-on. The add-on is
named like the module unless --addon names it. In both trees, `{{token}}` in file names and
contents stands for a name derived from the two, and every file name ends in `.tmpl`. A new module's examples then pin their
Maven graph, which needs Bazel and the network.
"""

import argparse
import os
import re
import secrets
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tools.addons.modules import ROOT

TEMPLATE = Path(__file__).resolve().parent / "template"
# Every template file ends in it, so that no tool takes the templates for sources.
SUFFIX = ".tmpl"
NAME = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
TOKEN = re.compile(r"\{\{([a-z_]+)\}\}")
# Godot's resource UIDs: uid:// and a base-36 number of up to 63 bits (ResourceUID).
UID_DIGITS = "abcdefghijklmnopqrstuvwxyz0123456789"
# The directory of the generator's self-test module (mise run addon:template), gitignored.
SELFTEST = ".selftest"


def words(name: str) -> list[str]:
    return [word.capitalize() for word in name.split("_")]


def uid() -> str:
    number = secrets.randbits(63)
    digits = ""
    while number:
        number, digit = divmod(number, len(UID_DIGITS))
        digits = UID_DIGITS[digit] + digits
    return "uid://" + (digits or "a")


@dataclass(frozen=True)
class Names:
    """The names the template derives from a module directory and an add-on directory."""

    directory: str
    addon: str

    @property
    def module(self) -> str:
        return self.directory.removeprefix(".")

    def tokens(self) -> dict[str, str]:
        same = self.addon == self.module
        parts = [self.module] if same else [self.module, self.addon]
        return {
            "module": self.module,
            "module_name": f"autoload_{self.module}",
            "addon": self.addon,
            # Unique across add-ons and applications, and never the add-on's own name.
            "extension": "_".join(parts) if not same else f"{self.module}_extension",
            "class": "".join(word for part in parts for word in words(part)),
            "title": " ".join(word for part in parts for word in words(part)),
            "script_uid": uid(),
            "scene_uid": uid(),
        }


def render(text: str, tokens: dict[str, str]) -> str:
    return TOKEN.sub(lambda match: tokens.get(match[1], match[0]), text)


def copy_tree(source: Path, target: Path, tokens: dict[str, str]) -> list[Path]:
    """Copy one template tree with its tokens replaced; never overwrite a file."""
    written = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source).as_posix().removesuffix(SUFFIX)
        destination = target / render(relative, tokens)
        if destination.exists():
            raise FileExistsError(f"{destination} exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(render(path.read_text(), tokens))
        written.append(destination)
    return written


def generate(directory: str, addon: str | None = None, root: Path = ROOT) -> list[Path]:
    """Write a new module with one add-on, or one add-on into an existing module."""
    names = Names(directory, addon or directory.removeprefix("."))
    for name in (names.module, names.addon):
        if not NAME.fullmatch(name):
            raise ValueError(f"{name}: use lower snake case, such as platform_paths")
    module = root / "addons" / directory
    tokens = names.tokens()
    written = []
    if not (module / "MODULE.bazel").exists():
        written += copy_tree(TEMPLATE / "module", module, tokens)
        for bazelversion in (module / ".bazelversion", module / "examples/.bazelversion"):
            shutil.copyfile(root / ".bazelversion", bazelversion)
            written.append(bazelversion)
    written += copy_tree(TEMPLATE / "addon", module / names.addon, tokens)
    return written


def pin(directory: str, root: Path = ROOT) -> None:
    """Pin the examples' Maven graph, which starts from the template's empty lock file."""
    subprocess.run(
        ["bazel", "run", "@maven//:pin"],
        cwd=root / "addons" / directory / "examples",
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
        "--replace",
        action="store_true",
        help=f"delete addons/{SELFTEST} first; only for the self-test module",
    )
    parser.add_argument(
        "--no-pin",
        action="store_true",
        help="leave a new module's examples/maven_install.json unpinned",
    )
    args = parser.parse_args()
    if args.replace:
        if args.module != SELFTEST:
            parser.error(f"--replace only regenerates addons/{SELFTEST}")
        shutil.rmtree(ROOT / "addons" / SELFTEST, ignore_errors=True)
    created = not (ROOT / "addons" / args.module / "MODULE.bazel").exists()
    written = generate(args.module, args.addon or None)
    for path in written:
        print(path.relative_to(ROOT))
    if created and not args.no_pin:
        pin(args.module)
    if args.module != SELFTEST:
        print(
            "\nNext: describe the module in the first paragraph of its README, run "
            "`mise run addons:generate` and verify it with "
            f"`mise run addon:host {args.module}`."
        )


if __name__ == "__main__":
    main()
