"""The applications of examples/ and what their app.pkl says about them."""

from dataclasses import dataclass
from pathlib import Path

from tools.pkl.evaluate import evaluate, manifest
from tools.setup.modules import EXAMPLES

ROOT = Path(__file__).resolve().parents[2]
# The schema every examples/<name>/app.pkl amends, and the line an app.pkl starts with.
SCHEMA = Path(__file__).resolve().parent / "App.pkl"
AMENDS = 'amends "../../tools/apps/App.pkl"'


def lanes() -> tuple[str, ...]:
    """The lanes an application may name, as the schema's Lane union lists them."""
    return tuple(evaluate(SCHEMA, "choices")["lanes"])


@dataclass(frozen=True)
class Application:
    """One application, a project directly in examples/, as its app.pkl declares it."""

    name: str
    lanes: tuple[str, ...]

    @property
    def package(self) -> str:
        return f"//{(EXAMPLES / self.name).as_posix()}"

    @classmethod
    def load(cls, path: Path) -> Application:
        """Read the app.pkl at `path`, as Pkl evaluates it."""
        value = manifest(path, AMENDS)
        return cls(path.parent.name, tuple(value["lanes"]))


def applications(root: Path = ROOT) -> tuple[Application, ...]:
    """Every application of the checkout that has an app.pkl, by name."""
    return tuple(map(Application.load, sorted((root / EXAMPLES).glob("*/app.pkl"))))
