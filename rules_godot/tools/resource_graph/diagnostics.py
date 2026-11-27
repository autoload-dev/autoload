"""
The errors and warnings that the resource graph and pack selection report, with the file and
line they concern, and how the tools sort and print them.
"""


def diagnostic(code: str, path: str, message: str, line: int = 0) -> dict:
    """An error finding; warning has the same fields with that severity."""
    return {
        "code": code,
        "path": path,
        "line": line,
        "severity": "error",
        "message": message,
    }


def warning(code: str, path: str, message: str, line: int = 0) -> dict:
    return dict(diagnostic(code, path, message, line), severity="warning")


def format_diagnostic(item: dict) -> str:
    return "{path}:{line}: {severity}: {code}: {message}".format(**item)


def sorted_diagnostics(diagnostics: list[dict]) -> list[dict]:
    return sorted(
        diagnostics,
        key=lambda item: (item["path"], item["line"], item["code"], item["message"]),
    )


class Findings:
    """Collects the findings of a pass over the files of a project."""

    def __init__(self) -> None:
        self.diagnostics: list[dict] = []

    def error(self, code: str, path: str, message: str, line: int = 0) -> None:
        self.diagnostics.append(diagnostic(code, path, message, line))

    def warn(self, code: str, path: str, message: str, line: int = 0) -> None:
        self.diagnostics.append(warning(code, path, message, line))
