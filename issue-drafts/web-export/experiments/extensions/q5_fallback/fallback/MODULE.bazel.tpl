module(name = "web_cc_fallback")

bazel_dep(name = "platforms", version = "1.1.0")

# What a ruleset would register: C++ for the web is incompatible unless a real toolchain
# resolves first.
register_toolchains("//:{VARIANT}")
