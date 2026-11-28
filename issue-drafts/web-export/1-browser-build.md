# Build and run a web application from a prebuilt runtime

Sub-issue of #88.

---

## Goal

A `godot_app` builds for the web export platform into what Godot's own web export
produces, and `bazel run` starts it in a browser. The result deploys unchanged to a static
host or to itch.io.

## Scope

- **One web export platform**, without threads, from Godot's prebuilt web templates, in the
  release and debug variants, for the stable release and the next minor's preview.
- **GDScript projects.** An application whose add-ons bring extensions follows #MISSING:
  it fails and names them, or builds without them.
- **Parity with Godot's export.** The same files under the same names, and the same page
  line for line, for the same project and export options: the page's configuration, the
  boot splash, the icons, the project's additions to the page's head and a project's own
  HTML shell. A check compares against a real export by Godot.
- **The runtime describes itself.** Its files, its Godot version and the Emscripten version
  it was built with are known to the build, so the engine version check covers web runtimes.
- **`bazel run`** in a visible or headless browser, with the application's log on the
  terminal and its exit code as the command's.
- **A smoke test in CI**, internal to this repository: an application of a consumer
  scenario starts in the headless browser and exits with a code of its own. The host jobs
  install the browser, as they set up the Android SDK.
- **Documentation**: the platform guide, the capability matrix and the verification hosts.

## API

### The export platform

```sh
bazel build //path/to:app --platforms=@autoload_rules_godot//godot/platforms:web_wasm32
```

A consumer's own, and the predicate for `select()`:

```starlark
load("@autoload_rules_godot//godot/platforms:defs.bzl", "godot_export_platform")

godot_export_platform(
    name = "web",
    operating_system = "web",
    cpus = ["@platforms//cpu:wasm32"],
)

config_setting(
    name = "my_web_only_thing",
    constraint_values = ["@platforms//os:emscripten"],
)

godot_resources(
    name = "main",
    srcs = ["main.gd", "main.tscn"],
    deps = select({
        "@autoload_rules_godot//godot/platforms:is_web": [":browser_input"],
        "//conditions:default": [":desktop_input"],
    }),
)
```

rules_godot calls the operating system `web`; Bazel's constraint is
`@platforms//os:emscripten`. A web pack has the feature tags `web`, `wasm32`, `nothreads`
and `web_noextensions`.

### The application

`godot_app` is unchanged; the web is one more platform it builds for. Nothing is
registered: the engine's hub gains the web runtimes, and the templates are fetched only
when an application builds for the web.

```starlark
godot_app(
    name = "app",
    pack = ":pack",
    application_id = "com.example.mygame",
)
```

Its outputs are the directory and its archive, as Godot's export names the files:

```
app/
  index.html
  index.js
  index.wasm
  index.pck
  index.audio.worklet.js
  index.audio.position.worklet.js
  index.png                   # boot splash
  index.icon.png
  index.apple-touch-icon.png
app.zip
```

`--output_groups=bundle` or `--output_groups=archive` selects one, as on the desktop.

### The provider

```starlark
load("@autoload_rules_godot//godot:providers.bzl", "GodotWebAppInfo")

def _deploy_impl(ctx):
    app = ctx.attr.app[GodotWebAppInfo]
    app.bundle                    # the directory
    app.archive                   # its ZIP
    app.entry_point               # "index.html", relative to the directory
    app.cross_origin_isolation    # whether the host must serve the isolation headers
    ...
```

### Export options

Authored in the pack's `export_options`, under the names of Godot's export dialog:

```starlark
godot_pack(
    name = "pack",
    project = ":game",
    deps = [":main"],
    export_options = {
        "html/canvas_resize_policy": "2",
        "html/head_include": '"<meta name=\\"theme-color\\" content=\\"#242424\\">"',
        "html/custom_html_shell": '"res://web/shell.html"',
        "html/export_icon": "true",
        "html/focus_canvas_on_start": "true",
        "html/experimental_virtual_keyboard": "false",
        "vram_texture_compression/for_mobile": "true",
    },
)
```

