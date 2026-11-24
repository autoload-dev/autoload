"""RG013: public documentation does not link to internal documentation."""

from collections.abc import Iterable

from tools.conventions.context import Context, Location
from tools.conventions.documents import internal_document, local_links
from tools.conventions.framework import Finding, RuleInfo


class PublicDocumentationLinks:
    info = RuleInfo(
        "RG013",
        "Public documentation does not link to internal documentation",
    )

    def evaluate(self, context: Context) -> Iterable[Finding]:
        for name in context.workspace.documents:
            # The shared index routes readers to both audiences. Internal reference
            # pages are not consumer documentation.
            if name == "docs/README.md" or internal_document(name):
                continue
            # Several links on one line to the same page are one finding.
            targets = {
                (link.line, link.path)
                for link in local_links(name, context.workspace.text(name))
                if internal_document(link.path)
            }
            for line, path in sorted(targets):
                yield Finding(
                    Location(name, line),
                    f"keep public documentation self-contained; remove internal link to {path}",
                )
