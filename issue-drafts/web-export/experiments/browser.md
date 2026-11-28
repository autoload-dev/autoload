# Browser experiments for web support

Experiments for the questions "to establish first" of the web issues: Support web as an
export platform (#88), Build and run a web application from a prebuilt runtime (#198) and
Support threads and progressive web apps on the web (#200). Everything here ran on one host;
the scripts are in [browser/](browser/).

**Host and versions.** MacBook Pro, Apple M5 Max (`Mac17,6`), 128 GB, macOS 27.2.1, arm64.
Godot 4.7.2 stable (`4.7.2.stable.official.ed1daf0bf`), its official export templates
(Emscripten 4.0.20) and its macOS editor, all from the prototype's Bazel repositories
(`godot_templates_archive`, `godot_editor_macos`). rules_browsers 0.4.0 from the BCR, Chrome
for Testing `chrome-headless-shell` 147.0.7687.0 (its default pin). Bazel 9.3.0. Prototype
commit `3d91f7c5e` in a pooled worktree (`exp-web-browser`), examples module.

**Not run anywhere: Linux.** No Linux host or VM was used (Docker was not running, and
pulling images would fetch tools outside Bazel). "Software rendering as on a GPU-less Linux
CI" was emulated on macOS with SwiftShader forced. See each section's caveats.

## Files

| File | What it is |
| --- | --- |
| `browser/bazel/MODULE.bazel.diff` | What the experiment added to the examples' `MODULE.bazel`. |
| `browser/bazel/defs.bzl`, `browser/bazel/BUILD.bazel` | The five ways of obtaining the browser (package `//exp/browser` in the examples). |
| `browser/project/` | The probe project (`main.gd`) and `export.sh`, which exports it with the pinned editor in eight presets. |
| `browser/harness/serve.py` | Local server and launcher: serves an export on 127.0.0.1, starts the browser, prints the log, exits with the game's code. |
| `browser/harness/hook.js` | The page side: Engine callbacks that POST back to the server. |
| `browser/harness/run_matrix.py` | Runs `serve.py` 20 times per case and writes `summary.json` per matrix. |
| `browser/harness/tabulate.py` | Turns the summaries into the tables below. |
| `browser/results/` | Each finished matrix's `summary.json` (per-run logs and JSON stayed in the scratchpad). |

## 1. rules_browsers as a tool of the execution platform (#198)

**Answer.** Yes: an attribute `cfg = "exec"` on `@rules_browsers//browsers/chromium:chromium`
builds and runs with `--platforms=…:web_wasm32`; taking it in the target configuration, as
rules_browsers' own test rules and its make-variable alias do, fails analysis because its
`select()` has no branch for `os:emscripten`. A toolchain of the ruleset's own per host,
pointing at rules_browsers' per-host repositories, is the cleanest shape; but the exec
configuration follows the *execution* platform, so `bazel run` under remote execution would
get the Linux browser, and the ruleset cannot pin the Chrome version through rules_browsers'
extension (only the root module can).

### What works and what fails

All in `//exp/browser` of the examples module, built with
`--platforms=@autoload_rules_godot//godot/platforms:web_wasm32` (see `bazel/`):

| Variant | Starlark | Result |
| --- | --- | --- |
| A. exec attribute | `attr.label(cfg = "exec", default = "@rules_browsers//browsers/chromium:chromium", providers = [NamedFilesInfo])` | Builds; `bazel run //exp/browser:exec -- --version` prints `Google Chrome for Testing 147.0.7687.0`. |
| B. target attribute | same with `cfg = "target"` | Fails: `configurable attribute "deps" in @@rules_browsers+//browsers/chromium:chromium doesn't match this configuration. Would a default condition help? Conditions checked: …:linux_x64 …:macos_x64 …:macos_arm64 …:windows_x64` |
| C. transition to the host | outgoing transition setting `//command_line_option:platforms` to `@platforms//host` | Builds and runs (same output as A). The attribute becomes a list (`ctx.attr.browser[0]`). |
| D. make variables | `genrule(toolchains = ["@rules_browsers//browsers/chromium:toolchain_alias"], cmd = "echo $(CHROME-HEADLESS-SHELL)")` | Fails with the same `select()` error: the alias is target-configured. |
| E. own toolchain | `toolchain_type` + one `toolchain(exec_compatible_with = [os, cpu])` per host, each wrapping `@rules_browsers_chrome_<host>//:info` (`cfg = "exec"`), consumed with `config_common.toolchain_type(…, mandatory = False)` | Builds and runs (same output). Needs `use_repo(browsers, "rules_browsers_chrome_linux", …_mac, …_mac_arm, …_win64)` in the module that defines the toolchains. |

Execution platform effects, checked with `bazel cquery 'deps(…)' --extra_execution_platforms=…`
and `--toolchain_resolution_debug`:

- A with an extra Linux x86_64 execution platform registered first selects
  `@rules_browsers_chrome_linux` (and chromedriver_linux): right for a test that runs
  remotely, wrong for `bazel run`, which runs on the Mac. For `bazel run`, C (or E with the
  host's constraints) is what selects the browser of the machine that opens it.
- A with a Linux arm64 execution platform fails with the same `select()` error.
- E with a Linux arm64 execution platform skips it ("mismatching values") and falls back to
  the next execution platform; on a host with no matching toolchain the optional toolchain
  is `None`, and the launcher can say "no pinned browser for this host" instead of failing
  analysis. I could not make Bazel treat the Mac itself as Linux arm64 (`--host_platform`
  does not replace the registered `@platforms//host`), so that last path is unrun.

### Hosts, size, laziness, versions, license

- **Hosts.** Chrome for Testing publishes linux64, mac-x64, mac-arm64, win32/win64 builds
  only; rules_browsers 0.4.0 maps `linux_x64`, `macos_x64`, `macos_arm64` and `windows_x64`.
  **No Linux arm64**, confirmed in the version table and the `config_setting`s.
- **Download size** of `chrome-headless-shell` 147.0.7687.0 (zip in the repository cache /
  extracted): linux64 112.0 MB / 256 MB, mac-x64 96.5 MB / 201 MB, mac-arm64 92.1 MB /
  190 MB, win64 111.4 MB / 270 MB. Variant A also pulls chromedriver (the `chromium` group
  contains both); E takes only the browser.
- **Lazy.** In a fresh output base, building a target that does not need the browser
  materialized only `rules_browsers+` (the module itself); building `//exp/browser:exec`
  then fetched `rules_browsers_chrome_mac_arm` and `rules_browsers_chromedriver_mac_arm`
  only. No node/npm repositories were fetched.
- **Module graph cost.** `bazel_dep(name = "rules_browsers", version = "0.4.0")` is not a
  leaf: it adds non-dev dependencies on `aspect_rules_js` 2.6.2, `aspect_rules_ts` 3.7.0,
  `rules_nodejs` 6.5.2, `aspect_bazel_lib`, `aspect_tools_telemetry` and others to every
  consumer's module resolution (483 lines in `MODULE.bazel.lock`), although none of them is
  fetched for the browser alone.
- **Versioning.** The BCR has 0.1.0–0.4.0 (0.4.0 released 2026-02-15). It pins Chrome
  147.0.7687.0 and lists 128–147; the GitHub `main` has moved to 160.0.8180.0 without a
  release. The repository is a mirror of `angular/dev-infra`'s `bazel/browsers` (one
  star, two maintainers). Versions come from `browsers.chrome(version = …)`, and the
  extension reads that tag **only from the root module or rules_browsers itself**
  (`_find_version_providing_modules`): rules_godot as a non-root module cannot pin it.
- **License.** The rules_browsers repository has no LICENSE file (GitHub reports none);
  `package.json` says ISC, and the upstream `angular/dev-infra` is MIT. The browser archive
  carries Chromium's BSD-style `LICENSE.headless_shell` (2 MB of third-party notices) and
  an `ABOUT` saying "Google Chrome … See the Terms of Service at chrome://terms".

### Unverified

- Running the Linux browser: the linux64 archive ships `deb.deps`/`rpm.deps` listing system
  packages (libnss3, libgbm1, libasound2, libatk…, libcups2, libxkbcommon0, libvulkan1, …),
  so a bare remote executor image may lack them. Not run.
- Windows. Not run.

## 2. Exit code and log (#198)

**Answer.** The Engine API's `onPrint`, `onPrintError` and `onExit` carry everything without
the DevTools protocol: whenever `onExit` came, it had the code passed to
`get_tree().quit()` (0, 3, 5, 9, 42, 255), and every line printed before the quit had
reached the page before it, in all 580 exiting matrix runs (and 80 more through the service worker). **But a quit before the audio driver
has finished starting never reaches `onExit`**: with Godot's default AudioWorklet driver a
quit in `_ready` or after 2 frames hung in 100% of runs (0/260: 240 with SwiftShader, both
templates and variants, and 20 with the GPU), a Godot web-platform bug, not a flake. `--headless` or `--audio-driver Dummy`
avoid it. Start-up with SwiftShader is ~0.2 s to the engine's first print and stable; the
pinned headless shell needs a flag to have WebGL2 at all.

### Harness

`harness/serve.py` serves an export from 127.0.0.1 on a free port, starts
`chrome-headless-shell` with a fresh `--user-data-dir`, and exits with the application's
code (124 on timeout, 126 when the page shows its failure notice). It rewrites the served
page only: it inserts `hook.js` after `<script src="index.js">` and replaces
`new Engine(GODOT_CONFIG)` with `new Engine(window.__harnessConfig(GODOT_CONFIG))`, which
adds `onPrint`, `onPrintError`, `onExit` and, if given, `args`. Two things I tried first did
not work and matter for the ruleset's design:

- **Patching `Engine.prototype.startGame` does nothing**: `godot.js` declares
  `const Engine` (a script-scoped binding, not replaceable from outside) and `SafeEngine`
  builds a fresh prototype per instance. A harness must either own the page or rewrite its
  `new Engine(…)` call (or wrap the Emscripten factory `Godot`, a global `var`).
- **One `fetch` per print loses lines**: a burst of 60 prints opened 60 connections and
  Python's default listen backlog (5) dropped some (54/59 lines arrived). The hook now sends
  one request at a time carrying everything queued; the server orders by sequence number
  and waits for gaps before exiting. With that, no run lost a line.

The probe project (`project/main.gd`, Compatibility renderer) reads `code=`, `frames=` and
`lines=` from its user arguments, prints a header, 50 numbered lines, one `printerr`, a
`LAST` line, and quits in `_ready` (`frames=0`) or in `_process` after N frames.
`project/export.sh` exports it with the pinned editor (`--headless --export-release|--export-debug`)
and the official templates as `custom_template/*`, keeping the editor's data under the
output directory (`HOME`/`CFFIXED_USER_HOME`).

### Results, template without threads

20 runs per case and variant; times are min / median / p90 / max in ms. "First print" and
"exit" are page times since navigation start (`performance.now()` at the callback), "wall"
is from starting Chrome to the server's exit. Flags: `--disable-gpu --use-angle=swiftshader
--enable-unsafe-swiftshader` plus the harness' common flags (`--no-first-run
--no-default-browser-check --disable-background-timer-throttling --disable-renderer-backgrounding
--disable-backgrounding-occluded-windows --autoplay-policy=no-user-gesture-required`). WebGL2
renderer: `ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (LLVM 10.0.0) (0x0000C0DE)), SwiftShader driver)`.

| Case (args after `--`) | Variant | Right code | First print | Exit (page) | Wall |
| --- | --- | --- | --- | --- | --- |
| `code=0`, quit in `_ready` | release / debug | 0/20 / 0/20 (all timeouts) | 189/227/302/337 | – | – |
| `code=3`, quit in `_ready` | release / debug | 0/20 / 0/20 | 192/218/729/775 | – | – |
| `code=3 frames=2` | release / debug | 0/20 / 0/20 | 190/196/258/359 | – | – |
| `code=3 frames=10` | release | 20/20 | 188/193/198/207 | 648/655/670/716 | 712/722/738/781 |
| | debug | 20/20 | 206/256/300/333 | 730/880/1016/1083 | 806/978/1119/1186 |
| `code=0 frames=60` | release | 20/20 | 189/198/245/268 | 1066/1107/1299/1371 | 1133/1174/1381/1458 |
| | debug | 20/20 | 207/223/283/311 | 1169/1187/1382/1423 | 1243/1268/1521/1541 |
| `code=42 frames=60` | release | 20/20 | 191/201/260/295 | 1073/1152/1309/1493 | 1138/1225/1402/1599 |
| | debug | 20/20 | 207/215/316/369 | 1153/1180/1520/1535 | 1231/1262/1691/1712 |
| `code=255 frames=60` | release | 20/20 | 188/193/214/226 | 1064/1076/1148/1251 | 1130/1144/1314/1325 |
| | debug | 20/20 | 199/263/302/325 | 1118/1298/1407/1418 | 1193/1392/1510/1545 |
| `--audio-driver Dummy -- code=5`, `_ready` | release | 20/20 | 189/198/293/342 | 486/513/645/675 | 553/586/760/784 |
| | debug | 20/20 | 203/247/306/328 | 537/647/799/800 | 609/756/1003/1021 |
| `--headless -- code=9`, `_ready` | release | 20/20 | 189/206/276/378 | 357/377/465/574 | 422/451/597/667 |
| | debug | 20/20 | 207/258/295/313 | 394/482/548/566 | 470/582/685/722 |

**With the Mac's GPU** the template without threads was **not established** with 20-run
counts: the matrix was stopped before it ran. Partial observations: with
`--enable-gpu` single runs exited with code 42 (ANGLE Metal, Apple M5 Max); an earlier
20-run attempt with the shell's default flags failed every run on the WebGL2 notice (which
is how the "no WebGL by default" finding came about), and in it `code=3 frames=10` also
hung (0/20), consistent with the time-based window below. The threaded template with the
GPU (20-run counts) is in section 3.

In every exiting run all 59–60 stdout lines (including `LAST`) and the `printerr` line
arrived, and each had a lower sequence number than the exit event: Godot delivers its
output before `onExit`. `printerr` reaches `onPrintError`. 60 frames take ~1.1 s of page
time; the engine's own start-up (navigation to first print) is ~0.2 s, to `READY` (the
main scene's `_ready`) ~0.25–0.3 s with the 39 MB wasm from a local server.

**The early-quit hang.** In all hung runs checked (the 60 of `nt-swiftshader` release) the whole log, `LAST` included, had arrived;
only `onExit` was missing, and the page reported `unhandled rejection: TypeError: parameter
1 is not of type 'BaseAudioContext'` from `index.js` 60–100 ms after `READY`. In
`godot.js`, `GodotAudioWorklet.create` loads the worklet module and then constructs an
`AudioWorkletNode` on `GodotAudio.ctx`; a quit meanwhile closes the context first, the
constructor throws, and `GodotAudioWorklet.close()` returns a promise that only resolves
in the success path (its `.catch` logs and never settles). `GodotOS.finish_async` waits for
all `atexit` promises with `Promise.all`, so the exit callback never runs. The window is
time-based, not frame-based: 10 frames were enough with SwiftShader (≈650 ms page time) and
not enough with the GPU (see above). A search of Godot's issues for the error text found
nothing (not exhaustive). Implications: a smoke test must not quit in `_ready` unless audio
is off; `--headless` (DisplayServer `headless`, audio `Dummy`, no renderer) and
`--audio-driver Dummy` both exit reliably, and the harness needs a timeout regardless.

### Flags

| Flags (besides the common ones) | WebGL2 | Result |
| --- | --- | --- |
| none (`chrome-headless-shell` defaults) | none | page notice "WebGL2 - Check web browser configuration and hardware support" (80/80 in the stopped default-flag attempt, plus single runs) |
| `--disable-gpu` | none | same notice, 20/20 |
| `--headless=new` | none | same notice (it is already headless) |
| `--enable-unsafe-swiftshader` | SwiftShader | exits (2/2) |
| `--use-angle=swiftshader` | SwiftShader | exits (2/2) |
| `--use-angle=swiftshader --enable-unsafe-swiftshader` | SwiftShader | 20/20, but first print median 536 ms (GPU process still starts) |
| `--disable-gpu --use-angle=swiftshader --enable-unsafe-swiftshader` | SwiftShader | the table above, first print ~200 ms |
| `--enable-gpu` (macOS) | ANGLE Metal, Apple M5 Max | see above |
| `--use-angle=metal` (macOS) | ANGLE Metal | exits (1/1) |
| `--ignore-gpu-blocklist` | none | notice |

So the pinned shell's defaults have no WebGL at all, on a Mac with a GPU too. The flags to
use for software rendering are `--disable-gpu --use-angle=swiftshader --enable-unsafe-swiftshader`;
for the GPU on macOS `--enable-gpu`. `--headless` passed to Godot does not help without
WebGL: the page checks WebGL2 before the engine sees its arguments.

### Arguments and `--headless`

- `args` replaces `GODOT_CONFIG.args`; `startGame` prepends `--main-pack index.pck`.
  `OS.get_cmdline_user_args()` returned exactly the arguments after `--` in every run
  (e.g. `["code=42", "frames=60"]`); `OS.get_cmdline_args()` printed `[]` on the web, even
  with engine options such as `--audio-driver Dummy` (they took effect: `AudioServer`
  reported `Dummy`).
- `--headless` on the web: `DisplayServer.get_name()` is `headless`, audio `Dummy`, the
  video adapter strings are empty, nothing is drawn, and the engine runs its main loop and
  exits normally (it is also the fastest case, exit median 377 ms). The page still requires
  WebGL2 (see Flags).

### Unverified

- **Linux without a GPU**: emulated with SwiftShader on macOS. SwiftShader's timing on a
  CI runner's CPU, and whether the Linux shell runs in a bare container, are untested.
- A visible browser (system Chrome) for `bazel run`: not run, to keep windows off this
  desktop. The callbacks are the same API, so I expect the same behaviour, but the
  AudioWorklet path differs once a user gesture can resume the context.
- Very long logs (I tried 500 lines once: complete) and binary or multi-line prints.
- Exit codes outside 0–255 (Godot passes an int; the browser does not truncate it, the
  OS would).

## 3. Threads (#200)

**Answer.** With COOP/COEP the threaded templates (`web_release.zip`, `web_debug.zip`)
start and exit in the pinned headless shell with SwiftShader as reliably as the template
without threads: 120/120 runs of the exiting cases per variant with the right code and the
complete log, and the same audio hang for an early quit. Without the headers the page never
starts the engine and shows Godot's notice naming the missing Cross-Origin Isolation and
SharedArrayBuffer.

### Evidence

Same harness and cases as in section 2, `--threads` (passes `threads: true` to
`Engine.getMissingFeatures`), headers on (`th-swiftshader`, 20 runs per case):

| Case | th_release | th_debug |
| --- | --- | --- |
| quit after 10/60 frames, codes 3/0/42/255 | 80/80 right code, page exit median 677–1099 ms | 80/80, median 797–1208 ms |
| `--audio-driver Dummy`, quit in `_ready` | 20/20, median 515 ms | 20/20, median 598 ms |
| `--headless`, quit in `_ready` | 20/20, median 382 ms | 20/20, median 440 ms |
| quit in `_ready` or after 2 frames, AudioWorklet | 0/60: hang, as without threads | 0/60 |

Threads print `Build configuration: Emscripten 4.0.20, multi-threaded, no GDExtension
support.`, `OS.has_feature("threads")` is true, and the page reports `crossOriginIsolated`
and `SharedArrayBuffer`. The debug template prints one extra line on exit: `Blocking on the
main thread is very dangerous, see https://emscripten.org/docs/porting/pthreads.html#blocking-on-the-main-browser-thread`
through `onPrintError` (20/20 debug runs, 0/20 release). Start-up is as fast as without threads (first engine print median 207–238 ms) and
noticeably tighter (p90−median ≤ 30 ms in release). With the Mac's GPU (`th-gpu`,
`--enable-gpu`, ANGLE Metal on Apple M5 Max): 20/20 for quit after 60 frames (code 42) and
for Dummy audio, 0/20 for quit in `_ready`.

