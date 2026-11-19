"""Read the pack and a runtime-only data file; the analysis tests never run it."""

import sys
from pathlib import Path

if __name__ == "__main__":
    sys.exit(0 if all(Path(path).is_file() for path in sys.argv[1:]) else 1)
