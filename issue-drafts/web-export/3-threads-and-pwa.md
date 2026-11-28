# Support threads and progressive web apps on the web

Sub-issue of #88. An attempt: if threads prove unreliable, the issue records why and the
progressive web app can land alone.

---

## Goal

An application can target the web with threads, and a web application can be a progressive
web app as Godot exports one. Together they reach parity with the choices of Godot's web
export, and they belong together: threads need cross-origin isolation, and on a host that
sets no headers, such as GitHub Pages, only the progressive web app's service worker
provides it.

## Scope

- **A second web export platform with threads.** Threads are a property of the target
  platform, not a flag: they change the ABI of extensions, the engine's feature tags and
  what the host must serve.
- **Prebuilt runtimes with threads**, in both variants, for both Godot versions.
- **`bazel run`** for the threaded platform; the local server sends the isolation headers.
- **The progressive web app** as Godot's export options describe it, for both web export
  platforms.
- **Parity**, as in #198, extended to these files.
- **A hint about hosting.** An application with threads does not start on a host without
  isolation; the build says what the host needs or that the progressive web app supplies it.

## API

### The export platform

```sh
bazel build //path/to:app --platforms=@autoload_rules_godot//godot/platforms:web_wasm32_threads
```

```starlark
godot_export_platform(
    name = "web_threads",
    operating_system = "web",
    cpus = ["@platforms//cpu:wasm32"],
    threads = True,
)
```

`threads` applies to the web only and is `False` by default. Predicates for `select()`:

```starlark
select({
    "@autoload_rules_godot//godot/platforms:is_web_threads": [...],
    "@autoload_rules_godot//godot/platforms:is_web_nothreads": [...],
    "//conditions:default": [...],
})
```

A pack for the threaded platform has the feature tag `threads` instead of `nothreads`.
`variant/thread_support` stays owned by Bazel.

### The progressive web app

Authored as Godot's export options:

```starlark
godot_pack(
    name = "pack",
    project = ":game",
    deps = [":main"],
    export_options = {
        "progressive_web_app/enabled": "true",
        "progressive_web_app/ensure_cross_origin_isolation_headers": "true",
        "progressive_web_app/offline_page": '"res://web/offline.html"',
        "progressive_web_app/display": "1",
        "progressive_web_app/orientation": "0",
        "progressive_web_app/icon_144x144": '"res://web/icon_144.png"',
        "progressive_web_app/icon_180x180": '"res://web/icon_180.png"',
        "progressive_web_app/icon_512x512": '"res://web/icon_512.png"',
        "progressive_web_app/background_color": "Color(0.14, 0.14, 0.14, 1)",
    },
)
```

The application's directory gains Godot's files:

```
app/
  ...
  index.manifest.json
  index.service.worker.js
  index.offline.html
  index.144x144.png
  index.180x180.png
  index.512x512.png
```

### The provider

`GodotWebAppInfo.cross_origin_isolation` tells a deploy rule what the host must do:
`"none"` without threads, `"headers"` with threads, `"service_worker"` with threads and a
progressive web app that ensures the headers.

## Deliberate differences from Godot

- Godot versions the service worker with the export's time, so two exports of the same
  project differ. The ruleset derives the version from the files the service worker
  caches: it changes exactly when they do.

## Established by experiment

On macOS ARM64 with Godot 4.7.2 and chrome-headless-shell 147.

- **With the isolation headers, the threaded templates start and exit as reliably** as the
  one without threads, with the same start-up time.
- **Without the headers the engine never starts**, and the page shows Godot's notice that
  names cross-origin isolation.
- **Godot's own page did not become isolated through its service worker** in the headless
  browser: it reloads when the worker is registered, before it controls the page, and then
  waits forever without a notice. One more reload once the worker is ready made every run
  isolated, with log and exit code intact.
- **Between two exports only the service worker's version differs**, and 20 bytes of the
  pack that were not investigated.

## Open

- Whether Godot's page isolates itself in a visible browser. If it does not there either,
  the reload is a second deliberate difference, or a bug to report to Godot.
- Real thread workloads, Linux hosts and other browsers. Safari does not support the
  header variant some hosts rely on for isolation; the documentation needs a
  recommendation per host.
- The progressive web app with threads behind headers, and without threads without them.

## Not in this issue

Extensions with threads, which the issue on web extensions owns. Header files for specific
hosts beside the export.
