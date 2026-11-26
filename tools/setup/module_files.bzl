"""
The files of every module the root module overrides with a directory of the checkout, which
the setup checks' tests declare as data and copy to their directories (checkout.py).
"""

load("//:addons.bzl", "ADDON_REPOSITORIES")

MODULE_FILES = [
    "//:module_files",
    "@autoload_rules_godot//:module_files",
] + [repository + "//:module_files" for repository in ADDON_REPOSITORIES]
