# Web tests: experiments for "Run godot_test in the browser" (#199)

Experiments against the prototype at `3d91f7c5e` (branch `claude/web-builds-prototyp-df2828`),
in a throwaway worktree. The coordinator later asked to judge everything against the shape
**"a test of a web application"**: a test target starts a built `godot_app` web output in
the pinned headless browser and passes when the project exits with 0 (`bazel run --
--headless` as a test). Questions 3 and 4 are answered for that shape. Questions 1 and 2 were
settled quickly and answer "can a project run GdUnit itself inside such an application test":
**yes**, with two conditions (scripts exported as text; the main loop named by a project
setting, not `--script`).

## Setup

| | |
| --- | --- |
| Host | Apple M5 Max, 18 cores, 128 GB, macOS 27.2.1 |
| Bazel | 9.3.0 (Bazelisk 1.29.0) |
| Godot | 4.7.2.stable.official.ed1daf0bf, template `web_nothreads_debug` (Emscripten 4.0.20) |
| GdUnit4 | 6.2.2 at commit `0127a55f` (the version `addons/gdunit` pins) |
| Browser | rules_browsers 0.4.0 (BCR), default Chrome for Testing **chrome-headless-shell 147.0.7687.0** |
| Remote | BuildBuddy, `--config=buildbuddy`, `UBUNTU24_04_IMAGE` executor, test action in `mcr.microsoft.com/playwright:v1.49.1-noble` |

Everything lives in a new package `addons/gdunit/examples/web_exp/` of the gdunit examples
module (copied here as [`web_exp/`](web_exp/)); module and `.bazelrc` changes are in
[`module-and-bazelrc.diff`](module-and-bazelrc.diff). Run from `addons/gdunit/examples`:

```sh
bazel test //web_exp:smoke_app_test //web_exp:gdunit_app_test --config=webtestb          # host
bazel test //web_exp:smoke_app_test //web_exp:gdunit_app_test --config=webtestb --config=buildbuddy  # Linux executor
web_exp/measure.sh local-serial 10 --local_test_jobs=1                                    # Q4 numbers
```

| File | What it is |
| --- | --- |
| [`web_exp/web_test_runner.py`](web_exp/web_test_runner.py) | The harness: stdlib HTTP server on `127.0.0.1:0`, an in-memory harness page that starts the engine with `Engine` (`init` + `preloadFile` + `start`), `onPrint`/`onPrintError`/`onExit` batched to `POST /__log` and `/__exit`; starts Chrome with a fresh profile; Bazel's test contract (`XML_OUTPUT_FILE`, `TEST_UNDECLARED_OUTPUTS_DIR`, sharding, `--test_filter`); ends with the engine's exit code. |
| [`web_exp/web_run.gd`](web_exp/web_run.gd) | GdUnit adapter inside the pack: `class_name GdUnitWebRunner extends SceneTree`, runs `GdUnitTestCIRunner` like `addons/gdunit/private/run.gd`, then hands the JUnit XML to the page. |
| [`web_exp/smoke/smoke.gd`](web_exp/smoke/smoke.gd) | The smallest application test: draw one frame, `quit(0)`. |
| [`web_exp/browser/`](web_exp/browser/) | **Variant B** (recommended): the browser as a toolchain of the test rule's own `test` exec group, plus an incompatible default test toolchain for the web. |
| [`web_exp/toolchains/`](web_exp/toolchains/BUILD.bazel), [`web_exp/defs.bzl`](web_exp/defs.bzl) | **Variant A**: toolchains of `default_test_toolchain_type` for the web, Chrome chosen by `select` in the exec configuration. |
| [`web_exp/measure.sh`](web_exp/measure.sh) | Repeats the tests and summarizes the runner's timings. |
| [`logs/`](logs/) | Logs cited below (ANSI and Chrome noise stripped). |

## 1. Does GdUnit find and run suites inside an exported web pack?

**Answer.** Yes, when the pack's scripts are exported as **text** (`script_export_mode` 0):
discovery (directory and single file), execution, parameterized tests, mocks and spies, the
JUnit report and GdUnit's exit codes (0 pass, 100 failure) all work in the browser. With
**binary tokens** (1) or **compressed tokens** (2) GdUnit finds nothing, and fixing its
discovery only moves the failure, because GdUnit parses the suites' source code. Separately,
Godot 4.6+ export templates **ignore `--script`**, so the runner must be the pack's main loop.

**Evidence.**

