# Web builds: prototype findings

A throwaway vertical slice that builds and runs a Godot web application with
`godot_app`. Its purpose is to surface the decisions that web support needs, above all
those with several options that affect other features. Code it adds is marked
`PROTOTYPE(web)`.

## What the prototype does

```sh
cd examples
bazel build //projects/lichtpost:app --platforms=@autoload_rules_godot//godot/platforms:web_wasm32
bazel run   //projects/lichtpost:app --platforms=@autoload_rules_godot//godot/platforms:web_wasm32
```

- `godot_export_platform(operating_system = "web", cpus = ["@platforms//cpu:wasm32"])`,
  a single platform slice like the desktops, with `@platforms//os:emscripten`.
- The prebuilt hub registers `runtime_web_wasm32_{release,debug}` from the export-template
  archive's `templates/web_nothreads_{release,debug}.zip`; the ZIP is the runtime's
  executable.
- The pack exports with preset platform `Web`; the shell probe works unchanged and records
  the web options and the feature tags `web wasm32 nothreads web_noextensions s3tc bptc`.
- `godot_web_application` copies the template's `godot.*` files as `index.*`, adds the PCK
  and the default boot splash, and fills `godot.html`'s `$GODOT_*` placeholders from the
  facts, as `EditorExportPlatformWeb::_fix_html` does. It writes a directory and a ZIP.
- `bazel run` serves the directory on `127.0.0.1:8060` with COOP/COEP headers and opens
  the browser.

Verified: Lichtpost builds in the release and debug variants, loads in a browser and
plays. The existing white-box tests of the touched packages pass. Not done: extensions,
threads, PWA, icons, custom HTML shell, tests, source-built engines, documentation,
conventions and Code Health.

## Decisions

Each decision lists its options and the features it touches. Ordered by reach.

### 1. Threads and extension support: where the template variant is chosen

