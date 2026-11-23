"""
Check real evaluated extractions and their ownership.

Arguments: the modules.bzl manifest, then declared Bazel runfile pairs of each public
entrypoint's complete extraction and its source.
"""

import sys
from pathlib import Path

from tools.docs.api_docs import read_inventory
from tools.docs.coverage import documentation_errors, module_apis, parse_module
from tools.docs.surface import assign_surface, normalize_label

if __name__ == "__main__":
    manifest, *arguments = sys.argv[1:]
    failures = []
    modules = {}
    for metadata, source in zip(map(Path, arguments[::2]), map(Path, arguments[1::2])):
        module = parse_module(metadata.read_text())
        modules[normalize_label(module.file)] = module
        errors = documentation_errors(module, source.read_text())
        errors.extend(module_apis(module)[1])
        if errors:
            failures.append(source.as_posix() + ":\n" + "\n".join(errors))
    try:
        assign_surface(read_inventory(Path(manifest)), modules)
    except ValueError as error:
        failures.append(str(error))
    if failures:
        sys.exit("\n\n".join(failures))
