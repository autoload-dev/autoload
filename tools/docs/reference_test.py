"""Compare the assembled primary reference tree with its committed representation."""

import sys
from pathlib import Path

from tools.docs.api_docs import reference_errors

if __name__ == "__main__":
    generated, manifest = map(Path, sys.argv[1:])
    errors = reference_errors(manifest.parent, generated)
    if errors:
        sys.exit("\n".join(errors) + "\nRun bazel run //tools/docs.")