Godot ships eight web templates: threads or not × `dlink` (GDExtension side modules) or
not × debug/release. The choice changes the pack's feature tags (`threads`/`nothreads`,
`web_extensions`/`web_noextensions`), the ABI that extension side modules must match
(`-pthread` or not), and the hosting requirements (threads need cross-origin isolation:
COOP/COEP headers or Godot's service-worker workaround).

| Option | Consequence |
| --- | --- |
| A. Fixed: no threads, dlink only when needed | Simplest. Godot's default since 4.3. Threads unavailable. |
| B. Attribute of `godot_export_platform` (e.g. `web_threads`, `web_extensions`), carried as a constraint like the iOS environment | Part of the target platform, so runtime slots, extension builds and `select()` see it. Fits that it changes native ABI and feature tags. More export platforms. |
| C. Build settings like `//godot:variant` | Orthogonal to the platform; but extension libraries and runtime must agree, which a platform constraint enforces and a flag does not by itself. |
| D. Derived: dlink iff the pack has extensions | No user choice, but the runtime then depends on the pack's content, which today it does not. |

Touches: runtime toolchain slots, export option ownership (`variant/*` is owned by the
prototype as constant `false`), feature-tag reservation, extension builds, hosting and
`bazel run`. Recommendation to discuss: B for threads, D or B for dlink.

### 2. Native code: an Emscripten C++ toolchain

A wildcard analysis of the examples with `web_wasm32` fails 36 configured targets on
`@bazel_tools//tools/cpp:toolchain_type` and 8 on rules_dart's toolchain. Extensions on
the web are side modules linked with the exact Emscripten version of the engine build.

- Who provides the toolchain: the consumer (emsdk's Bazel toolchain) or the ruleset with a
  pinned version per Godot release in `profiles.bzl`.
- What happens without it: today native add-ons **fail** a web wildcard build instead of
  being skipped. Either `godot_cc_extension` and the add-on rules become incompatible on
  web until supported, or every add-on declares `target_compatible_with`. This affects
  every add-on in `addons/` and the examples (sqlite, app_auth, platform_paths, dart).
- Packaging: extension libraries go into `GODOT_CONFIG.gdextensionLibs` and
  `fileSizes`, the descriptor needs a `web.wasm32` entry, and the dlink template ships
  `godot.side.wasm` (44 MB) besides the main module.

The same toolchain decides whether **source-built engines** (the SCons translation) can
target the web. Until then the web is prebuilt-only.

### 3. Tests on the web export platform

`bazel test` with `web_wasm32` fails: no execution platform matches
`@platforms//os:emscripten` for `default_test_toolchain_type`.

| Option | Consequence |
| --- | --- |
| A. Web tests are incompatible (skipped in wildcards) | Cheap; tests keep running on desktop platforms only. |
| B. Run GdUnit in a headless browser against the wasm runtime | Tests the real runtime; needs a pinned browser and a harness that reports results out of the page. New lane cost. |
| C. Run on the host editor with web feature tags, like the editor variant | Exercises web-specific GDScript branches, not the wasm runtime. |

Touches: the verification architecture, lanes and CI cost, `godot_test`'s exec-platform
mapping (`//godot/private/config:*_test_toolchain`).

### 4. Texture formats and imports

The web export defaults to `vram_texture_compression/for_desktop = true` and
`for_mobile = false`, i.e. S3TC/BPTC only. Mobile browsers need ETC2/ASTC, which requires
the project setting `rendering/textures/vram_compression/import_etc2_astc`. That changes
the import units' outputs and the pack size, and imports already run once per project and
target platform. Options: leave both to the project (authored export option and setting),
or derive them from the application (e.g. a `web_mobile` attribute), which would be the
first application value that changes imports.

### 5. Shell files: icons, splash, PWA, custom HTML

The prototype fills `godot.html` in Python from the facts, consistent with how the
ruleset writes Info.plist and manifests. Open parts:

- Icon and splash: Godot renders `<name>.icon.png`, `<name>.apple-touch-icon.png` and the
  boot splash `<name>.png`. The prototype copies Godot's default splash, which is wrong for
  a project with its own `application/boot_splash/image`, and rejects `html/export_icon`
  although its default is `true`. The shell probe's image rendering (as for iOS and
  Android) fits.
- PWA: `manifest.json`, the service worker with its cached file list, the offline page and
  three icons. Needed for cross-origin isolation without server headers (threads).
- `html/custom_html_shell` names a project file; it would resolve from the pack's members
  like `application/liquid_glass_icon`.

### 6. Output layout and provider

Godot names every file after the exported HTML file. The prototype writes `index.*`,
so the directory and ZIP deploy to static hosts and itch.io as they are. Open: whether
the name follows the app's name, whether to provide a `GodotWebAppInfo` (the backend
reuses the desktop output groups `bundle` and `archive`), and whether to pre-compress
`.wasm`/`.pck`.

### 7. The runtime's shape

`GodotRuntimeInfo.executable` holds the template ZIP. Either keep that, as Godot's
`custom_template` does, or extract the template in the repository rule and describe its
files. The engine-version validation (`check_engine`) does not run for web runtimes yet:
the version is in `godot.js`, not in a native binary.

### 8. `bazel run`

Python's standard-library server with COOP/COEP on Godot's port 8060, opening the system
browser. Open: port choice and conflicts, choosing a browser (`--device` already means a
device), the editor variant (stays incompatible; Godot's web editor is out of scope), and
whether `--headless` should start a headless browser and stream the console as the log,
which option 3B would need anyway.

### 9. Scope and smaller points

- Scope: the [capability matrix](capabilities.md) lists Web applications as open. Web
  support is a scope decision before it is a design one.
- Naming: rules_godot calls the operating system `web`, Bazel's constraint is
  `emscripten`; the CPU tag `wasm32` joins `CPU_TABLE` and the reserved feature tags.
- Renderer: the web runs only the Compatibility renderer; Godot falls back through
  `rendering_method.web`. A Forward+ project could get an analysis-time note.
- Debug symbols: the web backend returns none; wasm DWARF or source maps would be the
  counterpart.
- Godot 4.8 keeps the template layout; its profile inherits the prototype's web rows.
