# Report the extension libraries an application lacks on its platform

New issue; a prerequisite of #198 that applies to every export platform. Builds on the
issue that splits the extension rules into their primitives.

---

## Goal

An application says which of its add-ons have no extension library for the platform it is
built for, and the build either stops there or goes on without them, as the developer
chooses. Today the outcome depends on how the add-on is written: a `select()` branch of
`None` ships the application without the library and says nothing, and a `select()` without
a branch for the platform stops the analysis of every target that reaches it, wildcard
builds included.

The web makes this common. An application is worth exporting for the browser before each
of its add-ons supports it, to see what works.

## Decisions

- **Absence is information, not incompatibility.** Bazel's incompatibility spreads to
  everything that depends on a target and no setting can relax it, so one add-on without a
  web library would make the whole application unbuildable for the web.
- **One way to leave a platform out.** An extension has no library where the branch of
  its `library` is `None`, whether its libraries are prebuilt or built from source.
- **The application reports and decides.** By default a missing extension library fails
  the build and names the add-on and the platform. A setting builds the application
  without it and lists what is missing.
- **An application's own platforms stay explicit.** One that is not meant for a platform
  says so with `target_compatible_with`, and a wildcard build for that platform skips it.

## API

### An extension without a library for a platform

Unchanged for the author: a branch of `None`. What changes is that the extension passes
this on, so every application that reaches it can report it.

```starlark
godot_extension(
    name = "platform_paths",
    library = select({
        "@platforms//os:android": ":paths_library",
        "@platforms//os:ios": ":paths_library",
        "@platforms//os:linux": ":paths_library",
        "@platforms//os:macos": ":paths_library",
        # No library elsewhere, such as on the web.
        "//conditions:default": None,
    }),
)
```

The library and its sources are not analyzed where the branch is `None`. A `select()`
without a matching branch stays Bazel's analysis error.

`godot_cc_extension` has no way to leave a platform out. It has a library on every
platform `godot_extension_library` links for, and none on the others: the web, until web
extensions exist.

### The setting

A build setting and an attribute of the same name, as `engine_optimize` has both. The
attribute is the application's own choice; the flag, when given, overrides it for one
invocation.

```starlark
godot_app(
    name = "app",
    pack = ":pack",
    application_id = "com.example.mygame",
    # "error" (default) or "report".
    missing_extension_libraries = "report",
)
```

```sh
# See what a web build of the application does without the add-ons that lack one.
bazel run //path/to:app \
    --platforms=@autoload_rules_godot//godot/platforms:web_wasm32 \
    --@autoload_rules_godot//godot:missing_extension_libraries=report
```

With `error`, analysis fails:

```
//game:app: no extension library for web_wasm32 in:
  @autoload_sentry//sentry (used by //game:main)
  @autoload_sqlite//sqlite (used by //game/save:save)
Build it for a platform these add-ons support, select other add-ons for this platform, or
pass --@autoload_rules_godot//godot:missing_extension_libraries=report to build without them.
```

With `report`, the application builds without those libraries, prints the same list as a
warning and writes it to a file among its outputs. Scripts that use a class of a missing
extension fail at run time; their content validation reports instead of failing.

### Other add-ons per platform

No new API: a `select()` in the `deps` of the resources that use the add-on.

```starlark
godot_resources(
    name = "save",
    srcs = ["save.gd"],
    deps = select({
        "@autoload_rules_godot//godot/platforms:is_web": [":browser_storage"],
        "//conditions:default": ["@autoload_sqlite//sqlite"],
    }),
)
```

### An application that is not for a platform

Unchanged, as the platform guide shows for desktop applications:

```starlark
godot_app(
    name = "app",
    pack = ":pack",
    application_id = "com.example.mygame",
    target_compatible_with = select({
        "@platforms//os:emscripten": ["@platforms//:incompatible"],
        "//conditions:default": [],
    }),
)
```

## Established by experiment

- An add-on whose `select()` has no branch for the web and uses `no_match_error`, as
  `addons/sentry` does, fails analysis there, in a wildcard build too.
- A branch of `None` ships the application without the library and without a message.
- A rule cannot make itself incompatible from its implementation, and a macro cannot read
  the keys of a `select()`.

## Open

- How content validation tells an error caused by a missing extension's class from any
  other, so that `report` relaxes only those.
- Whether the editor variant and source runs take the same setting.
