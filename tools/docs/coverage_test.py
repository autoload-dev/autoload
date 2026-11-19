"""Check real evaluated extractions; arguments are declared Bazel runfile pairs."""

import sys
from pathlib import Path

from tools.docs.coverage import documentation_errors, module_apis, parse_module

if __name__ == "__main__":
    failures = []
    arguments = sys.argv[1:]
    for metadata, source in zip(map(Path, arguments[::2]), map(Path, arguments[1::2])):
        module = parse_module(metadata.read_text())
        errors = documentation_errors(module, source.read_text())
        errors.extend(module_apis(module)[1])
        if errors:
            failures.append(source.as_posix() + ":\n" + "\n".join(errors))
    if failures:
        sys.exit("\n\n".join(failures))
