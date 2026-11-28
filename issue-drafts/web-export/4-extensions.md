# Build and ship extensions for the web

Sub-issue of #88.

---

## Goal

A web application carries the extensions of the add-ons of its packs, as an application on
every other platform does. A consumer declares nothing beyond the add-on; the build picks
the engine template that can load extensions when there are any to load.

## Scope

- **An Emscripten toolchain from the ruleset, per Godot version.** Each Godot version gets
  the Emscripten version its official templates were built with, and the stable release
  and the next minor's preview build their extensions in one invocation.
- **Source-built extensions** for the web, with the engine's ABI across everything they
  link, godot-cpp included.
- **Both web export platforms.** With and without threads are two ABIs; an extension builds
  for each, and a mismatch fails the build instead of the page.
- **Prebuilt extensions** that bring a web library.
- **The template follows the pack.** An application whose packs have web extensions gets
  the template that loads them, and its feature tags agree. Godot finds a mismatch only in
  the browser; the build finds it at analysis time.
- **Proof: SQLite**, in its example and in a smoke test in CI that starts the application
  in the headless browser. A database in memory is enough; persistence in the browser is
  its own question.
- **Remote execution and caching stay intact.**

## API

### Nothing to register

The engine's hub provides the Emscripten toolchains with the engine, as it provides the
Android toolchains. An SDK is fetched only when a build compiles an extension for the web.

```starlark
# MODULE.bazel: unchanged.
godot_engines = use_extension("@autoload_rules_godot//godot:extensions.bzl", "godot_engines")
godot_engines.engine(name = "godot", default = True, version = "4.7.2")
```

| Godot | Emscripten |
| --- | --- |
| 4.7 | 4.0.20 |
| 4.8 | 6.0.12 |

A consumer's own Emscripten toolchain, registered ahead of the hub's, must be of the
engine's version:

```
//game:app: the extension //game:game_extension is built with Emscripten 5.0.2, but the
runtime of Godot 4.7.2 for web_wasm32 with 4.0.20.
```

### A source-built extension

`godot_extension_library` gains the web: there it links a side module with the engine's
ABI, with or without threads as the export platform says. `godot_cc_extension` builds for
the web with it, unchanged.

```starlark
godot_cc_extension(
    name = "game_extension",
    srcs = ["register_types.cc", "movement.cc"],
    entry_symbol = "game_library_init",
)
```

```sh
bazel build //path/to:app --platforms=@autoload_rules_godot//godot/platforms:web_wasm32
```

| Operating system | What `godot_extension_library` produces |
| --- | --- |
| Web | a `.wasm` side module |

The generated descriptor gains the web's feature tags, with `threads` or `nothreads` as
Godot's own web libraries carry them:

```ini
[libraries]
web.wasm32.nothreads.release = "bin/web.wasm32.nothreads.release/libgame_extension.wasm"
web.wasm32.threads.release = "bin/web.wasm32.threads.release/libgame_extension.wasm"
```

An extension that uses the primitives adds a branch for the web to its `library`.

### A prebuilt extension

A `.wasm` side module is a new dynamic link kind, for the web only.

```starlark
godot_extension(
    name = "prebuilt",
    entry_symbol = "game_library_init",
    library = select({
        "@autoload_rules_godot//godot/platforms:is_web_nothreads": "bin/libgame.web.nothreads.wasm32.wasm",
        "@autoload_rules_godot//godot/platforms:is_web_threads": "bin/libgame.web.threads.wasm32.wasm",
        "//conditions:default": None,
    }),
)
```

### What the application does with them

Nothing to declare. With web extensions in its packs, the application's files change as
Godot's export with extension support does:

```
app/
  index.html
  index.js
  index.wasm              # the small main module
  index.side.wasm         # the engine
  libgame_extension.wasm  # each extension library, under its own name
  index.pck
  ...
```

`variant/extensions_support` stays owned by Bazel: an authored value fails and names this
derivation.

## Costs to state in the documentation

- Godot's template for extensions loads the engine as a side module: 1.5 MB plus 44.1 MB
  instead of 39.5 MB for 4.7.2, so an application with extensions is larger and loads
  slower.
- An unpacked Emscripten SDK is 1.5 to 1.6 GB per version and host.
- Extensions that need C++ exceptions do not run on 4.7; from 4.8 they must be built with
  wasm exceptions.

## Established by experiment

On macOS ARM64 with Bazel 9.3.0, Godot 4.7.2 and 4.8 beta 1, Emscripten 4.0.20 and 6.0.12,
in headless Chrome 158.

- **godot-cpp builds as a side module under Bazel**, with a `cc_toolchain` configuration of
  the ruleset's own over Emscripten's archives. The registry's `emsdk` module builds one
  only with three workarounds and wraps the result in a tar; of it, the release table is
  reusable.
- **Two Emscripten versions build in one invocation**, with one SDK repository per version
  and execution platform.
- **Remote execution works**: the build ran on Linux x86_64 executors and gave the same
  bytes as on the Mac. Nothing is built on the host at fetch time, and without threads no
  position-independent system libraries are needed.
- **A side module loads without cross-origin isolation**, the examples' SQLite extension
  included. Godot's source is right and its documentation outdated.
- **Threads with extensions work on 4.7.2** and on 4.8 beta 1.
- **A wrong threads ABI fails only in the browser**, where the page then waits forever.
- **The Emscripten versions did not have to match**: modules of either version ran in the
  other's engine. The exact match stays the rule because exceptions and C++ standard
  library types across the boundary are untested.

## Open

- A side module with threads needs a start-up object that Emscripten's archives lack. The
  experiment linked those modules outside Bazel; a hermetic way is to be found.
- The bindings repository defaults to 64 bits, and the web needs 32.
- Release templates, `-c opt` and link-time optimization, Safari and Firefox, and the
  whole chain up to `godot_app` are untested.

## Not in this issue

Add-ons that depend on an operating system's APIs, Dart, and source-built web engines,
which need the same toolchain and are tracked in #88.
