# Defold: HTML5 playable ads and a small web engine

Researched 2026-11-23. Defold's current stable release is 1.14.1 (2026-11-10). Primary sources are Defold's manuals, the `defold/defold` and `defold/build-size` repositories, Defold's release notes on its forum, and the community tool `indiesoftby/defold-playable-ads` (MIT, by Artsiom Trubchyk, who also posts in Defold's forum; it is a third-party tool, not part of Defold). Source links into `defold/defold` point at the `dev` commit `2914ec8` (2026-11-23).

**Local measurements (2026-11-23).** Compression levels: gzip -9, zstd -19, brotli q11 with lgwin 24 (Node zlib), xz -9e.
- Stock engines: `dmengine_release.wasm` 1.13.0 and 1.14.1, downloaded from `d.defold.com`.
- Stripped engine: the playable tool's public demo HTML (gh-pages deploy of commit `dc2ed7c`, 2026-08-05). I decoded its embedded payloads. The wasm contains the version string `1.13.0`, the stable release when the demo was built.
- Section sizes: parsed from the wasm headers.

These findings are not repeated from `playable_ads.md` and `minimal_engine_size.md`: the network table, the zstd+base64 headline, the 2019 Facebook playable and the 32 MB heap advice.

## 1. Runtime: what Defold's web engine is and how big

### Takeaway
Defold ships one web runtime: a wasm-only `dmengine` built with Emscripten. asm.js (`js-web`) was removed in 1.13.0 (June 2026). The stock release engine is 2.37 MB raw / 0.98 MB gzip / 0.75 MB brotli in 1.13.0 and 3.03 MB / 1.24 MB / 0.94 MB in 1.14.1. A playable-stripped 1.13.0 engine is 1.67 MB raw, 0.69 MB gzip, 0.58 MB zstd and 0.54 MB brotli. That is about one tenth of the stripped Godot L2 engine (17.7 MB raw / 3.6 MB brotli). Two kinds of difference keep it small:
- Design: plain Lua 5.1 as the script runtime, no exceptions or RTTI, and a component set that is small by design.
- Build: link-time removal of whole subsystems.

Aggressive size flags play no part: the link runs at `-O3` and uses no LTO.

