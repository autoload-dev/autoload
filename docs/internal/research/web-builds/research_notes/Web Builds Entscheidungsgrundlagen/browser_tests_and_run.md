# Browser tests and `bazel run` for Godot web exports (state: 2026-11-23)

Source conventions. `GODOT/` stands for the local Godot 4.7.2 source tree at
`<bazel-output-user-root>/cache/repos/v1/contents/007cd308ea698c1482cec6bae06f5fa4889c7995ea15dc5bff689996d5ecbb09/54778939-c1da-48e8-9545-4f94becb5969/`
(read 2026-11-23). `RG/` stands for
`<repo>/rules_godot/`
(branch `claude/web-builds-prototyp-df2828`, commit f22f6963e). Source-code findings are
primary; statements marked "inference" were not run.

## Q1. Bazel options for browser tests (late 2026): maturity, browser pinning, remote Linux execution

### Takeaway
`rules_webtesting` is archived; the living options are Angular's `rules_browsers`
(BCR 0.4.0, Feb 2026, active commits in Nov 2026; pins Chrome-for-Testing
`chrome-headless-shell`, ChromeDriver and Firefox per host with SHA-256) and
`rules_playwright` (community, pins Playwright's browser builds, needs rules_js and Node).
Neither ships Linux arm64 Chrome, and both select browsers by the *target* platform, so
for an emscripten target the browser must be an exec-configured tool, not a plain data dep.

### Cited Findings
- `bazelbuild/rules_webtesting` is archived (`archived: true`, last push 2025-09-11) — [GitHub API repos/bazelbuild/rules_webtesting](https://github.com/bazelbuild/rules_webtesting); a mirror reports the archive date as 2025-11-18 and the README note "This project is no longer being updated" — [mirror](https://gh.r-mj.com/bazelbuild/rules_webtesting). Latest BCR version 0.4.1 — [BCR](https://registry.bazel.build/modules/rules_webtesting). Archiving was proposed because committers had done no maintenance for years — [bazel discussion #18445](https://github.com/bazelbuild/bazel/discussions/18445).
- `rules_browsers`: BCR versions 0.1.0 (2025-08-08), 0.2.0 (2025-08-13), 0.3.0 (2025-10-21), 0.4.0 (2026-02-16); maintainers Paul Gschwendtner (`devversion`) and Sebastian Barfurth — [BCR rules_browsers](https://registry.bazel.build/modules/rules_browsers). Source is maintained in `angular/dev-infra`; README: "Bazel rules for browser automation & testing"; no versioning policy, any release may break; Bzlmod via `bazel_dep` + `git_override` and `browsers.chrome(version=...)`, `browsers.chromedriver(...)`, `browsers.firefox(...)` — [github.com/devversion/rules_browsers](https://github.com/devversion/rules_browsers).
- Most recent `rules_browsers` commits: 2026-11-16 "update rules_browsers browsers metadata to latest versions" and dependency bumps (bot-driven, frequent) — [commits](https://github.com/devversion/rules_browsers/commits/main).
- `rules_browsers` Chromium = Chrome for Testing `chrome-headless-shell` zips with integrity, e.g. `https://storage.googleapis.com/chrome-for-testing-public/128.0.6613.137/linux64/chrome-headless-shell-linux64.zip`; `DEFAULT_VERSION = "160.0.8164.0"`; per-version host keys are only `linux`, `mac`, `mac_arm`, `win64` (117 versions each, no linux arm64) — [browsers/private/versions/chromium.bzl](https://github.com/devversion/rules_browsers/blob/main/browsers/private/versions/chromium.bzl).
- `rules_browsers` picks the host binary with `select()` over `//browsers/private:linux_x64`, `macos_x64`, `macos_arm64`, `windows_x64` in a `browser_group`, and exposes paths as make variables (`TemplateVariableInfo`, e.g. `CHROME-HEADLESS-SHELL`) via `browser_toolchain_alias` — [browsers/chromium/BUILD.bazel](https://github.com/devversion/rules_browsers/blob/main/browsers/chromium/BUILD.bazel), [browser_toolchain_alias.bzl](https://github.com/devversion/rules_browsers/blob/main/browsers/private/browser_toolchain_alias.bzl).
- `rules_browsers` also has `server_test` ("starts a server binary with a random port, and then launches a test binary once the port is bound ... useful for e.g. webdriver tests"), `wtr` (Web Test Runner) and `protractor_test` — [server_test/README.md](https://github.com/devversion/rules_browsers/blob/main/server_test/README.md).
- Angular CLI uses the Chrome binary from rules_browsers for Playwright in Vitest browser tests "for hermetic testing"; dependency bumps update Chrome, ChromeDriver and Firefox with their integrity values — [search summary of angular-cli PRs](https://github.com/angular/angular-cli/pull/31843) (PR bot notifications, not a guide).
- `rules_playwright` (repo `mrmeku/rules_playwright`, BCR versions 0.2.1, 0.3.0, 0.4.0; 0.3.0 tested on Ubuntu 20.04 with Bazel 8.x): module extension `playwright.repo(playwright_version=...)` downloads browsers (chromium, chromium-headless-shell, firefox, webkit, ffmpeg); a `playwright_integrity_map` rule generates SHA-256s for `integrity_path_map`; host selection via `macos_version`/`linux_distro` string flags ("set the appropriate flag for your test exec platform"); tests are `playwright_bin.playwright_test(args=["test"])` from rules_js npm with `PLAYWRIGHT_BROWSERS_PATH=$(rootpath ...)/../`; Firefox on macOS needs the `no-sandbox` tag; 27 stars, no GitHub releases — [github.com/mrmeku/rules_playwright](https://github.com/mrmeku/rules_playwright), [BCR 0.3.0](https://registry.bazel.build/modules/rules_playwright/0.3.0).
- Playwright: each release requires specific browser builds; `PLAYWRIGHT_BROWSERS_PATH` sets the download/search dir; `chromium-headless-shell` is used for headless by default, `--only-shell` skips the full browser, `channel: 'chromium'` uses the real Chrome in new headless mode; Firefox and WebKit are patched builds (no branded Firefox/Safari) — [playwright.dev/docs/browsers](https://playwright.dev/docs/browsers). Chromium headless change in v1.49 — [playwright#33566](https://github.com/microsoft/playwright/issues/33566).
- A WebGL game e2e setup (2025-04-30) uses Playwright with `--no-sandbox`, `--disable-dev-shm-usage`, `--use-gl=swiftshader`, headless, in a pinned Docker image (`PW_VERSION=1.52.0`) run with `--ipc=host` on `ubuntu-latest`, retries 2 on CI, 15 s readiness and screenshot timeouts — [barthpaleologue blog](https://barthpaleologue.github.io/Blog/posts/webgl-webgpu-playwright-setup).
- Bazel: `@bazel_tools//tools/test:default_test_toolchain_type` is the mandatory toolchain of every test rule's `test` exec group; the default toolchain sets `use_target_platform_constraints = True` (exec platform must carry the target platform's constraints); a legacy toolchain lets tests run anywhere, selected by `--use_target_platform_for_tests=false`/`--incompatible_use_default_test_toolchain` settings — [tools/test/BUILD.tools (release-9.3.0)](https://bazel.googlesource.com/bazel/+/refs/heads/release-9.3.0/tools/test/BUILD.tools). Historically `exec_compatible_with` did not apply to the test exec group — [bazel#13626 / search summary](https://github.com/bazelbuild/bazel/issues/13626).
- rules_godot already registers its own toolchains for `default_test_toolchain_type`: `%s_%s_test_toolchain` with `exec_compatible_with` = `target_compatible_with` = OS+CPU, `target_settings = [":<os>_export_platform"]`, `toolchain = "@bazel_tools//tools/test:empty_toolchain"`, for `linux` and `macos` only — `RG/godot/private/config/BUILD.bazel` lines 64–100 (local).
- I found no WebDriver-BiDi-specific Bazel ruleset; BiDi is consumed through Playwright/Puppeteer/WebDriver clients (no Bazel-specific source found).

### Inferences
- The `bazel test` failure is solvable with the existing pattern: add a toolchain for `default_test_toolchain_type` with `target_compatible_with = [@platforms//os:emscripten, @platforms//cpu:wasm32]` and `exec_compatible_with = [<linux|macos>, <cpu>]` (one per host exec platform), just as the desktop mapping does. That makes option B (and C) schedulable on Linux RBE or the macOS VM.
- Once the test runs on a host exec platform, the browser binary must be resolved for the *exec* platform. `rules_browsers`' `select()` and `rules_playwright`'s string flags key on the target configuration, which is emscripten here, so they would fail to match. Wrapping the browser in a `cfg = "exec"` attribute of the test rule (or a test-exec-group toolchain whose `exec_compatible_with` picks the browser) avoids that. This is design work either way; neither ruleset documents RBE use.
- `rules_playwright` drags in rules_js/Node/npm; a Python harness speaking CDP or BiDi directly to a pinned `chrome-headless-shell` (Chrome for Testing zip via `http_archive`) is the smallest dependency set and fits the ruleset's Python launchers. `rules_browsers` mostly provides exactly that pinning plus ChromeDriver.
- Chrome for Testing has no Linux arm64 build (per the version table), so Linux arm64 executors would need Playwright's Chromium or a distro Chromium.

### Gaps
- No primary source on running any of these rulesets on BuildBuddy RBE (sandbox, `/dev/shm`, user namespaces). Chrome inside RBE containers commonly needs `--no-sandbox` and `--disable-dev-shm-usage`; only the blog post above documents those flags, not an RBE source.
- `rules_playwright` 0.4.0 date and release notes were not found.
- Current Angular dev-infra `bazel/browsers` docs (the README just links there) were not read.

## Q2. Can Godot's web build run headless or in Node; how output and exit code reach a harness

### Takeaway
The web runtime needs a real browser with WebGL 2 and a `<canvas>`; there is no headless
path in the web platform (only opengl3 is offered, and `--headless` would swap in a
display server the web main loop does not expect). Output and exit code are cleanly
exposed through the JS engine config: `onPrint`/`onPrintError` (default
`console.log`/`console.error`) and `onExit(status_code)` fed by `OS.set_exit_code` /
`get_tree().quit(code)`. So a harness can capture logs and the exit code without scraping.

### Cited Findings
- `DisplayServerWeb::get_rendering_drivers_func()` returns only `"opengl3"` (under `GLES3_ENABLED`); the constructor requires `godot_js_display_has_webgl(2)` and otherwise reports "Your browser seems not to support WebGL 2" / "Unable to initialize WebGL 2 video driver" — `GODOT/platform/web/display_server_web.cpp` lines 1004–1010, 1135–1157 (local).
- The engine needs a canvas: `Config` uses the first `<canvas>` in the document and throws `No canvas found in page` otherwise — `GODOT/platform/web/js/engine/config.js` lines 334–342 (local).
- `--headless` is parsed in the common `Main::setup` (not editor-only): it sets `audio_driver = NULL_AUDIO_DRIVER; display_driver = NULL_DISPLAY_DRIVER;`; the `headless` display server is registered for every platform — `GODOT/main/main.cpp` lines 1505–1509; `GODOT/servers/display/display_server.cpp` line 68 (local).
- But the web main loop calls `DisplayServerWeb::get_singleton()->check_size_force_redraw()` every frame, and `get_singleton()` is a `static_cast<DisplayServerWeb *>(DisplayServer::get_singleton())` — `GODOT/platform/web/web_main.cpp` lines 80–86; `display_server_web.cpp` lines 62–64 (local).
- `onPrint` defaults to `console.log`, `onPrintError` to `console.error`; both map to Emscripten's `print`/`printErr` — `GODOT/platform/web/js/engine/config.js` lines 195–224, 288–289 (local).
- `onExit(status_code)` is a documented config callback; Godot wraps it to call `cleanup()` first ("We always need to call the cleanup callback to free memory") — `config.js` lines 165–172, 357–374 (local).
- Exit path: when `os->main_loop_iterate()` returns true (quit), the loop is replaced by `exit_callback`, which waits for the FS sync (`godot_js_os_finish_async`), runs `Main::cleanup()`, reads `OS_Web::get_exit_code()` and calls `emscripten_force_exit(exit_code)`. Setup failure exits with `EXIT_FAILURE` (or `EXIT_SUCCESS` for `--help`/`--version`); `Main::start()`'s return becomes the exit code — `GODOT/platform/web/web_main.cpp` lines 61–74, 104–110, 146–180 (local).
- Command-line args come from the engine config `args` (exported debug flags are written into `GODOT_CONFIG.args`); `startGame` prepends `--main-pack <exe>.pck` — `GODOT/platform/web/export/export_plugin.cpp` lines 142–152; `js/engine/engine.js` around line 200 (local).
- The shipped HTML shell calls `engine.startGame({onProgress})` and sets no `onExit`; `GODOT_CONFIG` is a literal in the page — `GODOT/misc/dist/html/full-size.html` lines 112–114, 200–212 (local).
- `JavaScriptBridge` eval is a build option `javascript_eval` (default `True`, defines `JAVASCRIPT_EVAL_ENABLED`) — `GODOT/platform/web/detect.py` lines 54, 268–269 (local).
- Godot's own `web_builds.yml` CI only builds (Emscripten on `ubuntu-26.04`); it runs no tests in a browser — [godotengine/godot .github/workflows/web_builds.yml](https://github.com/godotengine/godot/blob/master/.github/workflows/web_builds.yml) (fetched via GitHub API, grep for test/serve/browser found none).
- `web_main.cpp` contains `TEST_MAIN_OVERRIDE`, i.e. Godot's doctest unit tests can be compiled into a web build — `GODOT/platform/web/web_main.cpp` line ~141 (local).

### Inferences
- `--headless` on the web template would make `DisplayServerWeb::get_singleton()` a mis-cast `DisplayServerHeadless`, so it is unsupported in practice (undefined behaviour, likely a crash on the first frame). Not run. Consequently "headless" for web tests means a headless *browser* with software WebGL 2, not Godot's `--headless`.
- Node is not a realistic host: the runtime needs DOM, canvas and WebGL 2. No source found of Godot web running in Node.
- A harness should not use the shipped `index.html`; it should load `index.js` in its own page (or inject via the custom shell) and call `new Engine({...GODOT_CONFIG, args: [...test args], onPrint, onPrintError, onExit})`. `onExit` gives the exit code directly; stdout/stderr go to the harness. The FS-sync wait before exit means `onExit` fires asynchronously after `quit()`.
- Godot's own CI provides no precedent for running tests in a browser (fits the "precedent or remove" rule as a caution).

### Gaps
- Not verified by running: whether `get_tree().quit(code)` reliably triggers `onExit` with that code in `web_nothreads_debug` 4.7.2, and whether the nothreads template's `emscripten_force_exit` works with `EXIT_RUNTIME` settings. A 20-minute experiment with a pinned headless shell would settle it.
- No primary source on running Godot web with a "dummy" rasterizer in the browser.

## Q3. GdUnit4 in an exported (web) build; prior art

### Takeaway
GdUnit4 has, since late 2025 and mid 2026, deliberately decoupled its core from
`EditorInterface` so its CLI runner works on **template** (export) binaries; there is no
web-specific support, documentation or issue. Prior art for Godot tests in a browser is
thin: an AI-agent skill that drives a Godot web export through Chrome DevTools, and generic
WebGL+Playwright game setups.

### Cited Findings
- gdUnit4 moved to `godot-gdunit-labs/gdUnit4`. Issue GD-969 "Allow running tests in exported projects and on devices" (opened 2025-10-28 by a Sentry SDK contributor) reports that `GdUnitTestSuite.new()` failed to compile in exports because the chain `GdUnitTestSuite > … > GdUnitSettings > GdUnitShortcut > GdUnitCommandHandler` references `EditorInterface`; the reporter states the goal "run tests on mobile devices, and eventually on Web exports and game console kits" and plans a test main-loop script with baked-in args via the export "Extra Args" — [gdUnit4#969](https://github.com/godot-gdunit-labs/gdUnit4/issues/969). The maintainer says `GdUnitTestCIRunner` "should be independent of the Godot Editor and also run on mobile devices" — same issue.
- Fixed by PR GD-969 "Decoupling editor interface calls from test execution", merged 2025-10-29 — [gdUnit4#973](https://github.com/godot-gdunit-labs/gdUnit4/pull/973).
- TASK-1236 / PR #1237 (merged 2026-07-10) "Make GdUnitEditorColorTheme template-build-safe": editor-only classes "do not exist in template builds (exported games, headless CLI test runners)"; acceptance criterion: "`GdUnitCmdTool.gd` runs on a `template_debug` binary without any `EditorSettings`/`EditorInterface` parse errors"; observed in "the gdUnit4-coverage CI, which runs the CLI tool on a template-based runner binary" — [gdUnit4#1236](https://github.com/godot-gdunit-labs/gdUnit4/issues/1236), [gdUnit4#1237](https://github.com/godot-gdunit-labs/gdUnit4/pull/1237).
- Search of gdUnit4 issues for "web"/"html5" found only #655 (visual regression testing, open) and #969 — `gh search issues --repo godot-gdunit-labs/gdUnit4` (2026-11-23).
- A docs PR "GD-693: Document how to export Games with installed gdunit4 plugin" (merged 2025-06-25) concerns excluding gdUnit4 from game exports — [gdUnit4#788](https://github.com/godot-gdunit-labs/gdUnit4/pull/788).
- Prior art: the `godot-web-e2e` agent skill exports with `godot --headless --export-release`, serves over HTTP "to avoid file:// restrictions", focuses the canvas, injects input and checks console logs (Chrome DevTools, not Playwright) — [skills.sh godot-web-e2e](https://www.skills.sh/chen19007/my_skills/godot-web-e2e). Generic WebGL game e2e uses a readiness attribute on the canvas and screenshot diffs — [barthpaleologue blog](https://barthpaleologue.github.io/Blog/posts/webgl-webgpu-playwright-setup). A "Web export test tool for Godot 4.2" exists for manual feature checks — [pkostic-dev/tool-web-test](https://github.com/pkostic-dev/tool-web-test).
- Web export restriction: C# projects cannot be exported to the web in Godot 4 — [Godot docs (search summary)](https://docs.godotengine.org/en/latest/tutorials/export/exporting_for_web.html).

### Inferences
- Running GdUnit4 on the web means: export a *test pack* (test suites + gdUnit4 core, without its editor UI) with the web template, start it with GdUnit's CLI runner as main scene/script via `args`, and get results out through `onPrint` (console reporter) and `onExit` (exit code). GdUnit's file-based reports (JUnit XML under `res://reports`/`user://`) land in the browser's in-memory/IndexedDB FS, so the harness would need `JavaScriptBridge` or stdout parsing to emit `$XML_OUTPUT_FILE` for Bazel.
- Test discovery by scanning `res://` for `*.gd` may behave differently in an exported pack (scripts may be exported as binary tokens; `.remap` files). Unverified; this is the most likely porting snag besides the editor-class decoupling.
- No one appears to run GdUnit4 in a browser in public; option B would be first-of-its-kind, which weighs against it under the "precedent or remove" rule.

### Gaps
- No gdUnit4 documentation or test evidence for web exports was found.
- The gdUnit4-coverage CI's template runner setup was not inspected.

## Q4. CI cost and feasibility of headless Chrome with WebGL on Linux

### Takeaway
Headless Chrome on GPU-less Linux gets WebGL only via SwiftShader, which Chrome
deprecated as an automatic fallback (from Chrome 130) and now requires explicit opt-in
(`--enable-unsafe-swiftshader`, `--use-angle=swiftshader-webgl`). It still works as an
opt-in in early 2026, but pinning the browser version is essential. Godot's
Compatibility renderer on SwiftShader is CPU-heavy; expect seconds of startup per test
target, plus download of a ~40 MB wasm per run.

### Cited Findings
- Chromium SwiftShader doc (current main): automatic fallback deprecated, "WebGL context creation will soon fail instead of falling back to SwiftShader"; opt-in flags `--use-gl=angle --use-angle=swiftshader-webgl --enable-unsafe-swiftshader`; headless/GPU-less testing "will still be supported by opting in but is not intended for running untrusted content" — [chromium docs/gpu/swiftshader.md](https://chromium.googlesource.com/chromium/src/+/main/docs/gpu/swiftshader.md).
- Deprecation began in Chrome 130; Chrome 139 planned Finch experiments removing SwiftShader on macOS/Linux and replacing it with WARP on Windows; an enterprise policy re-enables SwiftShader — [blink-dev "Intent to Remove: SwiftShader Fallback"](https://groups.google.com/a/chromium.org/g/blink-dev/c/yhFguWS_3pM) (2024–2025 thread).
- chromedp added `--enable-unsafe-swiftshader` together with `--disable-gpu` to keep headless WebGL working — [chromedp v0.14.1 commit](https://chromium.googlesource.com/external/github.com/chromedp/chromedp/+/refs/tags/v0.14.1).
- A Feb 2026 Chromium review states that if SwiftShader is allowed in the fallback list (WARP or `--enable-unsafe-swiftshader`) the GPU process starts in SwiftShader — [blink-dev archive msg15540](https://go.mail-archive.com/blink-dev@chromium.org/msg15540.html) (search summary).
- Chrome DevRel: headless WebGL/WebGL2 reported as disabled or software-only unless ANGLE/Vulkan flags are set — [developer.chrome.com "Supercharge Web AI testing"](https://developer.chrome.com/blog/supercharge-web-ai-testing). Known issue: WebGL in headless mode on ARM Mac since Chrome 111 — [chromium-dev thread](https://groups.google.com/a/chromium.org/g/chromium-dev/c/8eR2GctzGuw).
- Godot 4 web targets only WebGL 2.0 with the Compatibility renderer; Forward+/Mobile unsupported — [Godot 4.7 docs, Exporting for the Web](https://docs.godotengine.org/en/4.7/tutorials/export/exporting_for_web.html).
- Example CI timing knobs from a WebGL e2e project: 15 s readiness and screenshot timeouts, 2 retries on CI, Docker image pinned to Playwright 1.52.0 — [barthpaleologue blog](https://barthpaleologue.github.io/Blog/posts/webgl-webgpu-playwright-setup).
- The template ZIP's wasm is large: the dlink side module alone is 44 MB per the prototype notes — `RG/docs/internal/web-prototype.md` decision 2 (local).

### Inferences
- Feasible on Linux x86_64 RBE and GitHub-hosted runners with a pinned `chrome-headless-shell` and the SwiftShader opt-in flags; the risk is Chrome removing the opt-in in a future version, mitigated by pinning.
- On the macOS VM, headless Chrome can use the real GPU via Metal/ANGLE, but the cited ARM-Mac headless WebGL issue makes this less predictable than Linux+SwiftShader.
- Cost per web test target ≈ browser startup + wasm compile (tens of MB) + SwiftShader rendering; tests that do not render (pure logic) still pay the WebGL context and the boot. A single bundled "all web tests" target per project would amortize this better than one browser per test file.

### Gaps
- No measured numbers for Godot web boot time under SwiftShader; no flakiness data specific to Godot. A bounded experiment (one export, one headless-shell, 10 runs) would supply them.
- Whether stable Chrome 14x/15x/16x still honours `--enable-unsafe-swiftshader` was not confirmed from release notes; only the Feb 2026 code review indicates it.

## Q5. `bazel run`: how Godot serves, headers, `file://`, browser launch and a "device" concept

### Takeaway
Godot's editor serves the export from its own HTTP server on `localhost:8060` (editor
settings `export/web/http_host`, `http_port`, `use_tls`, `tls_key`, `tls_certificate`;
self-signed cert if TLS without key), always sending COOP/COEP, `Access-Control-Allow-Origin: *`
and `Cache-Control: no-store`, then `shell_open`s the URL in the default browser. The
prototype matches this. Headers are only required for threads/extensions; `file://` is
not a supported way to open an export. A browser choice can map onto `--device` the way
Python's `webbrowser.get(name)` names browsers.

### Cited Findings
- Editor settings defaults: `export/web/http_host = "localhost"`, `http_port = 8060`, `use_tls = false`, `tls_key = ""`, `tls_certificate = ""` — `GODOT/platform/web/export/export.cpp` lines 45–50 (local).
- "Run in Browser" = export to the editor temp dir `web/tmp_js_export.html`, start the server (`_start_server(bind_host, bind_port, use_tls)`), then `OS::shell_open("http(s)://<host>:<port>/tmp_js_export.html")`; a FIXME notes export files are never cleaned up; there are also "Start HTTP Server", "Re-export Project" and "Stop HTTP Server" options — `GODOT/platform/web/export/export_plugin.cpp` lines 704–745, 779–885 (local).
- Host resolution: an IP or a resolved hostname; invalid host fails with "Try using '127.0.0.1'" — `export_plugin.cpp` lines 889–896 (local).
- TLS: with `use_tls` and no key/cert, the editor generates a 2048-bit RSA key and a self-signed certificate `CN=godot-debug.local` cached as `html5_server.key/.crt` in the editor cache dir — `GODOT/platform/web/export/editor_http_server.cpp` lines 57–73, 210–232 (local).
- Response headers: `Content-Type`, `Access-Control-Allow-Origin: *`, `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Embedder-Policy: require-corp`, `Cache-Control: no-store, max-age=0`; only files whose extension is in a MIME table (`html`, `js`, `json`, `pck`, `png`, `svg`, `wasm` → `application/wasm`, …) and that exist in the temp dir are served — `editor_http_server.cpp` lines 89–115, 246–252 (local).
- Godot's dev script `platform/web/serve.py`: port 8060 default, dual-stack bind, COOP/COEP + `Access-Control-Allow-Origin: *`, opens `http://127.0.0.1:<port>` with `open`/`xdg-open`/`os.startfile`, `--no-browser` flag — `GODOT/platform/web/serve.py` (local). Docs: serve.py is for testing only, use Apache/nginx in production — [Godot 4.7 docs](https://docs.godotengine.org/en/4.7/tutorials/export/exporting_for_web.html).
- Headers per variant: COOP `same-origin` + COEP `require-corp` are needed for Thread Support, and "Like thread support, enabling [Extensions Support] requires the use of cross-origin isolation headers"; the single-threaded export has no listed header requirement; the PWA option can emulate the headers via a service worker, which still needs a secure context (localhost usually exempt); `.wasm` should be `application/wasm` — [Godot 4.7 docs, Exporting for the Web](https://docs.godotengine.org/en/4.7/tutorials/export/exporting_for_web.html).
- `file://`: the godot-web-e2e workflow serves over HTTP "to avoid file:// restrictions" — [skills.sh godot-web-e2e](https://www.skills.sh/chen19007/my_skills/godot-web-e2e). The 4.7 docs page does not discuss `file://` (checked).
- Prototype launcher: `ThreadingHTTPServer(("127.0.0.1", 8060))`, COOP/COEP + `Cache-Control: no-store`, `.wasm`/`.pck` MIME additions, `webbrowser.open(url)` unless `--headless`; options `headless`, `detach`, `env` — `RG/tools/platforms/launch/launch_web.py` (local). Shared launcher options include `--device`, `--list-devices`, `--no-start-device`, `--headless` ("Godot --headless, emulator -no-window, no Simulator window") — `RG/tools/platforms/launch/launch_common.py` lines 33–77 (local).
- Prior art for a browser "device" in Flutter: `flutter run -d chrome` / `-d web-server` (well-known CLI behavior; no source fetched — see Gaps).

### Inferences
- The prototype's headers are a superset of what nothreads needs and match the editor's, so threads would work unchanged; adding `Access-Control-Allow-Origin: *` would make it identical to Godot's two servers. `Cache-Control: no-store` is useful because Bazel rebuilds overwrite the same URLs.
- Port: Godot's editor binds `localhost` by default while `serve.py` binds all interfaces; binding `127.0.0.1` is the safe choice. A fixed 8060 collides when two `bazel run`s run concurrently; binding port 0 (OS-chosen) or falling back to the next free port and printing the URL is the usual fix. Keeping 8060 as the default preserves Godot familiarity; `localhost`/`127.0.0.1` keeps a secure context, so even threaded/PWA builds work without TLS.
- TLS is only needed for LAN access from a phone (secure context for threads/PWA); the editor's self-signed-cert approach is the precedent, but it is out of scope for a local `bazel run`.
- `--device` for web can mean "which browser": `webbrowser.get("firefox"|"chrome"|"safari")` names (stdlib) or a pinned headless Chrome for `--headless`; `--list-devices` could list `webbrowser` registered browsers. Under `--headless`, launching the pinned `chrome-headless-shell` with the harness page and streaming `onPrint` to stdout, ending with `onExit`'s code, would give `bazel run --headless` the same semantics as desktop `--headless` and be the shared base for test option B.

### Gaps
- Flutter's `-d chrome` / `web-server` device model and Python `webbrowser` browser names are from general knowledge, not fetched sources in this session; verify before citing.
- The Godot docs page fetched did not cover remote debugging over the web server, `file://`, or exit codes.
