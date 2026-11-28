# Support web as an export platform

Body of #88.

---

Web becomes an export platform of `godot_app`: an application builds for the browser, runs
there through `bazel run`, and carries the extensions of its add-ons. The measure is parity
with Godot's own web export. For the same project and export options the ruleset produces
the files Godot's export produces, under the same names and with the same page; a
difference is allowed only where Godot's output is not reproducible or does not work, and
each one is named.

## Reference

Branch [`claude/web-builds-prototyp-df2828`](https://github.com/autoload-dev/autoload/tree/claude/web-builds-prototyp-df2828),
commit `3d91f7c5e`: a throwaway vertical slice in the ruleset, the decision research
([`Web Builds Entscheidungsgrundlagen.md`](https://github.com/autoload-dev/autoload/blob/3d91f7c5e/docs/internal/research/web-builds/reports/Web%20Builds%20Entscheidungsgrundlagen.md),
German) and the size and playable-ad prototypes. The research's proposals were the starting
point; the decisions below replace them where they differ. Each issue records what
experiments established for it.

## Order of work

Each is its own issue and can merge alone.

1. #PRIMITIVES **Split the extension rules into their primitives.** Not specific to the web;
   it gives linking for Godot a rule of its own, where the web's way of linking belongs.
2. #MISSING **Report the extension libraries an application lacks on its platform.** For
   every export platform; it is what lets an application build for the web before each of
   its add-ons does.
3. #198 **A browser build from a prebuilt runtime.** No threads, no extensions; the page and
   files of Godot's export; `bazel run` in a visible or headless browser; a smoke test in CI.
4. #200 **Threads and PWA.** A second web export platform with threads, and Godot's
   progressive web app output.
5. #201 **Extensions.** The extensions of an application's add-ons build for the web and
   ship with it, for both web export platforms.

## Decisions

| Question | Decision |
| --- | --- |
| What orders the work | The general web export: a browser build first, then threads and extensions. |
| Parity | Godot's own web export is the reference for the file set, the names and the page. |
| Threads | Supported, as a property of the export platform, because they change the ABI of extensions and what the host must serve. Without threads comes first and stays the default, as in Godot since 4.3. |
| Progressive web app | Supported as Godot offers it, with threads: it is what gives cross-origin isolation on hosts that set no headers. |
| `bazel run` | Serves the application on this host. The application's log reaches the terminal and its exit code ends the command, in a visible browser too. `--headless` is public. |
| Browser | The host's. `--headless` starts a Chromium browser found on this host; the ruleset pins and downloads none. |
| Output | A directory and its archive, and a provider for rules that deploy or start it. |
| Emscripten toolchain | From the ruleset, per Godot version and in the version of that Godot's official templates; another version fails. The stable release and the next minor's preview build web extensions in one invocation. |
| Add-ons without a web library | The application fails and names them; a setting builds it without them. |
| Proof for extensions | SQLite. |
| Renderer and C# | The web runs the Compatibility renderer only; a project that selects another gets a note. A C# project fails at analysis time, as Godot's exporter rejects it. |

## Known limits

- An application that quits within its first frames does not report its exit on the web,
  unless it runs with Godot's `--headless` or the dummy audio driver.
- An application with extensions is larger and loads slower than one without, because
  Godot's template for extensions loads the engine as a side module.
- An Emscripten SDK is 1.5 to 1.6 GB unpacked, per version and host.

## Open, without an issue

- **Source-built web engines.** They need the same Emscripten toolchain as extensions and
  are what makes a small engine possible: the official template is 7.10 MB Brotli, a
  source-built engine for Lichtpost 2.6 MB.
- **Playable ads.** Whether a single-file packer belongs in the ruleset, where the network
  adapters live and which networks to serve are undecided. They depend on source-built web
  engines.
- **Pre-compressed files and host header files** beside the export.
- **The editor variant** on the web.

## Resolved earlier

Without explicit project settings, the texture families an import writes depended on the
CPU of the machine that ran it. #80 pins both import settings for every export platform, so
a web pack always has S3TC/BPTC.