### Cited Findings
- **Runtime targets.** HTML5 bundles support two architectures: `wasm-web` (non-threaded) and `wasm_pthread-web`. When both are included, the loader picks the pthread engine if the page is cross-origin isolated. Defaults are `bob --architectures wasm-web` — [Defold HTML5 manual (doc repo, last change 2026-11-03)](https://defold.com/manuals/html5/), [Bob manual](https://defold.com/manuals/bob/).
- **asm.js removal.**
  - The removal was announced on 2026-03-10. The reasons given: Poki sees 100 % WebAssembly support, "Dropping asm.js will reduce maintenance effort and shorten CI build times", and asm.js "is the slowest platform to build and maintain" — [Defold forum: Removing Collada support and the asm.js platform (2026-03-10)](https://forum.defold.com/t/removing-collada-support-and-the-asm-js-platform/82506).
  - The release itself is change #11622, a breaking change: "bob.jar no longer supports js-web as a platform or architecture" — [Defold 1.13.0 release notes (forum)](https://forum.defold.com/t/defold-1-13-0-has-been-released/82980) and [Defold blog, 1.13.0 (2026-06-22)](https://defold.com/2026/06/22/Defold-1-13-0/).
  - Defold's size tracker notes "1.13.0-alpha, js-web support removed" — [defold/build-size comments.csv](https://github.com/defold/build-size/blob/master/comments.csv).
- **History of the stock release engine** (`dmengine_release.wasm`, raw bytes) — [defold/build-size engine_report.csv](https://github.com/defold/build-size/blob/master/engine_report.csv) (dashboard: [defold.com/build-size](https://defold.com/build-size)):

  | Version | wasm-web | js-web (asm.js) |
  | --- | ---: | ---: |
  | 1.3.0 (2022) | 2,178,435 | 4,523,948 |
  | 1.12.0 | 2,569,742 | 5,304,393 |
  | 1.13.0 | 2,369,043 | removed |
  | 1.13.1 | 2,385,802 | – |
  | 1.13.2 | 2,912,196 | – |
  | 1.14.1 | 3,026,820 | – |

  - The empty-project HTML5 bundle (zip) for 1.14.1 is 1,324,218 bytes — [defold/build-size bundle_report.csv](https://github.com/defold/build-size/blob/master/bundle_report.csv).
- **Local measurement of stock and stripped engines**:

  | Engine | raw | gzip -9 | zstd -19 | brotli 11 | xz -9e |
  | --- | ---: | ---: | ---: | ---: | ---: |
  | Stock 1.13.0 `dmengine_release.wasm` | 2,369,043 | 975,939 | 806,950 | 747,327 | 725,860 |
  | Stock 1.14.1 `dmengine_release.wasm` | 3,026,820 | 1,235,977 | 1,013,169 | 944,593 | 909,116 |
  | Stock 1.14.1 `dmengine_release.js` (glue) | 255,699 | 58,837 | 53,597 | 50,954 | 51,956 |
  | Playable demo 1.13.0, stripped `.wasm` | 1,665,182 | 693,138 | 578,188 | 535,399 | 519,340 |
  | Playable demo 1.13.0, `_wasm.js` glue | 271,437 | 63,168 | 57,238 | 54,437 | 55,448 |

  - Engine URLs: [1.13.0](https://d.defold.com/archive/stable/f735c12192bf95684e6ae1ae27c400b8170fc6d8/engine/wasm-web/dmengine_release.wasm) and [1.14.1](https://d.defold.com/archive/stable/ee283d4dad9fa451dd6399d83602e1dc25133681/engine/wasm-web/dmengine_release.wasm).
  - Demo: [indiesoftby.github.io/defold-playable-ads/index.html](https://indiesoftby.github.io/defold-playable-ads/index.html).
  - Sections of the stripped wasm: code 1,378,127 B, data 275,852 B, plus small import, elem and type sections. Stripping saves 29.7 % raw and 28.3 % zstd against stock 1.13.0.
- **Lua runtime.** The web build defines `DM_LUA_USE_LUA51` and links the `lua` library, not LuaJIT — [defold/defold share/extender/build_input.yml, `web` context](https://github.com/defold/defold/blob/2914ec826e4955ae0000935cdf3ea14bd363aa90/share/extender/build_input.yml#L520-L560).
- **Default engine libraries on the web.** The `web` context lists `engineLibs`:
  - Core: `engine`, `gameobject`, `resource`, `gamesys`, `script`, `lua`, `render`, `graphics`, `hid`, `input`, `dlib`, `lz4`, `zip`, `dmbedtls`, `liveupdate`.
  - Fonts: `font`, `font_richtext`, `font_render`, `font_gen`.
  - Components: `gamesys_gui`, `gamesys_particle`, `gamesys_model`, `gamesys_rig`, `gui`, `particle`, `rig`, `image`, `crashext`.
  - Physics: `physics`, `box2d_defold`, `script_box2d_defold`, `BulletDynamics`, `BulletCollision`, `LinearMath`, `script_bullet3d`.
  - Textures and sound: `graphics_transcoder_basisu`, `basis_transcoder`, `sound_nosimd`, `decoder_wav`, `decoder_ogg`.

  The renderer is selected by the symbol `GraphicsAdapterOpenGL` — [build_input.yml](https://github.com/defold/defold/blob/2914ec826e4955ae0000935cdf3ea14bd363aa90/share/extender/build_input.yml#L520-L560).
- **Graphics backends.** HTML5 can select WebGL, WebGPU or both through the app manifest; WebGL is the default — [App manifest manual (doc repo, last change 2026-11-03)](https://defold.com/manuals/app-manifest/). Since 1.14.1, WebGL 1 shaders are excluded by default — [HTML5 manual](https://defold.com/manuals/html5/).
- **Compile and link flags.**
  - Compile: `-fno-exceptions`, `-fno-rtti`, `-sDISABLE_EXCEPTION_CATCHING=1`, `GOOGLE_PROTOBUF_NO_RTTI` — [scripts/cmake/platform_html5.cmake](https://github.com/defold/defold/blob/2914ec826e4955ae0000935cdf3ea14bd363aa90/scripts/cmake/platform_html5.cmake).
  - Link on the build server: `optLevel: 3`, `linkFlags: ["--emit-symbol-map", "-O{{optLevel}}"]`, `ALLOW_MEMORY_GROWTH=1`, `INITIAL_MEMORY=33554432`, `IMPORTED_MEMORY=1`, `MAX_WEBGL_VERSION=2`, `STACK_SIZE=5242880`, `ERROR_ON_UNDEFINED_SYMBOLS=1`, plus a short `EXPORTED_FUNCTIONS` list — [build_input.yml `web`/`wasm-web`](https://github.com/defold/defold/blob/2914ec826e4955ae0000935cdf3ea14bd363aa90/share/extender/build_input.yml#L520-L578).
  - The config shows no `-Oz`, `-Os`, `-flto` or closure flag for the release link (same file).
- **Release variant.** Release engines drop `debugger`, `record*`, `engine_service`, `profile`, `profilerext` and `profiler_js`, and link `_null` replacements (`engine_release`, `engine_service_null`, `profile_null`, `profilerext_null`) — [share/extender/variants/release_input.appmanifest](https://github.com/defold/defold/blob/2914ec826e4955ae0000935cdf3ea14bd363aa90/share/extender/variants/release_input.appmanifest).
- **Per-function size tool.** Defold has its own: `scripts/web/wasm_symbol_sizes.py` combines the `.js.symbols` map from `--emit-symbol-map` with `bloaty` and writes a TSV of function sizes — [scripts/web/wasm_symbol_sizes.py](https://github.com/defold/defold/blob/2914ec826e4955ae0000935cdf3ea14bd363aa90/scripts/web/wasm_symbol_sizes.py). Since 1.13.0, symbols for both `wasm` and `pthread.wasm` bundles are published (#11387) — [1.13.0 release notes](https://forum.defold.com/t/defold-1-13-0-has-been-released/82980).
- **Rough gzip figures from users** [secondary]:
  - "Engine is about 1mb in gzip. Less if you remove some parts in appmanifest" (2024) — [Defold forum: Typical size for HTML5 build](https://forum.defold.com/t/typical-size-for-html5-build/78216).
  - An empty Defold 1.4.6 bundle downloads about 975 KB, or about 808 KB with an app manifest (server-gzipped; 2023, Defold staff) — [Defold forum: HTML5 bundle size](https://forum.defold.com/t/html5-bundle-size/73431).

### Inferences
- The 1.13.1 → 1.13.2 jump (+526 KB raw) falls in the release that added Rich Text by default and OTF/CFF font support ([1.13.2 release notes](https://forum.defold.com/t/defold-1-13-2-has-been-released/83276)). Rich Text can be removed again with **Use Rich Text = off**. The attribution is my inference: I found no published per-feature number for Rich Text.
- Defold reaches about 1.7 MB raw without `-Oz` or LTO. Its smallness therefore comes from scope and architecture, not compiler tuning:
  - a C-style engine with no exceptions or RTTI;
  - Lua 5.1 instead of a large VM or class database;
  - a fixed set of 2D-first components;
  - optional subsystems swapped for `_null` stubs at link time.

  Godot's 14.9 MB of code in the stripped L2 build is about 10.8× Defold's 1.38 MB code section.
- With the stripped Defold engine at about 0.54–0.58 MB compressed, the engine takes roughly a tenth of a 5 MB budget. The Godot L2 engine takes about three quarters.

### Gaps
- No public breakdown of Defold's 1.38 MB code section by subsystem. `wasm_symbol_sizes.py` needs the symbol map from a build; I did not run a build.
- Defold's own compile optimisation level for the prebuilt engine libraries (`-O2`, `-O3` or `-Os`) is not visible in the files I read. Only the extender link level (`-O3`) is confirmed.
- I found no Defold-published startup, compile or memory timings for the wasm engine on low-end Android.

## 2. App manifest and engine stripping

### Takeaway
Defold's app manifest is a YAML file of per-platform link-context edits: `excludeLibs`, `libs`, `excludeSymbols`, `symbols` and flags. The editor generates it from checkboxes. Each switch removes a prebuilt static library and links its `*_null` stub library instead. It also removes the subsystem's self-registration symbol from the exported-symbol list, so the linker drops the code. Assigning an app manifest in `game.project` makes Bob treat the project as having native extensions. Bob then sends it to Defold's build server ("Extender"), which **relinks** a custom engine from prebuilt libraries without recompiling the engine. This takes about 1–2 minutes and is free. A self-hosted Docker Extender is also possible.

### Cited Findings
- **Manifest switches.** The manual lists:
  - Physics 2D: Box2D v3, legacy Box2D, or None. Physics 3D (Bullet) on or off.
  - Rig + Model, or None.
  - Exclude Record and Profiler (Debug Only / None / Always).
  - Sound: Exclude Sound, Exclude WAV, Exclude OGG, Include Opus (off by default).
  - Exclude Input, GUI, Particle FX, Tilemaps, Live Update, Image, Types and Basis Transcoder.
  - Graphics backend per platform (HTML5: WebGL / WebGPU / both).
  - Use full text layout system, Use Rich Text.
  - HTML5 build options: `minSafariVersion`/`minFirefoxVersion`/`minChromeVersion`, `initialMemory` (default 33554432, overridden at run time by `html5.heap_size`) and `stackSize` (default 5242880).

  Source: [App manifest manual](https://defold.com/manuals/app-manifest/).
- **How a switch maps to libraries.** The editor maps each switch to exclude-libs and add-libs toggles in `editor/src/clj/editor/app_manifest.clj` ([source](https://github.com/defold/defold/blob/2914ec826e4955ae0000935cdf3ea14bd363aa90/editor/src/clj/editor/app_manifest.clj#L375-L565)):

  | Switch | Excluded libraries | Added stub |
  | --- | --- | --- |
  | Sound | `sound`, `tremolo` | `sound_null` |
  | GUI | `gamesys_gui`, `gui` | `gui_null` |
  | Particle FX | `gamesys_particle`, `particle` | `particle_null` |
  | Input | `hid` | `hid_null` |
  | Live Update | `liveupdate` | `liveupdate_null` |
  | Basis transcoder | `graphics_transcoder_basisu`, `basis_transcoder` | `graphics_transcoder_null` |
  | Rich text | `font_richtext` | `font_richtext_null` |
  | Image | `image` | `image_null` |
  | Physics (all) | — | `physics_null` |
  | Rig/model None | `gamesys_model`, `gamesys_rig`, `rig` (plus `excludeSymbols ScriptModelExt`) | `gamesys_rig_null`, `gamesys_model_null`, `rig_null` |

- **Example manifest of the playable tool** (`no_basis_liveupdate_physics.appmanifest`), `wasm-web` context:
  - `excludeLibs: [graphics_transcoder_basisu, basis_transcoder, profilerext, record, vpx, liveupdate, physics, LinearMath, BulletDynamics, BulletCollision, Box2D, script_box2d, gamesys_model, gamesys_rig, rig, image]`
  - `excludeSymbols: [ProfilerExt, ScriptBox2DExt, ScriptModelExt, ScriptImageExt]`
  - `libs: [graphics_transcoder_null, physics_null, profilerext_null, record_null, liveupdate_null, gamesys_rig_null, gamesys_model_null, rig_null, image_null]`

  Source: [defold-playable-ads example/no_basis_liveupdate_physics.appmanifest @dc2ed7c](https://github.com/indiesoftby/defold-playable-ads/blob/dc2ed7c0d4eef45f5ed4318f60d59be642b2721e/example/no_basis_liveupdate_physics.appmanifest). Some names (`Box2D`, `script_box2d`) are older than the current `box2d_defold` / `script_box2d_defold` in `build_input.yml`. Bob's `ExtenderUtil` contains an `AppManifestMigration` step for legacy library names ([ExtenderUtil.java](https://github.com/defold/defold/blob/2914ec826e4955ae0000935cdf3ea14bd363aa90/com.dynamo.cr/com.dynamo.cr.bob/src/com/dynamo/bob/pipeline/ExtenderUtil.java#L618-L660)).
- **Symbol mechanism.** Extensions register themselves through exported symbols. The build generates `extern "C" void dmExportedSymbols()`, which references every listed symbol ([scripts/cmake/exported_symbols.in.cpp](https://github.com/defold/defold/blob/2914ec826e4955ae0000935cdf3ea14bd363aa90/scripts/cmake/exported_symbols.in.cpp)). `_dmExportedSymbols` is in the web `EXPORTED_FUNCTIONS` list ([build_input.yml](https://github.com/defold/defold/blob/2914ec826e4955ae0000935cdf3ea14bd363aa90/share/extender/build_input.yml#L520-L560)). `excludeSymbols` removes entries from that list.
- **What triggers a custom engine build.** `ExtenderUtil.hasNativeExtensions()` returns true as soon as `game.project` sets `native_extension.app_manifest`, even without any native extension in the project ([ExtenderUtil.java L821–L833](https://github.com/defold/defold/blob/2914ec826e4955ae0000935cdf3ea14bd363aa90/com.dynamo.cr/com.dynamo.cr.bob/src/com/dynamo/bob/pipeline/ExtenderUtil.java#L821-L833)).
- **Build server.** "Defold provides the cloud build server free of charge, without any usage restrictions. The server is hosted in Europe". It is selected with `--build-server` or in editor preferences. "Any team member that builds and runs the project will get a project specific engine executable with all native extensions baked in" — [Extensions manual](https://defold.com/manuals/extensions/).
  - Self-hosting: Docker images from a public Google Artifact Registry plus `extender.jar` from [defold/extender releases](https://github.com/defold/extender/releases) — [Extender local setup manual](https://defold.com/manuals/extender-local-setup/).
  - The server's link command for the web is a templated `em++ … -Wl,--start-group {{libs}} {{engineLibs}} -Wl,--end-group --js-library …` over prebuilt `lib*.a` in `{{dynamo_home}}/lib/wasm-web` — [build_input.yml `wasm-web.linkCmd`](https://github.com/defold/defold/blob/2914ec826e4955ae0000935cdf3ea14bd363aa90/share/extender/build_input.yml#L561-L578).
- **Build time.** "99% of playable ad build time … takes a build on the remote Defold extender server. And usually it is about 1-2 minutes!" — [defold-playable-ads README](https://github.com/indiesoftby/defold-playable-ads) [secondary].
- **Per-exclusion savings**, measured by Defold in PR #12872 (1.13.2) on the uncompressed release wasm. Baseline 2,397,812 B; each option enabled alone — [Defold 1.13.2 release notes (2026-09-29)](https://forum.defold.com/t/defold-1-13-2-has-been-released/83276):

  | Option | Saved (raw wasm) |
  | --- | ---: |
  | Without GUI | 173,919 B (7.25 %) |
  | Without Particle FX | 72,160 B (3.0 %) |
  | Without Tilemaps | 16,933 B (0.7 %) |

- **Other savings data points**:
  - Live Update removal (1.2.186 beta, 2021) "cuts down the resulting file by the extra 50KB". The tool author measured this on the zstd+base64 asm.js HTML — [Defold forum: Defold for Playable Ads, post #31 (2021-08-09)](https://forum.defold.com/t/defold-for-playable-ads/68689) [secondary].
  - Playable manifest on 1.13.0 (local measurement, §1): −703,861 B raw (−29.7 %) and −228,762 B zstd (−28.3 %) against the stock wasm. This removes Bullet, Box2D, Basis, Live Update, model/rig and image together.
  - Empty 1.4.6 project: 975 KB → 808 KB gzip download with a manifest (2023) — [HTML5 bundle size](https://forum.defold.com/t/html5-bundle-size/73431) [secondary].
- **Size guidance in Defold's own manual.**
  - Remove physics if unused ("strongly advised"), GUI, particles, tilemaps, rich text, LiveUpdate and image.
  - BasisU: "compare the build size without BasisU … and without texture compression versus a build with BasisU and compressed textures. For games with limited textures, it might be more beneficial to reduce the binary size and skip texture compression".
  - The manual states "Playable ads are usually limited to between 2 and 5 MB".

  Source: [Optimizing game size (doc repo, last change 2026-11-09)](https://defold.com/manuals/optimization-size/). 1.14.0 updated Basis Universal to 2.50, and "Defold continues to use UASTC textures to keep engine size down" — [1.14.0 release notes](https://forum.defold.com/t/defold-1-14-0-has-been-released/83348).

### Inferences
- The stripping is **link-time only**:
  - All engine subsystems are prebuilt once per platform as static libraries, each with a `_null` twin exposing the same API.
  - A custom engine is a relink with a different library list, plus compiling any native extension sources. No engine source is recompiled.
  - That is why a "custom engine" takes 1–2 minutes and why Defold can offer it as a free shared cloud service.
- Exclusions save roughly additive amounts: GUI 174 KB, ParticleFX 72 KB, Tilemaps 17 KB. The 1.13.0 playable manifest removed about 0.7 MB raw. A fully stripped engine with GUI, ParticleFX, Tilemaps, Rich Text and sound also removed (where the game allows) plausibly lands around or below 1.5 MB raw on 1.14.x. This is not measured.

### Gaps
- I found no official per-switch numbers for physics (Box2D / Bullet), Basis, sound or Rich Text on wasm. The 1.13.2 table covers only GUI, ParticleFX and Tilemaps. A table could be produced by building the example with each switch against `build.defold.com`. I did not, to avoid sending builds to the external service without need.
- I found no published "absolute minimum" Defold wasm (every switch off).

## 3. Playable-ad packaging (single HTML, compression, network adapters)

### Takeaway
Defold itself has no official playable-ad exporter. The community tool `indiesoftby/defold-playable-ads` fills the gap:
- **Build.** A Gulp script builds a normal `wasm-web` bundle with bob.
- **Compression.** It zstd-19-compresses each output file (engine wasm, JS glue and every `archive/` file) separately, base64-encodes them into a JSON object `ARCHIVEJS_DATA`, and inlines that object into one HTML.
- **Runtime decoding.** It patches Defold's loader so that every request goes to an in-page fake `XMLHttpRequest`. That fake decodes base64 in chunks and decompresses with the pure-JS `fzstd`, so the wasm is instantiated from bytes.
- **Networks.** A single HTML serves all networks: a runtime adapter (`window.Playable`) detects FbPlayableAd → Mintegral → MRAID → Google ExitApi. Only AdMob needs a separate `--admob` build.
- **Size.** The demo is 1.12 MB as one file (0.84 MB gzip). The engine accounts for 0.85 MB of base64 and the game for 0.22 MB.

### Cited Findings
- **Tool status.**
  - Latest release 1.5.4 (2025-11-01), "Tested ✅" against Defold 1.11.1.
  - Last push 2026-08-05; its CI builds the example with the then-current stable bob and deploys the demo.
  - Supported: Google Ads, Facebook, Mintegral, Unity Ads, AppLovin. "Moloco, Snapchat, etc: Not tested".
  - Recommended testers: FB Playable Preview, Google H5 Validator, Playturbo, AppLovin preview, an MRAID validator.

  Sources: [README @dc2ed7c](https://github.com/indiesoftby/defold-playable-ads), [releases](https://github.com/indiesoftby/defold-playable-ads/releases), [workflow main.yml](https://github.com/indiesoftby/defold-playable-ads/blob/dc2ed7c0d4eef45f5ed4318f60d59be642b2721e/.github/workflows/main.yml).
- **Pipeline** (`exports.default`): `parseProjectConfig → zstdIsInstalled → javaIsInstalled → fetchBobVersionInfo (d.defold.com/stable/info.json) → downloadBobJar → checkBobJar → buildGame → copyFzstd → copyPackshot → bundleArchiveJs → bundlePlayableAds` — [gulpfile.js L566–L578](https://github.com/indiesoftby/defold-playable-ads/blob/dc2ed7c0d4eef45f5ed4318f60d59be642b2721e/playable_ad/gulpfile.js#L566-L578).
- **bob call.** `java -jar bob.jar --email foo@bar.com --auth 12345 --build-server https://build.defold.com --variant release --texture-compression true --settings playable_ad/build.settings [--settings user.ini] --bundle-output … --platform wasm-web --architectures wasm-web --archive distclean resolve build bundle` — [gulpfile.js L264–L300](https://github.com/indiesoftby/defold-playable-ads/blob/dc2ed7c0d4eef45f5ed4318f60d59be642b2721e/playable_ad/gulpfile.js#L264-L300). `build.settings` sets `[playable_ad] enabled = 1`, which turns on the playable sections of the HTML template.
- **Compression.**
  - The tool shells out to the system `zstd -c -19 -`. Each file in `<title>_wasm.js`, `<title>.wasm` and `archive/*` is stored as `ARCHIVEJS_DATA[path] = [rawLength, base64(zstd)]` — [gulpfile.js L111–L134, L302–L379](https://github.com/indiesoftby/defold-playable-ads/blob/dc2ed7c0d4eef45f5ed4318f60d59be642b2721e/playable_ad/gulpfile.js#L302-L379).
  - Defold's `dmloader.js` is minified with UglifyJS and inlined as `eval(Zstd_DecStr('<base64 zstd>'))`.
  - The tool prints the result size and warns above 2 MiB (`printSize(" resulting", 2 * 1024 * 1024)`) — [gulpfile.js L456–L564](https://github.com/indiesoftby/defold-playable-ads/blob/dc2ed7c0d4eef45f5ed4318f60d59be642b2721e/playable_ad/gulpfile.js#L456-L564).
- **Compression history** [secondary]:
  - 2021: asm.js, zopfli, then zstd. The switch to zstd and fzstd "saves 300KB". The engine without a custom manifest went from 1,627,392 B to 1,305,207 B as zstd+base64. Decompression became asynchronous, so it "doesn't hang the browser anymore" — [forum post #33 (2021-08-24)](https://forum.defold.com/t/defold-for-playable-ads/68689).
  - Tool 1.3.0 (2023) made wasm the default architecture — [post #38 (2023-12-19)](https://forum.defold.com/t/defold-for-playable-ads/68689).
- **Loader patching.** `modifyAndMinifyJs` rewrites `dmloader.js` in two ways ([gulpfile.js L76–L109](https://github.com/indiesoftby/defold-playable-ads/blob/dc2ed7c0d4eef45f5ed4318f60d59be642b2721e/playable_ad/gulpfile.js#L76-L109)):
  - It replaces every `XMLHttpRequest` with `ArchiveJsRequest`.
  - It replaces script loading `script.src = src` with `script.text = response`, needed "since Defold 1.10.2". The tool throws if the regex no longer matches, so loader changes in Defold break the build loudly.

  In 1.13.2+, Defold's `FileLoader` still "wraps XMLHttpRequest" (`requestOnce` → `new XMLHttpRequest()`). Real `fetch()` is used only for optional wasm streaming. Without streaming, the loader calls `WebAssembly.instantiate(result.response, importObject)` on the downloaded bytes — [dmloader.js (dev) L267–L300, L500–L568](https://github.com/defold/defold/blob/2914ec826e4955ae0000935cdf3ea14bd363aa90/com.dynamo.cr/com.dynamo.cr.bob/src/com/dynamo/bob/bundle/resources/web/dmloader.js#L267-L300).
- **In-page runtime** (template `playable_ad/manifests/web/engine_template.html`, merged into Defold's template through the extension manifest mechanism):
  - A hand-written base64 decoder `B64_U8(str, from, len)` decodes slices, so the whole string is never decoded at once.
  - `ArchiveJsRequest.send()` streams `fzstd.Decompress`. It feeds 33,333-byte base64 slices through `setTimeout` (non-blocking), fires `onprogress`, and returns a `Uint8Array` or text (via a `Blob` + `FileReader`).
  - `EngineLoader.stream_wasm = false` forces the XHR path.
  - Source: [engine_template.html L1–L249](https://github.com/indiesoftby/defold-playable-ads/blob/dc2ed7c0d4eef45f5ed4318f60d59be642b2721e/playable_ad/manifests/web/engine_template.html).
- **Inline images.** CSS `url(*.png|*.jpg)` references (splash, optional packshot `logo.png`/`playnow.png`) are replaced by data URIs. A `file://` warning is disabled. The viewport meta is forced to `width=device-width,user-scalable=no,…` — [gulpfile.js L381–L454](https://github.com/indiesoftby/defold-playable-ads/blob/dc2ed7c0d4eef45f5ed4318f60d59be642b2721e/playable_ad/gulpfile.js#L381-L454).
- **Network adapter.** `window.Playable` provides `gameLoaded()`, `gameEnd()`, `install()` and `retry()`. Lua calls it through `html5.run("doClick()")`.
  - `install()` tries `FbPlayableAd.onCTAClick()`, then Mintegral `window.install()`, then MRAID `mraid.open(url)` with the iOS or Android URL picked by user agent, then `ExitApi.exit()`, then `window.open(url)` as a fallback.
  - MRAID is detected either as `window.mraid` or as a global lexical binding (some validators).
  - The game's `Module._callMain` is wrapped to wait for `mraid` `ready` and `viewableChange` before starting.
  - Mintegral's `gameReady()` is fired once after the archive has loaded.
  - "Ad platform verification requires each supported exit API to be exposed directly in the JS code".

  Sources: [engine_template.html L251–L419](https://github.com/indiesoftby/defold-playable-ads/blob/dc2ed7c0d4eef45f5ed4318f60d59be642b2721e/playable_ad/manifests/web/engine_template.html#L251-L419), [README](https://github.com/indiesoftby/defold-playable-ads).
- **Store URLs and the AdMob variant.**
  - Store URLs come from `game.project` `[playable_ad] app_store_url` and `google_play_url` and are injected as `window.PlayableData`. The defaults point to AppLovin's preview apps.
  - The template always contains `<script src="https://tpc.googlesyndication.com/pagead/gadgets/html5/api/exitapi.js">`. The build fails if the tag is missing, and it strips the tag unless `--admob` is given.

  Sources: [ext.properties](https://github.com/indiesoftby/defold-playable-ads/blob/dc2ed7c0d4eef45f5ed4318f60d59be642b2721e/playable_ad/ext.properties), [gulpfile.js L392–L410](https://github.com/indiesoftby/defold-playable-ads/blob/dc2ed7c0d4eef45f5ed4318f60d59be642b2721e/playable_ad/gulpfile.js#L392-L410).
- **Native MRAID bridge.** The `playable_ad` native extension exposes a Lua module `mraid` with `set_listener(cb)` (`EVENT_VIEWABLE_CHANGE`) and `is_viewable()`. It is implemented as C++ plus an Emscripten `--js-library` (`library_mraid.js`, calling `mraid.isViewable()` and invoking the callback through `makeDynCall('vi', …)`) — [src/ext.cpp](https://github.com/indiesoftby/defold-playable-ads/blob/dc2ed7c0d4eef45f5ed4318f60d59be642b2721e/playable_ad/src/ext.cpp), [lib/web/library_mraid.js](https://github.com/indiesoftby/defold-playable-ads/blob/dc2ed7c0d4eef45f5ed4318f60d59be642b2721e/playable_ad/lib/web/library_mraid.js). Because the project has a native extension, every playable build is a cloud engine build.
- **Two-file mode.** `--embed-archive-js=false` emits `<title>.html` + `<title>_archive.js` for ZIP-based networks. It was added in 2021 because Facebook's 2 MB HTML+JS limit applies even in ZIP form ("the whole game unzipped must be < 5MB AND the index + JS must be < 2MB") — [README](https://github.com/indiesoftby/defold-playable-ads), [forum post #27 (2021-07-09)](https://forum.defold.com/t/defold-for-playable-ads/68689) [secondary].
- **Demo composition** (local measurement of [the demo HTML](https://indiesoftby.github.io/defold-playable-ads/index.html), Defold 1.13.0, deployed 2026-08-05):
  - Total 1,115,070 B (gzip -9: 839,187 B).
  - Payloads `[raw → zstd → base64]`:

    | File | raw | zstd | base64 |
    | --- | ---: | ---: | ---: |
    | `.wasm` | 1,665,182 | 578,470 | 771,296 |
    | `_wasm.js` | 271,437 | 57,239 | 76,320 |
    | `game0.arcd` (resource data: an 88 KB OGG music track, a 40 KB logo PNG, a font, GUI) | 176,306 | 163,893 | 218,524 |
    | `game0.arci`, `.dmanifest`, `.projectc`, `archive_files.json` | 8,705 together | — | 5,440 together |

  - The remaining ~43 KB holds the zstd-compressed `dmloader.js`, `fzstd`, the template, CSS and the splash PNG.
  - The game's `game.project` sets `heap_size = 64`, `scale_mode = stretch`, `high_dpi = 1`, 640×1136, and `engine_arguments = --verify-graphics-calls=false` — [game.project](https://github.com/indiesoftby/defold-playable-ads/blob/dc2ed7c0d4eef45f5ed4318f60d59be642b2721e/game.project).
- **Shipped playables.** The only public report besides the 2019 Facebook playable already in `playable_ads.md`: a 2025 user cut a game to a "zip to around 3.8mb" and then hit a Spine extension version mismatch with the tool — [forum post #52 (2025-07-18)](https://forum.defold.com/t/defold-for-playable-ads/68689) [secondary]. In January 2024 the tool author wrote: "We personally have never run any ad campaigns with playable ads made with Defold, so we need your feedback" — [post #48](https://forum.defold.com/t/defold-for-playable-ads/68689) [secondary].
- **Older timing.** For the 2021 asm.js version, the console showed "decode 500 ms, onload() 500 ms" for the engine JS — [post #2 (2021-06-26)](https://forum.defold.com/t/defold-for-playable-ads/68689) [secondary].

### Inferences
- The base64 tax is fully visible in the demo: 1,071,580 B of base64 for 803,734 B of zstd payload (+33 %). gzip of the whole HTML recovers only part of it (839 KB). The tool never uses `DecompressionStream`; it pays for a JS zstd decoder (`fzstd`, a few KB) to gain about 115 KB on the engine over gzip -9 (578 KB vs 693 KB).
- Per-file compression makes zstd almost useless on `game0.arcd` (−7 %). The archive holds already compressed OGG and PNG data, which matches the lossless-WebP observation for Lichtpost. Asset budgets, not engine compression, dominate once the engine is about 0.6 MB.
- The adapter design is network-agnostic: one artefact, with the API chosen at run time by injected globals. This avoids N per-network builds. The exception is Google's literal `exitapi.js` `<script>` requirement, which conflicts with "no external requests" elsewhere, so the tool builds it as a separate variant.
- The tool depends on regex surgery on Defold's `dmloader.js` (`XMLHttpRequest` rename, `script.src` → `script.text`). Its README (tested 1.11.1) and CI (latest stable) disagree on the tested version. It is therefore fragile across Defold releases: post #55 records one such break and fix in 2025. The gulpfile also passes `--texture-compression true` as two arguments, while bob's current manual says the switch takes no value. Whether this still works on 1.14.x is untested.

### Gaps
- The tool publishes no startup time measurements for wasm base64 decode, zstd decode and compile on low-end Android.
- Apart from the 2019 Facebook ad, I found no public list or size data of Defold playables running in production campaigns.
- I found no Defold-official playable-ads manual page. The size manual only mentions the 2–5 MB limits, and Defold's asset portal lists the community tool.

## 4. Build tooling: bob.jar options, template customisation, and a Bazel mapping

### Takeaway
Defold builds are driven by `bob.jar`, Defold's headless Java build tool, with `--platform wasm-web --architectures wasm-web[,wasm_pthread-web] --variant release|debug|headless [--strip-executable] --archive … resolve build bundle`. Native code goes to a build server given by `--build-server`. The HTML page is a Mustache template whose tokens come from `game.project` sections. Extensions contribute template fragments, as the playable tool does. Customisation happens in `game.project` (`[html5]` keys), a custom template or CSS, and `CUSTOM_PARAMETERS` in an `engine-setup` block. Size is reported through `--build-report-json` and `--build-report-html`.

### Cited Findings
- **Relevant Bob options** — [Bob manual](https://defold.com/manuals/bob/):
  - `-ar/--architectures`; `--variant` (debug, release, headless); `--strip-executable` ("Strip the dmengine of debug symbols"); `--build-server` and `--build-server-header`.
  - `-tc/--texture-compression`, "a switch with no value"; the legacy `--texture-compression=false` "is ignored and produces a warning".
  - `--exclude-archive`; `--use-uncompressed-lua-source`; `--use-lua-bytecode-delta`; `--bundle-format`; `-brjson/--build-report-json`, `-brhtml/--build-report-html`; `.defignore` replaces `--exclude-build-folder`.
  - `--variant` together with `--strip-executable` replaces the old `--debug`.
- **Template tokens.** The HTML is rendered with Mustache, and "Any *game.project* can be a token" (`{{section.field}}`). Custom tokens include `exe-name`, `DEFOLD_HAS_WASM_ENGINE`, `DEFOLD_HAS_WASM_PTHREAD_ENGINE`, `DEFOLD_HEAP_SIZE`, `DEFOLD_ENGINE_ARGUMENTS`, `DEFOLD_CUSTOM_CSS_INLINE`, `DEFOLD_ARCHIVE_LOCATION_PREFIX/SUFFIX`, scale-mode booleans and `build-timestamp` — [HTML5 manual](https://defold.com/manuals/html5/).
- **Loader parameters.** `CUSTOM_PARAMETERS` covers `archive_location_filter`, `engine_arguments`, `custom_heap_size`, `retry_time`/`retry_count`, `start_success`, `update_progress` and more, set in an `engine-setup` script between `dmloader.js` and `engine-start` — [HTML5 manual](https://defold.com/manuals/html5/).
- **Download verification.** The loader verifies the size and SHA-1 of engine and archive downloads (`html5.verify_downloaded_file_size`) and uses `crypto.subtle.digest("SHA-1")` — [HTML5 manual](https://defold.com/manuals/html5/), [dmloader.js L441, L452–L476](https://github.com/defold/defold/blob/2914ec826e4955ae0000935cdf3ea14bd363aa90/com.dynamo.cr/com.dynamo.cr.bob/src/com/dynamo/bob/bundle/resources/web/dmloader.js#L441).
- **Template merging.** Extensions put template fragments under `manifests/web/engine_template.html`, and the build server merges them with `manifestmergetool.jar` (`manifestMergeCmd … --platform {{platform}} --main … --lib …`) — [build_input.yml `web`](https://github.com/defold/defold/blob/2914ec826e4955ae0000935cdf3ea14bd363aa90/share/extender/build_input.yml#L520-L560). The playable tool uses this through its `playable_ad` extension, gated by `{{#playable_ad.enabled}}` — [engine_template.html](https://github.com/indiesoftby/defold-playable-ads/blob/dc2ed7c0d4eef45f5ed4318f60d59be642b2721e/playable_ad/manifests/web/engine_template.html).
- **Build server for CI.** It can be self-hosted. Bob's `--build-server <url>` "overrides the default for every release channel" — [Bob manual](https://defold.com/manuals/bob/), [Extender local setup](https://defold.com/manuals/extender-local-setup/).
- **Size reporting.** "Generate a build report when bundling" is the first step Defold recommends for size work. Bob also automatically keeps only assets reachable from the bootstrap collection — [Optimizing game size](https://defold.com/manuals/optimization-size/).

### Inferences
**Mapping to a Bazel action graph:**

| Defold step | Bazel equivalent |
| --- | --- |
| bob `build` (resources → archive) | the PCK export action |
| Extender relink (prebuilt libs + manifest → wasm) | an `emcc` link action over prebuilt per-module static archives, with stub archives chosen by a build setting |
| bob `bundle` + Mustache template | a template-expansion action |
| Gulp packer (per-file zstd → base64 JSON → inline into HTML → minify → size check) | a hermetic packer action (Python or Node tool) with a size-limit check |
| `--admob` variant | a per-network output via a build-setting transition |

All Defold steps are deterministic file transforms. They map 1:1 to Bazel actions. Only the Extender call is remote.

- Defold verifies the final size (warning at 2 MiB) only in the packer, not in the engine build. In Bazel this can become a failing test or validation action per network limit.

### Gaps
- The editor's own bundle dialog (as opposed to bob) for HTML5 is not covered here. It is not relevant for CI.
- I did not check the exact `--strip-executable` effect on wasm-web (name section removal vs no-op).

## 5. What transfers to Godot

### Takeaway
Three Defold ideas carry over to Godot:
1. **Link-time stubs instead of recompiles.** Prebuilt per-subsystem static libraries, each with a null twin, are selected by a manifest. A minimal engine is then a relink, not a rebuild.
2. **One self-extracting HTML with an in-page virtual file loader.** This is a packaging trick independent of the engine.
3. **A runtime-detected network adapter.** The CTA and lifecycle API is chosen from injected globals, so one artefact covers most networks.

The size gap does not transfer: Defold's 1.7 MB raw engine reflects a much smaller engine scope than Godot's.

### Cited Findings
- **Defold's stripping unit** is the static library plus the `excludeSymbols` registration entry, selected per platform in a YAML manifest. The editor exposes it as checkboxes — [app_manifest.clj](https://github.com/defold/defold/blob/2914ec826e4955ae0000935cdf3ea14bd363aa90/editor/src/clj/editor/app_manifest.clj), [App manifest manual](https://defold.com/manuals/app-manifest/).
- **Godot's comparable switches** (from `minimal_engine_size.md`): `modules_enabled_by_default=no`, `module_*_enabled`, `disable_3d`, `disable_physics_*`, `disable_navigation_*`, `disable_xr` and `disable_advanced_gui`, all SCons options that need recompilation. Class-level `build_profile` is not yet supported in rules_godot recipes. The fact cited here is that file, not a new source.
- **Per-function attribution.** Defold attributes wasm size per function through `--emit-symbol-map` + `bloaty` ([wasm_symbol_sizes.py](https://github.com/defold/defold/blob/2914ec826e4955ae0000935cdf3ea14bd363aa90/scripts/web/wasm_symbol_sizes.py)). This is the step that failed for Godot in `minimal_engine_size.md`: `--emit-symbol-map` tripped an emcc assertion there.
- **Packer core.** The packer is about 580 lines of Gulp/Node plus a 420-line HTML template — [gulpfile.js](https://github.com/indiesoftby/defold-playable-ads/blob/dc2ed7c0d4eef45f5ed4318f60d59be642b2721e/playable_ad/gulpfile.js), [engine_template.html](https://github.com/indiesoftby/defold-playable-ads/blob/dc2ed7c0d4eef45f5ed4318f60d59be642b2721e/playable_ad/manifests/web/engine_template.html). Its core is three things:
  - a request shim that replaces the loader's XHR;
  - a chunked base64 + streaming zstd decode;
  - `WebAssembly.instantiate(bytes)` instead of streaming compile.

### Inferences
- **Stripping in rules_godot.** Defold's approach maps onto Bazel if Godot's modules and `disable_*` areas are built as separate `cc_library` targets with stub alternatives:
  - A `string_flag` or `bool_flag` manifest would pick real or stub libraries.
  - Only the final `emcc` link (and the small generated module-registration unit, Godot's analogue of `dmExportedSymbols`) would re-run, and remote caching would share the per-module archives.
  - This is much more invasive for Godot than for Defold. Godot's `disable_*` switches are preprocessor defines spread across core and scene code, not library boundaries. Only the `modules/` boundary resembles Defold's units.
  - This is a design hypothesis to validate by experiment, per the project's idiom rule.
- **Packer for Godot.** Defold's packer design transfers almost directly to a Godot web export:
  - inline `godot.wasm`, `godot.js` and the `.pck` as compressed base64;
  - shim Godot's loader fetches (Godot's `engine.js` fetches the wasm and pck; the exact hook point, for example Emscripten's `instantiateWasm` or `wasmBinary` or a patched fetch, still needs checking in the Godot 4.7 sources);
  - instantiate from bytes.
  - Defold's choice of zstd plus a JS decoder over native `DecompressionStream` gzip is worth about 115 KB on Defold's engine. On Godot's 17.7 MB engine the gap between gzip (5.15 MB) and brotli or xz (3.5–3.6 MB) is about 1.5 MB, so a JS or wasm decoder pays off far more for Godot.
- **Adapter layer.** Defold's `window.Playable` adapter (gameLoaded / gameEnd / install / retry with injected-global detection, plus MRAID ready/viewable gating of `callMain`) is engine-agnostic JS. It could be reused nearly verbatim (MIT) as a template fragment around Godot's `Engine.startGame()`. The game would call it through `JavaScriptBridge`.
- **Budget for Godot.**
  - Defold: the stripped engine takes about 0.6 MB (zstd), or 0.85 MB as base64. Defold playables therefore have about 4 MB for assets under raw-HTML 5 MB caps, and about 1.1 MB under Meta's 2 MB single-HTML cap.
  - Godot: the L2 engine at about 3.5 MB (brotli or xz), about 4.7 MB as base64, leaves almost nothing under raw-HTML caps. It needs a ZIP-counted network, a two-file split like Defold's `--embed-archive-js=false`, or a further engine cut of several MB.
  - The Defold comparison suggests the cut must come from scope (class-level stripping), not from compiler flags: Defold itself does not even use `-Oz`.

### Gaps
- Whether Godot's module registration (`register_module_types`) can be generated per link, so that module libraries become swappable like Defold's `_null` libraries, was not examined.
- I made no measurement of Godot startup with an inline, JS-decompressed engine, and found no published Defold equivalent for wasm to compare against.
