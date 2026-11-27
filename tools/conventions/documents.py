"""Documentation evidence: which documentation is internal, and the local links of Markdown."""

import posixpath
import re
from collections.abc import Iterable
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from string import punctuation
from urllib.parse import unquote, urlsplit

from tools.conventions.layout import DOCS

# The ruleset's internal pages live beside its public guides.
INTERNAL_DOCS = tuple(f"{docs}internal/" for docs in DOCS)

# Static Markdown links/images and reference definitions. HTML attributes are
# inspected only inside tags, not link-like prose. This is a local source check,
# not a Markdown renderer; nested block containers need review (see the catalogue).
DESTINATION = re.compile(
    r"""(?:\]\(\s*<?|^ {0,3}\[[^\]\n]+\]:\s*<?)"""
    r"""([^\s<>"')]+)""",
    re.MULTILINE,
)
ESCAPE = re.compile(r"\\([" + re.escape(punctuation) + r"])")
LITERAL = re.compile(r"<!--.*?(?:-->|\Z)|(?<!\\)(`+)(?!`)(.*?)(?<!`)\1(?!`)", re.DOTALL)
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def internal_document(path: str) -> bool:
    """Whether a repository-relative path is internal documentation or one of its directories."""
    return f"{path}/".startswith(INTERNAL_DOCS)


class HTMLLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.destinations: list[tuple[int, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name in {"href", "src"} and value is not None:
                self.destinations.append((self.getpos()[0], value))


def blank(text: str) -> str:
    """Preserve source offsets and line numbers while hiding literal content."""
    return re.sub(r"[^\n]", " ", text)


def opening_fence(line: str) -> str:
    """The fence a line opens, or an empty string."""
    marker = FENCE.match(line)
    if not marker:
        return ""
    # A backtick fence's info string contains no backtick.
    backticks = marker[1].startswith("`")
    return "" if backticks and "`" in marker[2] else marker[1]


def closes(line: str, fence: str) -> bool:
    """Whether a line closes the open fence: the same character, at least as long."""
    marker = FENCE.match(line)
    if not marker or marker[2].strip():
        return False
    return marker[1][0] == fence[0] and len(marker[1]) >= len(fence)


def block_source(text: str) -> str:
    """Hide top-level fenced and indented code blocks."""
    lines = []
    fence = ""
    for line in text.splitlines(keepends=True):
        if fence:
            fence = "" if closes(line, fence) else fence
            lines.append(blank(line))
            continue
        fence = opening_fence(line)
        hidden = fence or line.startswith(("    ", "\t"))
        lines.append(blank(line) if hidden else line)
    return "".join(lines)


def link_source(text: str) -> str:
    """Hide top-level code blocks, inline code and HTML comments."""
    return LITERAL.sub(lambda match: blank(match[0]), block_source(text))


def destinations(text: str) -> Iterable[tuple[int, str]]:
    """Yield line numbers and destinations in nonliteral source."""
    source = link_source(text)
    for match in DESTINATION.finditer(source):
        yield source.count("\n", 0, match.start()) + 1, ESCAPE.sub(r"\1", match[1])
    html = HTMLLinks()
    html.feed(source)
    yield from html.destinations


@dataclass(frozen=True)
class Link:
    """A local link: its line and the repository-relative path it resolves to."""

    line: int
    path: str


def local_links(name: str, text: str) -> Iterable[Link]:
    """
    Yield the local links of the document ``name``, resolved against its directory; a
    fragment-only link resolves to the document itself. External URLs are skipped.
    """
    for line, value in sorted(destinations(text)):
        destination = urlsplit(unescape(value))
        if destination.scheme or destination.netloc:
            continue
        path = unquote(destination.path)
        if not path:
            resolved = name
        elif path.startswith("/"):
            resolved = posixpath.normpath(path.lstrip("/"))
        else:
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), path))
        yield Link(line, resolved)
