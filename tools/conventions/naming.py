"""Name spellings shared by the naming rules."""

import re

# Package segments (RG001) and ordinary target names (RG002).
LOWER_SNAKE_CASE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