| Option | Effect or owner |
| --- | --- |
| `html/*` | The page, as Godot writes it. A custom HTML shell is a resource of the pack. |
| `vram_texture_compression/*` | Which texture families the pack keeps. |
| `variant/thread_support` | Bazel: the export platform. An authored value fails. |
| `variant/extensions_support` | Bazel: derived from the pack's extensions. An authored value fails. |
| `custom_template/*` | Bazel: the registered engine. |
| `progressive_web_app/*` | Rejected when enabled, until #200. |

### Run

```sh
bazel run //path/to:app --platforms=@autoload_rules_godot//godot/platforms:web_wasm32
bazel run //path/to:app --platforms=... -- --device=firefox -- --verbose
bazel run //path/to:app --platforms=... -- --headless -- -- --level=3
```

The launcher serves the directory on `127.0.0.1`, opens the page, streams the
application's log and exits with its exit code. Godot's arguments after the second `--`
reach the engine as on the other platforms.

| Option | Effect on the web |
| --- | --- |
| `--device=<name or path>` | The browser: the system's default without it, and with `--headless` the first Chromium browser found on this host |
| `--list-devices` | List the browsers the launcher can start, then exit |
| `--headless` | A Chromium browser of this host without a window, with software rendering where the host has no GPU, and Godot's `--headless` |
| `--port=<number>` | The server's port; 8060 by default, the next free one when it is taken |
| `--fresh`, `--detach`, `--env` | Fail: a browser gives the application no environment, and its storage is the browser's |

### The browser

The launcher uses the browsers of this host, as the Android launcher uses the host's SDK
tools. It downloads none. `--headless` needs a Chromium browser: Chrome, Chromium, Edge or
`chrome-headless-shell`. Without one the launcher fails and says what it looked for:

```
No Chromium browser found on this host for --headless. Looked for: Google Chrome,
Chromium, Microsoft Edge, chrome-headless-shell. Install one, or name its path with
--device=<path>.
```

rules_godot gains no dependency for it.

## Behavior at the limits

- A wildcard build for the web skips an application that says it is not for the web, with
  `target_compatible_with`. One that does not say so and lacks an extension library
  follows #MISSING.
- A C# project fails at analysis time.
- A project that selects the Forward+ or Mobile renderer gets a note that the web runs the
  Compatibility renderer.

## Established by experiment

On macOS ARM64 with Godot 4.7.2 and chrome-headless-shell 147; a Linux x86_64 executor
ran the application in the browser too.

- **The exit code and the log reach the host without the DevTools protocol.** Whenever the
  page reported an exit, the code and every line before it were right.
- **An application that quits in its first frames never reports its exit.** Quitting
  closes the audio context while its worklet still starts, and the page waits forever; the
  log is complete. Godot's `--headless` and the dummy audio driver avoid it. It looks like
  a bug in Godot.
- **A project without a main scene exits with 0 on the web**, where Godot reports an error
  on the desktop.
- **`chrome-headless-shell` has no WebGL 2 by default.** It needs software rendering
  turned on explicitly, or the GPU on macOS.
- **Start-up** takes about 0.2 s to the engine's first line with software rendering, and
  about 1 s for an application that quits after a frame.
- **On a Linux executor the browser needs libraries** that a minimal image lacks, and
  its profile directory under `/tmp`.
- **rules_browsers was tried and set aside.** Its browser is reachable from another rule
  only through a private provider, only the root module can choose the browser's version,
  and it adds its JavaScript rules to every consumer's module graph.
- **Log lines sent one request each get lost**; they have to be sent in batches.

## Open

- The flags for software rendering depend on the browser's version, which the host now
  decides; which versions the launcher supports.
- Whether `bazel run` in a visible browser works around the early-quit hang or only
  documents it.
- Whether the application's start without a main scene should fail the build.

## Not in this issue

Extensions, threads, the progressive web app, source-built engines, pre-compressed files,
the editor variant.