1. *`--script` is compiled out of official templates.* godotengine/godot#111909 ("Disable
   some unsafe CLI arguments in template builds by default", merged 2025-11-12, Godot 4.6+)
   adds the SCons option `disable_path_overrides`, default `True`; without
   `OVERRIDE_PATH_ENABLED`, `main.cpp` clears `script`, `game_path` and `main_loop_type` from
   the command line (main/main.cpp at 4.7.2-stable, around line 4320). Observed: with
   `args: ["--script", "res://web_run.gd", ...]` the engine starts, prints nothing more, and
   idles. This holds for every official 4.6+ template, desktop `template_debug` too; the
   GdUnit PRs about `template_debug` predate it. `--main-pack` stays available on the web.
   *Fix in how we export:* the pack sets `application/run/main_loop_type` to the adapter's
   global class (`godot_pack(settings = {"application/run/main_loop_type": '"GdUnitWebRunner"'})`),
   which `main.cpp` still reads from the project. A project without a main scene also needs a
   nonempty `main_args`, or Godot stops with "Can't run project: no main scene defined" (and
   reports **exit 0** on the web, see "Exit codes" below); the harness passes an unknown
   option `--autoload-test` before `--`, which Godot keeps in `main_args` and ignores. A main
   scene would do as well.

2. *Packs in fastbuild are text anyway.* `godot_pack` writes the PCK without Godot unless
   `-c opt` or `--@autoload_rules_godot//godot:pack_conversion=godot`
   (`rules_godot/godot/private/pack_conversion.bzl`), so `preset_settings.script_export_mode`
   only takes effect with the latter. The experiment builds with `pack_conversion=godot` and
   checks the PCK: mode 0 stores `suites/PassingTest.gd` as text; modes 1 and 2 store
   `suites/PassingTest.gd.remap` + `suites/PassingTest.gdc` (`GDSC` header).

3. *Results* (`-a res://suites`, debug nothreads template, `logs/q1_*.log`,
   `logs/q1_summary.txt`):

   | Export | GdUnit's scan | Adapter discovers through `ResourceLoader` (`--resolve-remaps`) |
   | --- | --- | --- |
   | text (0) | 9 tests in 3 suites, 1 deliberate failure, mocks/spies pass, exit 100 | same |
   | binary (1) | "No test cases found", runner exit 1 (no JUnit) | 7 tests found (parameterized not expanded), 7× "Precondition: The parameter 'source_file' is not set", exit 105 |
   | compressed (2) | as binary | as binary |

   With `-a res://suites/PassingTest.gd` in binary mode GdUnit prints "Given directory or file
   does not exists": `GdUnitTestSuiteScanner.scan` uses `FileAccess.file_exists`, which sees
   only `.remap`/`.gdc`; its directory scan sees no `.gd` extension. The `ResourceLoader`
   override (in `web_run.gd`, `WebRunner.discover_tests`) gets past that, but
   `GdUnitTestDiscoverer.discover_tests_from_gd_script` calls
   `GdScriptParser.get_function_descriptors`, which reads `script.source_code` — empty for
   token scripts. Mocks/spies (`GdUnitMockBuilder` uses `MOCK_TEMPLATE.source_code`) and
   the orphan monitor depend on source too. Making binary tokens work means patching GdUnit's
   parser-based discovery, not our export.

4. *Smallest change that makes it work:* the test application's pack exports scripts as text
   (fastbuild default; explicit `script_export_mode = "0"` for `-c opt`) and names the adapter
   as main loop. No GdUnit patch. Text scripts also keep GdUnit's failure lines
   (`res://suites/FailingTest.gd:4`).

5. *Console output:* GdUnit's colored console reaches `onPrint` with ANSI escapes; engine
   errors from `assert_error` and GdUnit's deliberate `push_error` arrive on `onPrintError`
   with GDScript backtraces (debug template).

**Unverified / open.**

- GdUnit's **HTML report** fails: `GdUnitHtmlPatterns.load_template` gets null and
  "Source directory not found 'res://addons/gdUnit4/src/reporters/html/template/css/'".
  The templates are non-resource files the export leaves out; the preset's `include_filter`
  would add them, but `godot_pack.preset_settings` supports only `script_export_mode`. JUnit
  is unaffected and the run's exit code is not changed by it.
- Test-level filters (GdUnit `-i suite:test`, or a test name with `-a`) were not tried.
- Scene-based tests and input (`GdUnitSceneRunner`) were not tried; the display server is
  `web` (WebGL2 through SwiftShader), not `headless`.

## 2. How does the report leave the browser?

