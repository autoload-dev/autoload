"""
Create an add-on module in addons/ from the template, or add an add-on to a module.

`python3 -m tools.addons.new <module> [--addon <addon>]` (`bazel run //tools/addons:new --`) writes
tools/addons/template/module/ to addons/<module>/ for a new module, with
tools/addons/template/bcr/ to .bcr/addons/<module>/ for its releases, and
tools/addons/template/addon/ to addons/<module>/<addon>/ for the add-on. The add-on is
named like the module unless --addon names it. In both trees, `{{token}}` in file names and
contents stands for a name derived from the two, and every file name ends in `.tmpl`. A new
module's examples then pin their Maven graph, which needs Bazel and the network. The
written files belong to the module from then on: nothing regenerates them.

`addons/.selftest` (gitignored) is the self-test's module (`mise run ci:work -- <lane>:addon-template`): it is
regenerated from scratch each time.
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tools.addons import registry
from tools.addons.modules import ROOT, module_name, module_path
from tools.addons.uids import id_to_uid

TEMPLATE = Path(__file__).resolve().parent / "template"
# Every template file ends in it, so that no tool takes the templates for sources.
SUFFIX = ".tmpl"
NAME = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
TOKEN = re.compile(r"\{\{([a-z_]+)\}\}")
SELFTEST = ".selftest"
# How often pin() runs the examples' pin, and the wait before the second run; later
# waits grow linearly.
PIN_ATTEMPTS = 3
PIN_RETRY_SECONDS = 20


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
            "module_name": module_name(self.module),
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


def generate(
    directory: str, addon: str | None = None, root: Path = ROOT, release: bool = True
) -> list[Path]:
    """
    Write a new module with one add-on, or one add-on into an existing module. A new module
    that is released also gets its registry templates in .bcr/addons/<directory>/.
    """
    names = Names(directory, addon)
    invalid = [name for name in (names.module, names.addon) if not NAME.fullmatch(name)]
    if invalid:
        raise ValueError(f"{invalid[0]}: use lower snake case, such as platform_paths")
    module = root / module_path(directory)
    tokens = names.tokens((root / ".bazelversion").read_text().strip())
    written = []
    if not (module / "MODULE.bazel").exists():
        written += copy_tree("module", module, tokens)
        if release:
            written += registry_templates(directory, root, tokens)
    return written + copy_tree("addon", module / names.addon, tokens)


def registry_templates(directory: str, root: Path, tokens: dict[str, str]) -> list[Path]:
    """The templates publish-to-bcr reads for the module's releases, written once."""
    templates = root / registry.templates_directory(directory)
    written = copy_tree("bcr", templates, tokens)
    metadata = templates / registry.METADATA
    metadata.write_text(registry.metadata(directory, root))
    return [*written, metadata]


def pin(
    directory: str, root: Path = ROOT, wait: Callable[[float], None] = time.sleep
) -> None:
    """Pin the examples' Maven graph, which starts from the template's empty lock file.

    Gradle, which resolves the graph, tries a failing repository request three times in
    quick succession and then disables that repository for the rest of the resolution, so
    one burst of 429 or 5xx responses from Maven Central fails every module still to be
    resolved there as `(INTERNAL)`. A new pin resolves afresh: a failed pin is run again,
    after a growing wait, up to PIN_ATTEMPTS times in all.
    """
    # Under `bazel run //tools/addons:new`, the generator's own runfiles variables would
    # point the pin's launcher at the wrong runfiles tree.
    runfiles = {"RUNFILES_DIR", "RUNFILES_MANIFEST_FILE", "JAVA_RUNFILES"}
    environment = {
        name: value for name, value in os.environ.items() if name not in runfiles
    }

    def run(check: bool) -> int:
        return subprocess.run(
            ["bazel", "run", "@maven//:pin"],
            cwd=root / module_path(directory) / "examples",
            env={**environment, "REPIN": "1"},
            check=check,
        ).returncode

    for attempt in range(1, PIN_ATTEMPTS):
        if run(check=False) == 0:
            return
        delay = PIN_RETRY_SECONDS * attempt
        print(
            f"Pinning failed (attempt {attempt} of {PIN_ATTEMPTS}); "
            f"pinning again in {delay} s.",
            file=sys.stderr,
            flush=True,
        )
        wait(delay)
    run(check=True)


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
    # The self-test module is never released.
    written = generate(args.module, args.addon or None, release=args.module != SELFTEST)
    for path in written:
        print(path.relative_to(ROOT))
    if any(path.name == "MODULE.bazel" for path in written) and not args.no_pin:
        pin(args.module)
    if args.module != SELFTEST:
        print(
            "\nNext: describe the module in its README and verify it with "
            f"`mise run ci:work -- desktop:addon:{args.module}`."
        )


if __name__ == "__main__":
    main()
