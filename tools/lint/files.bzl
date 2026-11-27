"""
The file lint's tools (files.py), each under the variable that holds the runfiles path of its
executable: //tools/lint:files sets them as its `env`, and //tools/format:fix, which runs it
as a rules_multirun command, which passes no `env` on, as its `environment`.
"""

FILE_TOOLS = {
    "CLANG_FORMAT": "//tools/lint:clang_format",
    "CONVENTIONS": "//tools/conventions:files",
    "GDLINT": "//tools/lint:gdscript",
    "IMPORT_LINTER": "//tools/lint:imports",
    "RUMDL": "@multitool//tools/rumdl",
    "SHELLCHECK": "@multitool//tools/shellcheck",
}

FILE_TOOL_PATHS = {name: "$(rlocationpath %s)" % tool for name, tool in FILE_TOOLS.items()}