**Answer.** Three ways work, all shown in [`web_test_runner.py`](web_exp/web_test_runner.py)
and [`web_run.gd`](web_exp/web_run.gd); the simplest robust one is **JavaScriptBridge**: the
adapter reads `results.xml` from `user://` and calls a function of the harness page, which
POSTs it to the host. Emscripten's `FS` is **not** reachable from the page.

**Evidence.** Every run printed `report channels ["bridge:results.xml",
"indexeddb:/userfs/godot/app_userdata/gdunit web experiment/gdunit/report_1/results.xml",
"log:results.xml"]`, and `bazel-testlogs/.../test.xml` is GdUnit's JUnit
(`<testsuites ... tests="7" failures="0">`).

- **JavaScriptBridge** (official templates are built with `javascript_eval=yes`):
  ```gdscript
  var window: JavaScriptObject = JavaScriptBridge.get_interface("window")
  if window != null and window.godotTestReport != null:
      window.godotTestReport("results.xml", FileAccess.get_file_as_string(results))
  ```
  ```js
  window.godotTestReport = (name, text) => { flush(); post('/__report?channel=bridge&name=' + encodeURIComponent(name), text); };
  ```
  It runs before `quit()`, ordered with the log, independent of IDBFS timing.
- **IndexedDB after exit.** `user://` is IDBFS at `/userfs`; the database `/userfs`, store
  `FILE_DATA`, holds the files by path (value `.contents`, a `Uint8Array`). The page reads it
  in `onExit` (after 200 ms) and POSTs every file; the runner writes them to
  `TEST_UNDECLARED_OUTPUTS_DIR/userfs/`. It worked in every run, but relies on Godot having
  synced IDBFS before exit; not studied under load.
- **The log.** The adapter prints the XML between `@@JUNIT-BEGIN@@`/`@@JUNIT-END@@`; works,
  but mixes report and log and depends on every print arriving.
- **Not possible:** `Module.FS`. `index.js` exports only `copyToFS` (write), `initFS`,
  `callMain`, `request_quit` etc.; `FS` is in Emscripten's "missing exports" list, and
  `Engine`'s `onExit` cleanup sets `engine.rtenv = null`.
- GdUnit writes to `user://`: `res://` (the default `res://reports`) is the read-only pack.
  The report path is `/userfs/godot/app_userdata/<config/name>/...`.

For a general application test (not GdUnit) the same bridge could carry any file the project
wants on the host (`TEST_UNDECLARED_OUTPUTS_DIR`), since the project cannot read environment
variables in the browser.

## 3. Execution platform for a web test in Bazel

**Answer.** Give the web test rule **its own `test` exec group** whose toolchain is the
browser: toolchains with `target_compatible_with = [@platforms//os:emscripten]` and
`exec_compatible_with` = each platform that has a pinned Chrome. Bazel then runs the test on
the first such execution platform (BuildBuddy Linux when `--config=buildbuddy`, else the
host) and the toolchain brings that platform's Chrome. Register in addition an
**incompatible** `default_test_toolchain_type` toolchain for the web: every other test rule
— `godot_test`/`gdunit_test`, any test without its own exec group — becomes incompatible
(skipped in wildcards, "incompatible and cannot be built" when requested). Bazel 9.3.0.

**Evidence.**

- Baseline: `bazel test //web_exp:gdunit_web_passing_test --config=web` → "No matching
  toolchain found for type @bazel_tools//tools/test:default_test_toolchain_type, which is
  required to run tests for target platform ...:web_wasm32". It fails at the test action, after
  the build.
