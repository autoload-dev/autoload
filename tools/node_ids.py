"""
Give the nodes a text scene declares the stable unique_id Godot 4.7 saves.

Godot assigns a random ID to every node a scene declares without one, and the
export writes it into the PCK, so two exports differ. A node the scene declares
has a type, an instance or an instance placeholder, or is the scene's root;
other node entries override a node of an instanced scene, which owns its ID.
The ID derives from the scene's res:// path and the node's path, so every
checkout writes the same one, and a build adds the same one to the scenes it
exports.
"""

import hashlib
from collections.abc import Iterator

from tools.resource_graph import headings

# Godot writes these attributes before unique_id, in this order.
_LEADING = ("name", "type", "parent", "index")
_DECLARING = ("type", "instance", "instance_placeholder")


def _nodes(text: str) -> Iterator[tuple[dict[str, str], str, int]]:
    """Yield each node heading's attribute values, node path and unique_id offset."""
    for heading in headings(text):
        if heading.section != "node":
            continue
        values = heading.attrs
        parent, name = values.get("parent"), values.get("name", "")
        path = "." if parent is None else name if parent == "." else f"{parent}/{name}"
        leading = [end for key, end in heading.ends.items() if key in _LEADING]
        yield values, path, max(leading, default=heading.end)


def _declared(values: dict[str, str]) -> bool:
    return "parent" not in values or any(key in values for key in _DECLARING)


def node_id(scene: str, path: str, taken: set[int]) -> int:
    """Return the ID of the node at path in scene, avoiding the IDs taken."""
    attempt = 0
    while True:
        seed = f"{scene}\0{path}\0{attempt}".encode()
        identity = int.from_bytes(hashlib.sha256(seed).digest()[:4], "big") & 0x7FFFFFFF
        if identity and identity not in taken:
            return identity
        attempt += 1


def missing_node_ids(text: str) -> list[str]:
    """Return the paths of the declared nodes without unique_id, the root by its name."""
    return [
        values.get("name", "") if path == "." else path
        for values, path, _ in _nodes(text)
        if _declared(values) and "unique_id" not in values
    ]


def with_node_ids(text: str, scene: str) -> str:
    """Return text with a unique_id for each declared node that has none."""
    nodes = list(_nodes(text))
    taken = {int(values["unique_id"]) for values, _, _ in nodes if "unique_id" in values}
    parts = []
    start = 0
    for values, path, position in nodes:
        if not _declared(values) or "unique_id" in values:
            continue
        identity = node_id(scene, path, taken)
        taken.add(identity)
        parts += [text[start:position], f" unique_id={identity}"]
        start = position
    return "".join(parts) + text[start:]
