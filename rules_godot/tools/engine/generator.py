"""Replay an upstream Python generator using only declared action inputs."""

import argparse
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NamedTuple


class Value:
    def __init__(self, value: object) -> None:
        self.value = value

    def read(self) -> object:
        return self.value

    def __str__(self) -> str:
        return str(self.value)


class File(str):
    @property
    def name(self) -> str:
        return Path(self).name

    @property
    def path(self) -> str:
        return str(self)

    def get_contents(self) -> bytes:
        return Path(self).read_bytes()

    def get_text_contents(self) -> str:
        return Path(self).read_text()

    def read(self) -> bytes:
        return self.get_contents()

    @property
    def abspath(self) -> str:
        return str(Path(self).absolute())


class Environment(dict[str, Any]):
    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as error:
            raise AttributeError(name) from error

    def NoCache(self, _targets: object) -> None:
        pass

    def Detect(self, _program: object) -> None:
        # Upstream falls back to its built-in translation reader when gettext
        # is absent. Never run undeclared programs installed on the execution
        # platform from a Bazel action.
        return None


def safe_relative(path: str) -> Path:
    value = Path(path)
    if value.is_absolute() or ".." in value.parts:
        raise ValueError(f"Generator path must stay inside its workspace: {path}")
    return value


def value_of(source: dict[str, Any]) -> object:
    """
    Return a Value source's value, with the fields declared input files supply.

    A field known only at build time, such as a stamped commit, names the input
    file that holds it under "files".
    """
    value = source["value"]
    for key, path in source.get("files", {}).items():
        value[key] = safe_relative(path).read_text()
    return value


class Registration(NamedTuple):
    """Whether an application's build profile is a registered runtime profile, and how to register it."""

    line: str = ""
    registered: bool = False


def _unregistered_options(
    data: Mapping[str, Any], application: Path | None, registration: Registration
) -> list[str]:
    """The build options of an application's profile that no registration allows."""
    if application is None or registration.registered:
        return []
    return sorted(data.get("disabled_build_options") or {})


def with_class_profile(
    spec: dict[str, Any],
    application: Path | None,
    recipe: Path | None,
    registration: Registration | None = None,
) -> dict[str, Any]:
    """
    Return the class generator's specification with the disabled classes of a build profile.

    An application's profile replaces the recipe's own. Build options shape the engine's
    graph, so an application's profile may set them only as a registered runtime profile,
    whose runtime variant has its own graph.
    """
    profile = application or recipe
    if profile is None:
        return spec
    registration = registration or Registration()
    data = json.loads(profile.read_text())
    options = _unregistered_options(data, application, registration)
    if options:
        raise ValueError(
            f"The build profile {application} sets {', '.join(options)}, build "
            "options that need a runtime variant of the engine. Register the profile in "
            f"MODULE.bazel: {registration.line}"
        )
    return spec | {"sources": [{"value": list(data.get("disabled_classes", []))}]}


def run(spec: dict[str, Any], inputs: dict[str, str], outputs: dict[str, str]) -> None:
    original = Path.cwd()
    input_paths = {key: Path(value).absolute() for key, value in inputs.items()}
    output_paths = {key: Path(value).absolute() for key, value in outputs.items()}
    with tempfile.TemporaryDirectory(prefix="godot-generator-") as directory:
        workspace = Path(directory)
        for logical, actual in input_paths.items():
            target = workspace / safe_relative(logical)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(actual, target)
        for logical in outputs:
            (workspace / safe_relative(logical)).parent.mkdir(parents=True, exist_ok=True)
        python_dirs = sorted({str(path.parent) for path in workspace.rglob("*.py")})
        previous_path = sys.path[:]
        try:
            os.chdir(workspace)
            sys.path[:0] = [
                str(workspace / Path(spec["code_file"]).parent),
                str(workspace),
                *python_dirs,
            ]
            if spec.get("inline"):
                import methods

                namespace = {"methods": methods}
                # The inline builder is declared upstream engine source.
                exec(compile(spec["inline"], spec["code_file"], "exec"), namespace)  # noqa: S102
                function = namespace[spec["function"]]
            else:
                module_spec = importlib.util.spec_from_file_location(
                    "_godot_builder", spec["code_file"]
                )
                assert module_spec is not None and module_spec.loader is not None
                module = importlib.util.module_from_spec(module_spec)
                module_spec.loader.exec_module(module)
                function = getattr(module, spec["function"])
            sources = [
                Value(value_of(source)) if "value" in source else File(source["path"])
                for source in spec["sources"]
            ]
            result = function(
                [File(path) for path in spec["targets"]],
                sources,
                Environment(spec.get("environment", {})),
            )
            if result not in (None, 0):
                raise RuntimeError(f"Godot generator returned {result}")
            for logical, actual in output_paths.items():
                generated = workspace / safe_relative(logical)
                if not generated.is_file():
                    raise RuntimeError(f"Godot generator did not produce {logical}")
                actual.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(generated, actual)
        finally:
            sys.path[:] = previous_path
            os.chdir(original)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--output", action="append", default=[])
    # The build profiles of the class generator: the application's, then the recipe's.
    parser.add_argument("--class-profile", type=Path)
    parser.add_argument("--recipe-profile", type=Path)
    # Whether the application's profile is a registered runtime profile, and the
    # MODULE.bazel line that registers it.
    parser.add_argument("--registered-profile", action="store_true")
    parser.add_argument("--registration", default="")
    args = parser.parse_args()
    run(
        with_class_profile(
            json.loads(Path(args.spec).read_text()),
            args.class_profile,
            args.recipe_profile,
            Registration(args.registration, args.registered_profile),
        ),
        dict(value.split("=", 1) for value in args.input),
        dict(value.split("=", 1) for value in args.output),
    )


if __name__ == "__main__":
    main()