- **Variant B** ([`web_exp/browser/`](web_exp/browser/), `--config=webtestb` =
  `--extra_toolchains=//web_exp/browser:all`), minimal Starlark:
  ```starlark
  toolchain_type(name = "browser_toolchain_type")
  browser_toolchain(name = "chrome_linux_x86_64",
      chrome = "@rules_browsers_chrome_linux//:chrome-headless-shell-linux64/chrome-headless-shell",
      files = ["@rules_browsers_chrome_linux//:info"])
  toolchain(name = "browser_linux_x86_64",
      exec_compatible_with = ["@platforms//os:linux", "@platforms//cpu:x86_64"],
      target_compatible_with = ["@platforms//os:emscripten"],
      toolchain = ":chrome_linux_x86_64", toolchain_type = ":browser_toolchain_type")
  # ... the same for macos/arm64 (mac_arm)

  no_test_toolchain(name = "no_test", target_compatible_with = ["@platforms//:incompatible"])
  toolchain(name = "web_default_test",
      target_compatible_with = ["@platforms//os:emscripten"],
      toolchain = ":no_test",
      toolchain_type = "@bazel_tools//tools/test:default_test_toolchain_type")

  web_browser_test = rule(..., test = True,
      exec_groups = {"test": exec_group(toolchains = [":browser_toolchain_type"])},
      attrs = {"_runner": attr.label(default = ..., executable = True, cfg = config.exec("test")), ...})
  # impl: ctx.exec_groups["test"].toolchains[BROWSER_TOOLCHAIN].chrome
  ```
  Results:
  - `bazel test //web_exp/browser/tests:all --config=webtestb` (host): `browser_toolchain_test
    PASSED`, the unmarked `gdunit_test` `desktop_test` **SKIPPED**, a toolchain-free
    `trivial_test` **SKIPPED**.
  - Same with `--config=buildbuddy`: `browser_toolchain_test PASSED` (remote), the others
    SKIPPED.
  - Requested explicitly: "Target //web_exp/browser/tests:desktop_test is incompatible and
    cannot be built, but was explicitly requested. //web_exp/browser:no_test <-- target
    platform (...web_wasm32) didn't satisfy constraint @@platforms//:incompatible". So a
    resolved toolchain that is incompatible makes its dependent incompatible; `godot_test`'s
    `TEST_EXEC_GROUPS` declares the default test toolchain type (optional), and it propagates
    there too.
  - On the host platform, the browser test with `target_compatible_with =
    ["@platforms//os:emscripten"]` is SKIPPED in a wildcard and refused when requested.
