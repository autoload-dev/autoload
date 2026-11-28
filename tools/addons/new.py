"""
Create an add-on module in addons/ from the template, or add an add-on to a module.

`python3 -m tools.addons.new <module> [--addon <addon>]` (`bazel run //tools/addons:new --`) writes
tools/addons/template/module/ to addons/<module>/ for a new module, with
tools/addons/template/bcr/ to .bcr/addons/<module>/ for its releases,
tools/addons/template/examples/ to examples/addons/<module>/ for its example applications
in the root module, regenerating the root's declarations of the add-on modules
(tools/addons/declarations.py), and
tools/addons/template/addon/ to addons/<module>/<addon>/ for the add-on. The add-on is
named like the module unless --addon names it. In these trees, `{{token}}` in file names and
contents stands for a name derived from the two, and every file name ends in `.tmpl`. The
written files belong to the module from then on, but for its shared files: the settings every
module keeps as the generator writes them, which `aspect generate` writes again for every
module and the file lint compares (`stale_shared_files`).

`addons/selftest` with `examples/addons/selftest` (both gitignored) is the self-test's module
(`aspect work addon-template`, tools/addons/selftest.py): it is regenerated from scratch
each time and removed afterwards, with its declaration.

Sections: Names, Templates, Shared files, Generator.
"""

import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from tools.addons import declarations, registry
from tools.addons.modules import ROOT, examples_path, module_name, module_path
from tools.addons.uids import id_to_uid
from tools.setup.modules import addon_modules

# ==== Names ===================================================================

NAME = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")


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
        return self.directory

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


# ==== Templates ===============================================================

TEMPLATE = Path(__file__).resolve().parent / "template"
# Every template file ends in it, so that no tool takes the templates for sources.
SUFFIX = ".tmpl"
TOKEN = re.compile(r"\{\{([a-z_]+)\}\}")


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


# ==== Shared files ============================================================

# The files of the module template that every module keeps as the generator writes them, by
# their path in the module; its registry templates in .bcr/addons/<module>/ are all shared.
SHARED_MODULE_FILES = frozenset(
    {
        ".bazelignore",
        ".bazelrc",
        ".bazelversion",
        ".gitattributes",
        ".gitignore",
        "BUILD.bazel",
        "REPO.bazel",
        "bcr/smoke/.bazelrc",
        "bcr/smoke/.bazelversion",
    }
)


# The repository's license, which every module carries at its root for its release archive
# and the text of its package metadata's license.
LICENSE = "LICENSE"
# A module that brings third-party archives declares them in this file; the template tree
# archives/, the helper it loads beside it and the test of its versions, is shared.
ARCHIVES = "third_party/archives.bzl"


def bazel_version(root: Path) -> str:
    return (root / ".bazelversion").read_text().strip()


def write_files(root: Path, files: dict[Path, str]) -> list[Path]:
    """
    Write the files, by path relative to root, that are missing or differ; the others keep
    their modification times, which Git and Bazel read.
    """
    written = []
    for path, text in files.items():
        target = root / path
        if not target.is_file() or target.read_text() != text:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
            written.append(target)
    return written


def registry_files(directory: str, root: Path, tokens: dict[str, str]) -> dict[Path, str]:
    """
    The templates publish-to-bcr reads for the releases of addons/<directory>, by path
    relative to root: the bcr template tree and the metadata the ruleset's shares.
    """
    templates = registry.templates_directory(directory)
    files = {
        templates / render(relative, tokens): render(path.read_text(), tokens)
        for path, relative in template_files("bcr")
    }
    files[templates / registry.METADATA] = registry.metadata(directory, root)
    return files


# The registry templates of every released module, by their names.
REGISTRY_FILES = (*(relative for _, relative in template_files("bcr")), registry.METADATA)


def shared_files(directory: str, root: Path = ROOT) -> dict[Path, str]:
    """
    What the generator writes to the shared files of the module addons/<directory>, by path
    relative to root: the repository's license, the helper of third-party archives and its
    test only for a module that declares some, and the registry templates only for a module that is
    released, which has them.
    """
    tokens = Names(directory).tokens(bazel_version(root))
    module = module_path(directory)
    files = {
        module / relative: render(path.read_text(), tokens)
        for path, relative in template_files("module")
        if relative in SHARED_MODULE_FILES
    }
    files[module / LICENSE] = (root / LICENSE).read_text()
    if (root / module / ARCHIVES).is_file():
        files.update(
            (module / relative, render(path.read_text(), tokens))
            for path, relative in template_files("archives")
        )
    if (root / registry.templates_directory(directory)).is_dir():
        files.update(registry_files(directory, root, tokens))
    return files


def stale_shared_files(root: Path = ROOT) -> dict[Path, str]:
    """
    The shared files of every add-on module that differ from what the generator writes, by
    path relative to root, with what it writes.
    """
    stale = {}
    for module in addon_modules(root):
        for path, text in shared_files(Path(module).name, root).items():
            target = root / path
            if not target.is_file() or target.read_text() != text:
                stale[path] = text
    return stale


# ==== Generator ===============================================================


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
        raise ValueError(f"{invalid[0]}: use lower snake case, such as in_app_reviews")
    module = root / module_path(directory)
    tokens = names.tokens(bazel_version(root))
    written = []
    if not (module / "MODULE.bazel").exists():
        written += copy_tree("module", module, tokens)
        written += write_files(
            root, {module_path(directory) / LICENSE: (root / LICENSE).read_text()}
        )
        written += copy_tree("examples", root / examples_path(directory), tokens)
        written += declarations.write(root)
        if release:
            written += write_files(root, registry_files(directory, root, tokens))
    return written + copy_tree("addon", module / names.addon, tokens)


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
        f"`bazel test -- @autoload_{args.module}//... //examples/addons/{args.module}/...`."
    )


if __name__ == "__main__":
    main()
