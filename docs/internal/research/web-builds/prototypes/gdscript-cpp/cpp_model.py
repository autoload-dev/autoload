"""The project's classes as the C++ generator sees them, and a function being compiled."""

from dataclasses import dataclass, field

from cpp_engine import Engine
from cpp_types import c_type, gd_type


@dataclass
class Program:
    """All classes of the project, and which functions compile to C++."""

    classes: dict[str, Klass] = field(default_factory=dict)
    compiled: set[tuple[str, str]] = field(default_factory=set)
    engine: Engine | None = None
    # Engine classes whose headers direct calls need, and the bindings they call.
    used_classes: set[str] = field(default_factory=set)
    direct: set[str] = field(default_factory=set)
    # Operators evaluated at run time: (operator, left type, right type).
    operators: set[tuple[str, str, str]] = field(default_factory=set)

    def member(self, fqcn: str, name: str) -> dict[str, int]:
        """The member indices of a class that has the member, or none."""
        klass = self.classes.get(fqcn)
        return klass.member_indices if klass and name in klass.member_indices else {}

    def functions(self, fqcn: str) -> dict[str, dict]:
        klass = self.classes.get(fqcn)
        return klass.functions if klass else {}


@dataclass
class Klass:
    fqcn: str
    member_indices: dict[str, int]
    member_types: dict[str, str]
    functions: dict[str, dict]
    symbol: str
    program: Program = field(default_factory=Program)
    native: str = ""


@dataclass
class Function:
    """A function being compiled: its C++ lines and what its locals are."""

    klass: Klass
    node: dict
    lines: list[str] = field(default_factory=list)
    locals: dict[str, str] = field(default_factory=dict)
    # C++ local of a script-typed local -> the C++ local caching its GDScript instance.
    instances: dict[str, str] = field(default_factory=dict)
    temp: int = 0
    depth: int = 1

    @property
    def program(self) -> Program:
        return self.klass.program

    def emit(self, line: str) -> None:
        self.lines.append("\t" * self.depth + line)

    def fresh(self, stem: str) -> str:
        self.temp += 1
        return f"{stem}_{self.temp}"


def function_symbol(klass: Klass, name: str) -> str:
    return f"{klass.symbol}_{name.replace('@', '_')}"


def signature(klass: Klass, f: dict) -> str:
    params = ", ".join(
        f"{c_type(gd_type(p['type']))} l_{p['name']}" for p in f["parameters"]
    )
    head = f"GDScriptInstance *p_self{', ' if params else ''}{params}"
    return f"static {c_type(gd_type(f['return']))} {function_symbol(klass, f['name'])}({head})"
