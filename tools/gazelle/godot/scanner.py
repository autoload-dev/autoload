"""
The scanner of Gazelle's Godot language: reads the references of Godot files with the
ruleset's resource graph scanner, for the language's Go code, which starts it once per run.

Each line on stdin is a request, `{"files": [{"file": <absolute path>, "path": <res://
path>}, ...]}`, and each line on stdout its answer, `{"files": [<scan>, ...]}` in the same
order. A scan holds the UIDs a file authors, the global classes it declares, the class it
extends by name, the references it makes at load time (`{"kind": "res"|"uid"|"class",
"value": ...}`), the res:// paths it reads at runtime and the files its importer reads. A
C++ source's scan holds the classes it registers with Godot instead.
"""

import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import IO

from tools.resource_graph import ANALYZED_FORMATS, file_references

# The kinds of the graph's references that a file's importer reads and that code reads at
# runtime; every other kind with a target loads it with the file.
_IMPORT_KINDS = frozenset({"gltf_buffers", "gltf_images"})
_RUNTIME_KINDS = frozenset({"file_access"})

_NATIVE_FORMATS = frozenset({".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp"})

# How an extension registers a class with Godot's ClassDB: godot-cpp's and a module's
# register_class templates and the engine's GDREGISTER macros.
_REGISTRATION = re.compile(
    r"register_(?:abstract_|internal_|runtime_|virtual_)?class<\s*(\w+)\s*>"
    r"|GDREGISTER_(?:ABSTRACT_|INTERNAL_|RUNTIME_|VIRTUAL_)?CLASS\(\s*(\w+)\s*\)"
)


def _empty() -> dict:
    return {
        "uids": [],
        "classes": [],
        "extends": None,
        "refs": [],
        "runtime": [],
        "members": [],
    }


def _load_references(found: dict) -> list[dict]:
    """The references a file makes when Godot loads it: paths, UIDs and class names."""
    refs = []
    for item in found["references"]:
        if item["kind"] in _IMPORT_KINDS | _RUNTIME_KINDS:
            continue
        if item["path"]:
            refs.append({"kind": "res", "value": item["path"]})
        if item["uid"]:
            refs.append({"kind": "uid", "value": item["uid"]})
    refs.extend({"kind": "class", "value": name} for name in found["names"])
    return refs


def _paths(found: dict, kinds: Iterable[str]) -> list[str]:
    return sorted(
        {
            item["path"]
            for item in found["references"]
            if item["kind"] in kinds and item["path"]
        }
    )


def scan(path: str, text: str) -> dict:
    """The scan of one file at a res:// path, by its format."""
    suffix = PurePosixPath(path).suffix.lower()
    result = _empty()
    if suffix in _NATIVE_FORMATS:
        result["classes"] = sorted(
            {"".join(match) for match in _REGISTRATION.findall(text)}
        )
    elif suffix in ANALYZED_FORMATS:
        found = file_references(path, text)
        result.update(
            uids=found["uids"],
            classes=found["classes"],
            extends=found["extends"],
            refs=_load_references(found),
            runtime=_paths(found, _RUNTIME_KINDS),
            members=_paths(found, _IMPORT_KINDS),
        )
    return result


def _read(file: str, path: str) -> dict:
    """The scan of a file on disk; one that cannot be read or is no text scans empty."""
    suffix = PurePosixPath(path).suffix.lower()
    if suffix not in ANALYZED_FORMATS | _NATIVE_FORMATS:
        return _empty()
    try:
        text = Path(file).read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return _empty()
    return scan(path, text)


def serve(requests: IO[str], answers: IO[str]) -> None:
    """Answer each request line with one line, until the input ends."""
    for line in requests:
        request = json.loads(line)
        files = [_read(item["file"], item["path"]) for item in request["files"]]
        answers.write(json.dumps({"files": files}) + "\n")
        answers.flush()


if __name__ == "__main__":
    serve(sys.stdin, sys.stdout)
