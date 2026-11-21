"""Verify the curated BCR metadata contains public primary contracts exactly once."""

import sys
from pathlib import Path

from stardoc.proto import stardoc_output_pb2

from tools.docs.api_docs import read_inventory
from tools.docs.surface import exports, normalize_label

if __name__ == "__main__":
    inventory = read_inventory(Path(sys.argv[1]))
    seen = {}
    modules = set()
    for filename in (path for argument in sys.argv[2:] for path in argument.split()):
        metadata = stardoc_output_pb2.ModuleInfo.FromString(Path(filename).read_bytes())
        label = normalize_label(metadata.file)
        assert label in inventory["PUBLIC_APIS"], (
            f"Non-public metadata in BCR artifact: {label}"
        )
        assert label not in modules, f"Duplicate module in BCR metadata: {label}"
        modules.add(label)
        symbols = exports(label, metadata)
        assert set(symbols) == set(inventory["PUBLIC_APIS"][label]["symbols"]), label
        for export in symbols.values():
            assert export.identity[1] not in inventory["CROSS_REPOSITORY_MODULES"], (
                f"Implementation helper in BCR metadata: {export}"
            )
            assert export.identity not in seen, (
                f"Duplicate BCR primary: {seen.get(export.identity)} and {export}"
            )
            seen[export.identity] = export
    assert modules == set(inventory["PUBLIC_APIS"]), (
        "Missing public entrypoints in BCR metadata"
    )
