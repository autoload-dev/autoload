"""RG013: public documentation does not link to internal documentation."""

import posixpath
import re
from collections.abc import Iterable
from html import unescape
from html.parser import HTMLParser
from string import punctuation
from urllib.parse import unquote, urlsplit

from tools.conventions.context import Context, Location
from tools.conventions.framework import Finding, RuleInfo

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


def link_source(text: str) -> str:
    """Hide top-level code blocks, inline code and HTML comments."""
    lines = []
    fence = ""
    for line in text.splitlines(keepends=True):
        marker = FENCE.match(line)
        if fence:
            lines.append(blank(line))
            if (
                marker
                and marker[1][0] == fence[0]
                and len(marker[1]) >= len(fence)
                and not marker[2].strip()
            ):
                fence = ""
        elif marker and (marker[1][0] != "`" or "`" not in marker[2]):
            fence = marker[1]
            lines.append(blank(line))
        elif line.startswith(("    ", "\t")):
            lines.append(blank(line))
        else:
            lines.append(line)
    return LITERAL.sub(lambda match: blank(match[0]), "".join(lines))


def destinations(text: str) -> Iterable[tuple[int, str]]:
    """Yield line numbers and destinations in nonliteral source."""
    source = link_source(text)
    for match in DESTINATION.finditer(source):
        yield source.count("\n", 0, match.start()) + 1, ESCAPE.sub(r"\1", match[1])
    html = HTMLLinks()
    html.feed(source)
    yield from html.destinations


class PublicDocumentationLinks:
    info = RuleInfo(
        "RG013",
        "Public documentation does not link to internal documentation",
        "docs/public/conventions.md#rg013",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        for name in context.workspace.documents:
            # The shared index routes readers to both audiences. Internal reference
            # pages are not consumer documentation.
            if name == "docs/README.md" or name.startswith("docs/internal/"):
                continue
            text = context.workspace.text(name)
            seen: set[tuple[int, str]] = set()
            for line, value in sorted(destinations(text)):
                destination = urlsplit(unescape(value))
                if destination.scheme or destination.netloc or not destination.path:
                    continue
                path = unquote(destination.path)
                resolved = posixpath.normpath(
                    path.lstrip("/")
                    if path.startswith("/")
                    else posixpath.join(posixpath.dirname(name), path)
                )
                if resolved != "docs/internal" and not resolved.startswith(
                    "docs/internal/"
                ):
                    continue
                if (line, resolved) in seen:
                    continue
                seen.add((line, resolved))
                yield Finding(
                    Location(name, line),
                    f"keep public documentation self-contained; remove internal link to {resolved}",
                )
