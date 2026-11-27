# Add-ons

Godot add-ons of autoload-dev, built with the rules of this repository and consumed by Godot
applications through Bazel. Every add-on brings its native SDKs.

Each directory here is a Bazel module of its own, `addons/<module>` named `autoload_<module>`,
with its own `MODULE.bazel`, version, release tags and a README that describes its add-ons:

- [Firebase](firebase/README.md): Firebase Core, Analytics and Cloud Firestore on Android and iOS.
- [GdUnit](gdunit/README.md): GdUnit4 test suites as Bazel tests.
- [Sentry](sentry/README.md): crash and error reporting on Android, iOS, Linux and macOS.

There is one module per add-on, or per group of add-ons that must be versioned together
because they share one SDK. Each module's example applications live in
[`examples/addons/<module>/`](../examples/addons) of the repository's root module, which
consumes the add-ons like an external application.

## Use in an application

Depend on the module's release, as its README shows:

```starlark
bazel_dep(name = "autoload_<module>", version = "0.1.0")
```

Before a module is on the Bazel Central Registry, the release notes of its tag show the
`archive_override` that fetches the release's archive. To use a commit instead, take the
module's directory as `strip_prefix`:

```starlark
archive_override(
    module_name = "autoload_<module>",
    integrity = "sha256-...",
    strip_prefix = "autoload-<commit>/addons/<module>",
    urls = ["https://github.com/autoload-dev/autoload/archive/<commit>.tar.gz"],
)
```

The add-ons need a rules_godot that matches them: use an override for `autoload_rules_godot`
at the same commit until a release has what they need.

Every module and the third-party libraries it builds in declare their identity (PURL) and
license as [package metadata](https://github.com/bazel-contrib/supply-chain). SBOM and
license tools such as `@supply_chain_tools` read it from an application's build graph, so a
software bill of materials of a pack or an application lists the add-ons it contains. An
application writes one as SPDX from its `godot_pack`:

```starlark
load("@supply_chain_tools//sbom:sbom.bzl", "sbom")
load("@supply_chain_tools//sbom:spdx.bzl", "spdx")

sbom(
    name = "sbom",
    target = ":pack",
)

spdx(
    name = "spdx",
    sbom = ":sbom",
)
```

## A new add-on

`bazel run //tools/addons:new -- <module>` creates a module with one add-on, and
`bazel run //tools/addons:new -- <module> --addon <addon>` adds an add-on to a module. Both
write from the template in
[tools/addons/template](../tools/addons/template), which builds on Android, iOS, the editor
and desktop from the start. The [add-on guidance](AGENTS.md) describes the layout.

## Releases

Every module is released on its own, with a tag `autoload_<module>-v<version>` whose release
notes show the `bazel_dep` to add.
