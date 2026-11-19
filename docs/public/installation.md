# Installation

Add rules_godot to a Bazel module, register a Godot engine and set the Bazel options the
rules rely on. The [README](../../README.md#quick-start) shows the shortest path; this page
explains each part.

## Requirements

- Bazel 9 or later. rules_godot declares `bazel_compatibility = [">=9.0.0"]`.
- Godot >=4.7.2 and <5.0.0. Bazel downloads the editor and export templates; no globally
  installed Godot is needed.
- A Linux or macOS host with a native C/C++ toolchain: GCC or Clang on Linux, Xcode Command
  Line Tools on macOS. Android and iOS packaging need their SDKs, see
  [Application platforms](platforms.md).

## Add the module

Add the dependency and register an engine in your root `MODULE.bazel`:

```starlark
bazel_dep(name = "rules_godot", version = "0.1.0")

godot_engines = use_extension("@rules_godot//godot:extensions.bzl", "godot_engines")
godot_engines.prebuilt(name = "godot", version = "4.7.2")
use_repo(godot_engines, "godot")
register_toolchains("@godot//toolchains:all")
```

Register the engines in the consuming root module; the ruleset's own development engines
are a development dependency. [Engines](engine.md) covers source builds and replacing
single slots, [Versions](versions.md) version ranges and exact pins.

### Use an unreleased revision

To build against a commit that is not in the Bazel Central Registry, keep the `bazel_dep`
and add an override. For a shared build, pin a reviewed full commit SHA:

```starlark
git_override(
    module_name = "rules_godot",
    remote = "https://github.com/autoload-dev/rules_godot.git",
    commit = "<full commit SHA>",
)
```

An `archive_override` with an integrity digest works as well. To work on rules_godot beside
your project, use a local checkout:

```starlark
local_path_override(module_name = "rules_godot", path = "../rules_godot")
```

## Bazel options

Add these lines to your module's `.bazelrc`:

```text
build --incompatible_exclude_starlark_flags_from_exec_config
common --experimental_output_paths=strip
common --modify_execution_info=(?!Godot).*=-supports-path-mapping
```

The first line keeps application settings such as `--@rules_godot//godot:app_version` from
rebuilding compilers and code generators for the execution platform. It is needed while
your Bazel version leaves the flag off, as Bazel 9 does;
[bazelbuild/bazel#26909](https://github.com/bazelbuild/bazel/issues/26909) makes it the
default in Bazel 10.

The other two lines make a project's imports, validations and class fragments run once for
all target configurations, such as a host test and an Android application, instead of once
for each. Bazel's path mapping shares these actions through a disk or remote cache. It needs
sandboxed or remote execution: with `--spawn_strategy=local` these actions fail to find a
strategy. The pattern keeps it to the actions rules_godot opts in; other rules' mnemonics
you want mapped, such as rules_android's `DexBuilder` and `Desugar`, join the list.

## Editor views

`bazel run` of a `godot_editor` target opens the project in the Godot editor, and what you
save there changes your checkout. Add this line to your `.bazelignore` before the first
editor view:

```text
.godot-editor
```