Without the headers (`th-no-headers`, 20 runs): 0/20 start; every run ends at the page's
notice, which is exactly what a user sees in place of the canvas:

```text
Error
The following features required to run Godot projects on the Web are missing:
Cross-Origin Isolation - Check that the web server configuration sends the correct headers.
SharedArrayBuffer - Check that the web server configuration sends the correct headers.
```

The page also logs it with `console.error`. The template without threads needs neither
header: `nt-no-headers` exits 20/20 (code 42) and 20/20 (Dummy audio, code 5).

### Unverified

- Real Linux and Windows hosts, and Firefox/Safari (Safari's support of
  `Cross-Origin-Embedder-Policy: credentialless`, asked in #200, was not looked at).
- Workloads that actually use threads (the probe does not start a `Thread`, and the
  `emscriptenPoolSize` default of 8 was not varied); memory use; the template's
  behaviour under many parallel headless instances.

## 4. PWA service worker (#200)

**Answer.** Served without COOP/COEP, Godot's own page registers the service worker and
reloads, but the reload comes before the worker controls the page: the second load is
still not isolated, stops with `Error while registering service worker: Error: Service
worker already exists.` and never starts the engine (0/40, every run). One more reload
after `navigator.serviceWorker.ready` makes the page cross-origin isolated, and the
harness' log and exit code then survive unchanged (80/80). Between two exports only the
service worker's `CACHE_VERSION` (export time) differs.

### Evidence

- Export: `project/export.sh` presets `th_pwa`/`nt_pwa` (`progressive_web_app/enabled=true`,
  `ensure_cross_origin_isolation_headers=true`) with the pinned editor. Extra files:
  `index.manifest.json`, `index.service.worker.js`, `index.offline.html`,
  `index.144x144.png`, `index.180x180.png`, `index.512x512.png`; `GODOT_CONFIG` gains
  `"serviceWorker":"index.service.worker.js"`.
- Godot's page alone, threaded PWA release, no headers, SwiftShader (`pwa-th-no-headers`,
  20 runs each of quit after 60 frames and Dummy audio): 0/40. Every run had exactly two
  loads, `navigator.serviceWorker.controller` was null and `crossOriginIsolated` false on
  both, and the second load logged "Service worker already exists". A user sees the loading
  spinner and no notice. Opening `/index.html` instead of `/` changed nothing (7/7 stuck
  the same way before the run was stopped).
