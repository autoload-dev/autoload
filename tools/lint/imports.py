"""
The file lint's import-linter run: the layering contracts of a module's Python packages.

`imports.py <file>...` checks, for each Python file given, the contracts of the nearest
`layers.ini` in its directory or above it within its Bazel module, and each `layers.ini` given, such as
rules_godot/tools/layers.ini, over the packages in the module's directory. A contract concerns
the import graph, not one file, so each contracts file is checked once, whole. Each broken
chain of imports prints the import that completes it, `<path>:<line>: imports <module>, which
the contract '<name>' forbids`.
"""

import contextlib
import io
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import TypeGuard

from importlinter import configuration
from importlinter.application import use_cases


def _module_root(path: Path) -> Path:
    for directory in path.resolve().parents:
        if (directory / "MODULE.bazel").is_file():
            return directory
    raise FileNotFoundError(f"{path} is in no Bazel module")


# The name of a module's contracts file, beside or above the files it covers.
_CONTRACTS = "layers.ini"


def contracts_of(path: Path) -> Path | None:
    """
    The contracts file that covers a file: itself if it is one, else the nearest layers.ini
    within its module.
    """
    if path.name == _CONTRACTS:
        return path
    for directory in path.resolve().parents:
        if (directory / _CONTRACTS).is_file():
            return directory / _CONTRACTS
        if (directory / "MODULE.bazel").is_file():
            return None
    return None


# A direct import of a broken chain in a contract check's metadata.
_LINK = frozenset({"importer", "imported", "line_numbers"})


def _is_chain(value: object) -> TypeGuard[list[dict]]:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(link, dict) and _LINK <= link.keys() for link in value)
    )


def _last_links(metadata: object) -> Iterator[dict]:
    """
    The imports that complete the chains in a contract check's metadata, whatever its type:
    the last of each chain, and of a layers route also each further tail's, but none of its
    further heads, whose imports the route only shares.
    """
    if _is_chain(metadata):
        yield metadata[-1]
    elif isinstance(metadata, dict) and _is_chain(metadata.get("chain")):
        yield metadata["chain"][-1]
        yield from metadata.get("extra_lasts", [])
    elif isinstance(metadata, dict):
        for value in metadata.values():
            yield from _last_links(value)
    elif isinstance(metadata, list):
        for value in metadata:
            yield from _last_links(value)


def _source(root: Path, module: str) -> Path:
    """The file of a module below the module root, relative to the working directory."""
    path = root.joinpath(*module.split("."))
    package = path / "__init__.py"
    found = package if package.is_file() else path.with_suffix(".py")
    return found.relative_to(Path.cwd().resolve())


def findings(contracts: Path) -> list[str]:
    """The broken contracts' findings; raises when the contracts cannot be checked."""
    root = _module_root(contracts)
    sys.path.insert(0, str(root))
    configuration.configure()
    options = use_cases.read_user_options(str(contracts))
    # What lint_imports does before create_report, which has no public counterpart; the
    # version is pinned (requirements.in).
    use_cases._register_contract_types(options)
    # Its progress output would read as findings.
    with contextlib.redirect_stdout(io.StringIO()):
        report = use_cases.create_report(options, cache_dir=None)
    if report.could_not_run:
        raise ValueError(f"{contracts}: {report.invalid_contract_options}")
    lines = set()
    for contract, check in report.get_contracts_and_checks():
        if check.kept:
            continue
        links = list(_last_links(check.metadata))
        for link in links:
            path = _source(root, link["importer"])
            known = [number for number in link["line_numbers"] if number is not None]
            lines.add(
                f"{path}:{min(known, default=1)}: imports {link['imported']}, "
                f"which the contract '{contract.name}' forbids"
            )
        if not links:
            lines.add(f"{contracts}:1: the contract '{contract.name}' is broken")
    return sorted(lines)


def main(argv: list[str]) -> int:
    try:
        contracts = {found for path in argv if (found := contracts_of(Path(path)))}
        found = [line for path in sorted(contracts) for line in findings(path)]
    # Any failure, such as a module grimp cannot parse, means the contracts went unchecked.
    except Exception as error:  # noqa: BLE001
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 2
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
