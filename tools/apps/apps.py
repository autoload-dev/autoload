"""The applications of examples/ and what their app.pkl says about them."""

from dataclasses import dataclass
from pathlib import Path

from tools.pkl.evaluate import evaluate

ROOT = Path(__file__).resolve().parents[2]
# The schema every examples/<name>/app.pkl amends.
SCHEMA = Path(__file__).resolve().parent / "App.pkl"
EXAMPLES = Path("examples")


@dataclass(frozen=True)
class Application:
    """One application, a project directly in examples/, as its app.pkl declares it."""

    name: str
    lanes: tuple[str, ...]
    config: str | None = None

    @property
    def package(self) -> str:
        return f"//{(EXAMPLES / self.name).as_posix()}"

    @property
    def flags(self) -> str:
        """The flags every command of the application takes."""
        return f" --config={self.config}" if self.config else ""

    @classmethod
    def load(cls, path: Path) -> Application:
        """Read the app.pkl at `path`, as Pkl evaluates it."""
        value = evaluate(path)
        # Pkl renders no null property, such as an unset config.
        return cls(path.parent.name, tuple(value["lanes"]), value.get("config"))


def applications(root: Path = ROOT) -> tuple[Application, ...]:
    """Every application of the checkout that has an app.pkl, by name."""
    return tuple(map(Application.load, sorted((root / EXAMPLES).glob("*/app.pkl"))))