- Mechanism (from the exported page and `godot.js`): when `Engine.getMissingFeatures`
  reports missing isolation and `serviceWorker` is set, the page races
  `getRegistration()`/`installServiceWorker()` against a 2 s timer and then calls
  `window.location.reload()`. `register()` resolves on registration, not activation, and
  the worker calls `clients.claim()` only on a `claim`/`update` message, not on `activate`;
  so the reload navigation is not controlled. On the second load `getRegistration()`
  returns the registration and the page gives up.
- With one extra reload by the harness once the worker is ready (`--sw-reload`,
  `pwa-th-no-headers-swreload`, release and debug, 20 runs per case): 80/80 right code
  (42 and 5), always three loads (isolated: false, false, true), all 60 stdout lines before
  `onExit`. Page time of the third load to exit: median 1047–1049 ms (60 frames) and 465 ms
  (Dummy audio); wall time from starting Chrome median 1284–1294 ms and 708–710 ms, i.e.
  the two extra loads cost ~0.25 s. The harness' `/__harness/*` requests are not in the
  worker's cache list; they go through its `fetch` handler, which adds the headers, and
  arrive.
- With the engine started, `Engine.start` also calls `installServiceWorker()` after
  `callMain`, so a PWA served *with* headers registers the worker in the background.
- **Non-determinism between two exports** of the same project (two runs of `export.sh`,
  byte comparison of every file): only `index.service.worker.js` differs, in one line,
  `const CACHE_VERSION = '1795851276|903729';` vs `'1795851756|3053293';` (export time in
  seconds and a microsecond part). The manifest, offline page, the three icons, the page
  and the engine files are identical. (`index.pck` also differed, by 20 bytes, in every
  preset, PWA or not; each run re-imported a fresh project copy, so this is most likely new
  resource UIDs from the import, not the PWA; not investigated.) `CACHE_PREFIX` is
  `<project name>-sw-cache-`; `CACHED_FILES` lists the page, `index.js`, the offline page,
  both icons and the audio worklets; `CACHEABLE_FILES` the wasm and pck.

### Not established

- The threaded PWA debug variant with Godot's page alone, the threaded PWA *with* headers,
  and the PWA without threads without headers: stopped before they ran.
- Whether a real browser's first visit hits the same race (likely: same code; a user's
  manual reload would be the "third load"), and Safari/Firefox.
- Whether the ruleset should reload like the harness or wait for activation before
  Godot's reload; that is a design choice the data only motivates.
