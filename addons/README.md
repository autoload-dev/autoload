# Add-ons

Godot add-ons of autoload-dev, built with the rules of this repository and consumed by Godot
applications through Bazel. Every add-on brings its native SDKs.

Each directory here is a Bazel module of its own, with its own `MODULE.bazel`, version and
release tags:

| Module | Directory | Add-ons | Version |
| --- | --- | --- | --- |
| `autoload_firebase` | [`firebase/`](firebase) | Firebase Core, Analytics | 0.1.0 |

There is one module per add-on, or per group of add-ons that must be versioned together, like
the Firebase add-ons, which share one Firebase SDK. Each module keeps its example applications in
its `examples/` directory: a root module that consumes the add-on like an external application.

## Use in an application

The add-on modules are not published to the Bazel Central Registry yet. Depend on a commit of
this repository, with the module's directory as `strip_prefix`:

```starlark
bazel_dep(name = "autoload_firebase", version = "0.1.0")
archive_override(
    module_name = "autoload_firebase",
    integrity = "sha256-...",
    strip_prefix = "rules_godot-<commit>/addons/firebase",
    urls = ["https://github.com/autoload-dev/rules_godot/archive/<commit>.tar.gz"],
)
```

The add-ons need a rules_godot that matches them: use an override for `autoload_rules_godot`
at the same commit until a release has what they need.

## Releases

Every module is released on its own, with tags named `<module>-v<version>`, such as
`autoload_firebase-v0.1.0`. The tag's commit has the same `version` in the module's
`MODULE.bazel`.
