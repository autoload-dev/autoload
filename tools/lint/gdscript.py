"""
The GDScript lint, which the file lint runs as gdlint (files.py): gdlint's checks with the rules
that a .gdlintrc keeps, on the given scripts; it prints each problem and exits 1 on any.
`gdscript.py <.gdlintrc> <script>...`
"""

import sys
import tempfile
from pathlib import Path
from types import MappingProxyType

import lark
import yaml
from gdtoolkit.linter import DEFAULT_CONFIG, lint_code
from gdtoolkit.parser import parser

# gdtoolkit caches its compiled grammars below the user's home, which a Bazel test's sandbox
# mounts read-only on Linux. It always writes the cache, even with disable_grammar_caching(), so
# the cache goes to a temporary directory of its own.
parser._cache_dirpath = tempfile.mkdtemp(prefix="gdtoolkit")

# Scripts that are not checked, by their path in the ruleset's module, each with its reason.
EXCLUDED = (
    # The validation's fixtures exercise the forms GDScript allows, such as `extends` before
    # `class_name`, a doc string before them and a property beside the variable that backs it.
    "godot/private/tests/validation/fixtures/classes/docfirst.gd",
    "godot/private/tests/validation/fixtures/classes/noext.gd",
    "godot/private/tests/validation/fixtures/interface/base/base.gd",
    # A script the validation must reject because it does not parse.
    "godot/private/tests/validation/fixtures/script_errors/parse_error.gd",
)


def configuration(path: Path) -> MappingProxyType:
    """A .gdlintrc's rules, with gdlint's defaults for those it leaves out."""
    return MappingProxyType(
        {**DEFAULT_CONFIG, **(yaml.safe_load(path.read_text()) or {})}
    )


def problems(script: str, config: MappingProxyType) -> list[str]:
    """gdlint's problems of a script, as gdlint prints them; one where it does not parse."""
    try:
        found = lint_code(Path(script).read_text(), config)
    except lark.exceptions.LarkError as error:
        return [f"{script}: Error: does not parse: {error}"]
    return [
        f"{script}:{problem.line}: Error: {problem.description} ({problem.name})"
        for problem in found
    ]


def main(config: str, *scripts: str) -> int:
    rules = configuration(Path(config))
    found = [
        line
        for script in scripts
        if not script.endswith(EXCLUDED)
        for line in problems(script, rules)
    ]
    print("\n".join(found))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