- **Variant A** ([`web_exp/toolchains/`](web_exp/toolchains/BUILD.bazel), `--config=webtest`):
  toolchains of `default_test_toolchain_type` with `target_compatible_with` emscripten/wasm32
  and `exec_compatible_with` per Chrome platform, `empty_toolchain`; Chrome and runner come
  from `cfg = config.exec("test")` with a `select` over the exec platform's constraints.
  Works locally and remotely (`--toolchain_resolution_debug` in
  `logs/q3_remote_toolchain_resolution.log`: "Selected execution platform
  @@toolchains_buildbuddy...//:platform_linux_x86_64"). **But** it also lets every other test
  run on the web configuration: the unmarked desktop `gdunit_test` ran the macOS editor on
  the host and failed `test_platform_is_web` — wrong results instead of a skip. Variant A
  only works with `target_settings` or marking every other test; variant B gets the skip for
  free.
- Wildcard hygiene, both variants: host-tool targets in a package that a web wildcard covers
  must be incompatible on the web (the `py_binary` runner: "No matching toolchains found for
  types @bazel_tools//tools/python:toolchain_type"), and a `select` over exec platforms needs
  a default (`:no_chrome`, incompatible). In the ruleset, those live in rules_godot, outside
  consumer wildcards.
- Remote specifics: Chrome must run with `--no-sandbox` inside Bazel's sandbox ("sandbox
  initialization failed: Operation not permitted" under darwin-sandbox) and on the executor;
  its profile must be under a short path (`/tmp`; macOS limits Unix socket paths to 104
  bytes, `TEST_TMPDIR` is longer — Chrome hung silently); and BuildBuddy's Ubuntu 24.04 image
  lacks Chrome's libraries ("libnspr4.so: cannot open shared object file", exit 127). A
  per-target `exec_properties = {"test.container-image": "docker://mcr.microsoft.com/playwright:v1.49.1-noble"}`
  (only the `test` exec group) fixed that; the first run pulled the image (38 s wall).

**Unverified / open.**

- The incompatible default test toolchain belongs where the ruleset registers its test
  toolchains (`rules_godot/godot/private/config/BUILD.bazel`); not tried from there, nor its
  interplay with a consumer's own test toolchains.
- Which image to use remotely: a pinned image with Chrome's libraries, or shipping the
  libraries hermetically. Linux arm64 has no pinned Chrome (no toolchain, so no exec platform
  for web tests there).
- `rules_browsers` 0.4.0 pulls `aspect_bazel_lib` 2.14.0, whose coreutils toolchain fails in
  Bazel 9 (`rule() got unexpected keyword argument 'incompatible_use_toolchain_transition'`);
  the experiment raises it with `bazel_dep(name = "aspect_bazel_lib", version = "2.22.5")`.
  The ruleset would rather depend only on the Chrome archives (or pin rules_browsers' version
  table) than on rules_browsers' JS stack. Fetching Chrome took seconds (cached).

## 4. Cost and stability

**Answer.** An application test costs **about 1–2 s** of runner time and **2–4 s** of Bazel
test time on this host and on a BuildBuddy Linux executor, dominated by wasm compilation and
engine start, not by Chrome. No flake in 110 runs. Software rendering is in effect
(SwiftShader). Sharding and `--test_filter` map cleanly onto suite selection on the host.

**Evidence** (`web_exp/measure.sh`, fresh Chrome profile per run, `--disable-gpu
--enable-unsafe-swiftshader --use-angle=swiftshader`, `--audio-driver Dummy`, medians with
min–max, seconds). The page reports `ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (LLVM
10.0.0)), SwiftShader driver)` on macOS and `... (Subzero) ...` on Linux.

| Run | Test | Exit 0 | Runner total | Chrome start | Fetch wasm+pck | Wasm compile + engine init | Project run |
| --- | --- | --- | --- | --- | --- | --- | --- |
| host, serial (10) | smoke | 10/10 | 0.88 (0.84–1.40) | 0.12 | 0.11 | 0.29 | 0.11 |
| host, serial (10) | GdUnit, 7 tests | 10/10 | 1.44 (1.42–1.46) | 0.11 | 0.11 | 0.64 | 0.33 |
| host, 8 parallel (30) | smoke | 30/30 | 1.33 (1.18–2.16) | 0.26 | 0.20 | 0.39 | 0.22 |
| host, 8 parallel (30) | GdUnit, 7 tests | 30/30 | 2.72 (1.96–3.44) | 0.59 | 0.43 | 0.89 | 0.59 |
| BuildBuddy Linux (10) | smoke | 10/10 | 1.00 (0.95–1.57) | 0.11 | 0.13 | 0.48 | 0.09 |
| BuildBuddy Linux (10) | GdUnit, 7 tests | 10/10 | 1.93 (1.56–2.89) | 0.12 | 0.12 | 1.01 | 0.43 |

"Runner total" is Chrome launch to engine exit; Bazel reported 1.8–4.1 s per test action
(adds Python startup and sandbox setup). The site is 39 MB (`index.wasm` 37.9 MB, PCK 1.1 MB
with GdUnit) served from localhost; the GdUnit pack's larger init (0.64 vs 0.29 s) is loading
GdUnit's ~250 scripts. Expect a remote first run to add the image pull.

**Sharding and filtering.** The runner applies Bazel's contract on the host, as
`rules_godot/godot/private/test_cases.gd` does in the pack: it touches
`TEST_SHARD_STATUS_FILE`, keeps suites containing `TESTBRIDGE_TEST_ONLY`, distributes them
round-robin over `TEST_TOTAL_SHARDS`, and passes the selection as GdUnit `-a <suite>` in the
engine config's `args`. `shard_count = 3`: shard 1 got `FailingTest`, 2 `MockTest`, 3
`PassingTest`; `--test_filter=Passing`: shard 1 ran `PassingTest`, shards 2 and 3 printed
"no suite" and **did not start a browser**. Selection must happen on the host: the browser
has no environment variables for the project, so in the pack it would need them passed as
arguments. Other GdUnit options pass through after `--` the same way.

**Exit codes (for the agent studying them).** Two observations: (1) Godot's "Can't run
project: no main scene defined" ends with `onExit(0)` on the web — a misconfigured test would
pass; (2) a project that quits within the first frames without `--audio-driver Dummy` raised
"TypeError: Failed to construct 'AudioWorkletNode'" and **`onExit` never fired** (the runner
timed out). With the dummy audio driver it did not recur. The runner also ends early when
Chrome exits on its own (it caught exit 127 remotely at once instead of timing out).

**Unverified / open.**

- No GPU comparison (hardware vs SwiftShader) and no `--headless` display server run.
- Projects that render heavily or load large packs; only a one-frame smoke project and 7 unit
  tests were measured.
- CI's Linux job hardware (only BuildBuddy executors), macOS x86_64, Windows.
- 110 runs show no flake; that bounds a flake rate only to roughly below 3 %.

## Recommendations for #199

- The test shape the coordinator proposes fits: a rule that takes a web `godot_app`, starts
  it in the pinned headless Chrome and passes on exit 0, with its own `test` exec group whose
  toolchain is the browser. It needs no editor, so it does not need `godot_test` at all.
- GdUnit runs inside such an application when the project's test pack (a) exports scripts as
  text and (b) names a GdUnit adapter as `application/run/main_loop_type` (or main scene); the
  adapter returns the JUnit XML through `JavaScriptBridge`. This could be what
  `autoload_gdunit` offers for the web, with the ruleset supplying only the application test.
- Register an incompatible default test toolchain for the web so every other test is skipped
  in web wildcards.
