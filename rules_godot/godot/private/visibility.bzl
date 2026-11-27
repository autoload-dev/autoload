"""The visibility of targets that only their technical users must see."""

visibility("//...")

# Visible to every package, but no supported API: a consumer's targets through the ruleset's
# macros, a generated repository or the repository's own tooling in its root module must reach
# the target, and Bazel cannot name the packages of another repository in a visibility. Each
# target that uses it says who needs it. rules_python marks such targets the same way
# (python/private/visibility.bzl).
NOT_ACTUALLY_PUBLIC = ["//visibility:public"]
