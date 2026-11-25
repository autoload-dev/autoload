"""
Create an add-on module in addons/ from the template, or add an add-on to a module.

`python3 -m tools.addons.new <module> [--addon <addon>]` (`bazel run //tools/addons:new --`) writes
tools/addons/template/module/ to addons/<module>/ for a new module, with
tools/addons/template/bcr/ to .bcr/addons/<module>/ for its releases,
tools/addons/template/examples/ to examples/addons/<module>/ for its example applications
in the root module, which it adds to the root's MODULE.bazel, and
tools/addons/template/addon/ to addons/<module>/<addon>/ for the add-on. The add-on is
named like the module unless --addon names it. In these trees, `{{token}}` in file names and
contents stands for a name derived from the two, and every file name ends in `.tmpl`. The
written files belong to the module from then on: nothing regenerates them.

`addons/.selftest` with `examples/addons/selftest` (both gitignored) is the self-test's module
(`aspect work <lane>:addon-template`, tools/addons/selftest.py): it is regenerated from scratch
each time and removed afterwards, with its entry in the root's MODULE.bazel.
"""

import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from tools.addons import registry
from tools.addons.modules import ROOT, examples_path, module_name, module_path
from tools.addons.uids import id_to_uid

TEMPLATE = Path(__file__).resolve().parent / "template"
# Every template file ends in it, so that no tool takes the templates for sources.
SUFFIX = ".tmpl"
NAME = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
TOKEN = re.compile(r"\{\{([a-z_]+)\}\}")
# The line of the root's MODULE.bazel after which the add-on modules are declared.
DECLARATIONS = (
    "# The add-on modules whose example applications examples/addons/<module>/ holds"
)


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
        written += copy_tree("examples", root / examples_path(directory), tokens)
        written.append(declare(directory, root))
        if release:
            written += registry_templates(directory, root, tokens)
    return written + copy_tree("addon", module / names.addon, tokens)


def declaration(directory: str) -> str:
    """The root module's declaration of an add-on module, which its examples consume."""
    name = module_name(Names(directory).module)
    return (
        f'\nbazel_dep(name = "{name}", version = "0.1.0", dev_dependency = True)\n'
        f"local_path_override(\n"
        f'    module_name = "{name}",\n'
        f'    path = "{module_path(directory).as_posix()}",\n'
        f")\n"
    )


def declare(directory: str, root: Path) -> Path:
    """
    Declare a new add-on module in the root's MODULE.bazel, after the others, unless a run
    that ended before its cleanup, such as the self-test's, left it declared.
    """
    manifest = root / "MODULE.bazel"
    text = manifest.read_text()
    if declaration(directory) in text:
        return manifest
    start = text.index(DECLARATIONS)
    # After the last add-on module's override, or else the comment that introduces them.
    overrides = list(re.finditer(r'\n    path = "addons/[^"]+",\n\)\n', text))
    end = overrides[-1].end() if overrides else text.index("\n", start) + 1
    manifest.write_text(text[:end] + declaration(directory) + text[end:])
    return manifest


def registry_templates(directory: str, root: Path, tokens: dict[str, str]) -> list[Path]:
    """The templates publish-to-bcr reads for the module's releases, written once."""
    templates = root / registry.templates_directory(directory)
    written = copy_tree("bcr", templates, tokens)
    metadata = templates / registry.METADATA
    metadata.write_text(registry.metadata(directory, root))
    return [*written, metadata]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", help="the module's directory below addons/")
    parser.add_argument(
        "--addon", default="", help="the add-on's directory in the module"
    )
    args = parser.parse_args()
    for path in generate(args.module, args.addon or None):
        print(path.relative_to(ROOT))
    print(
        "\nNext: describe the module in its README and verify it with "
        f"`aspect work desktop:addon:{args.module}`."
    )


if __name__ == "__main__":
    main()
