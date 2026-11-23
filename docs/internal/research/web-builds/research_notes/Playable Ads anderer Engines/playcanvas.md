# PlayCanvas: how HTML5 playable ads are built

Researched 2026-11-23. Builds on `../Web Builds Entscheidungsgrundlagen/playable_ads.md` (network limits, base64 vs. compression, other engines) and `minimal_engine_size.md` (Godot L2 engine: 17.7 MB raw / 5.2 MB gzip / 3.6 MB brotli). Their findings are not repeated here.

Primary sources are the PlayCanvas engine repo, the `playcanvas-rest-api-tools` repo (source read at `main`, last commit 2024-08-15), the `playcanvas/developer-site` repo (docs source, last edited 2026-11-23), and npm. `[secondary]` marks forum posts and third-party pages. `[measured]` marks local measurements made on 2026-11-23 with Node 24 zlib (gzip -9, brotli q11) and `lz4js@0.2.0`, the library the tool uses. The bundles were built with esbuild 0.25 against `playcanvas@2.24.3` (released 2026-11-23). All work was done in the session scratchpad.

## 1. Runtime: engine size, tree shaking, custom builds, optional wasm modules

### Takeaway
The PlayCanvas engine is pure JavaScript, and it has grown considerably. The full minified UMD build was ~1.2 MB in 2021 (engine 1.39). In 2.24.3 it is 2.90 MB raw / 755 KB gzip / 584 KB brotli. The docs' "~1.2 MB" figure is therefore stale. Since 2.x the engine is published as side-effect-free ES modules with an official tree-shaking guide (`AppBase` + explicit component systems and resource handlers). A tree-shaken WebGL2 playable-style app measures 1.54–1.62 MB raw / ~405–418 KB gzip / ~312–324 KB brotli. That is still roughly 11–12× smaller compressed than our stripped Godot engine. Physics (Ammo), Basis and Draco are separate wasm modules of 0.07–0.29 MB compressed each. PlayCanvas's own single-file playable path does not support them at all.

### Cited Findings
- **Engine sizes by version** `[measured]` (min UMD build from npm via jsDelivr):

  | Version | raw | gzip -9 | brotli 11 | lz4js | base64(lz4) |
  | --- | --- | --- | --- | --- | --- |
  | 1.39.4 (in the official Cube Jump example) | 1,178,989 | 290,978 | 238,476 | 475,869 | 634,492 |
| 1.54.0 | 1,327,407 | 332,355 | 268,725 | 540,592 | 720,792 |
  | 1.63.0 | 1,475,564 | 372,459 | 299,996 | – | – |
  | 2.0.0 | 1,682,064 | 428,571 | 342,047 | – | – |
  | 2.24.3 (`playcanvas.min.js`) | 2,898,446 | 754,615 | 584,201 | 1,203,076 | 1,604,104 |

  For 2.24.3, base64 of the raw file would be 3.86 MB and base64 of the gzip 1.01 MB. The `.min.mjs` ESM single-file build is 2,895,086 B raw. npm lists 2.24.3 as published 2026-11-23, with releases roughly weekly (2.24.0 on 2026-11-09) — [npm playcanvas](https://www.npmjs.com/package/playcanvas).
- The official docs still say "The Engine alone takes about 1.2 MB of a Facebook ad's budget" (page rewritten 2026-11-21) — [Playable Ads index](https://developer.playcanvas.com/user-manual/editor/publishing/playable-ads/), source [developer-site](https://github.com/playcanvas/developer-site/blob/main/docs/user-manual/editor/publishing/playable-ads/index.md). That number matches 1.39 (2021), not current 2.x. This conflicts with the measurements above.
- **Tree shaking (official, page added 2026-11-12):** "The PlayCanvas Engine is published on npm as ES modules, one module per source file, and its `package.json` declares `"sideEffects": false`." `AppBase` "registers only the component systems and resource handlers that you list in an `AppOptions` object", and "Each class you don't list is left out". The page also says: "The single-file builds in `playcanvas/build/` are meant for use without a build tool". Passing the whole namespace (`setup(pc)`) "makes some build tools, such as esbuild, keep the entire engine" — [Bundle Size and Tree Shaking](https://developer.playcanvas.com/user-manual/engine/bundle-size/), source [bundle-size.md](https://github.com/playcanvas/developer-site/blob/main/docs/user-manual/engine/bundle-size.md).
- The engine CI guards tree-shakability. One test bundles `import { Vec3 }` and asserts < 10 KB. Another asserts that a WebGL feature module "does not retain the shader chunks of the other device" (GLSL vs WGSL) — [test/bundles/treeshake.test.mjs](https://github.com/playcanvas/engine/blob/main/test/bundles/treeshake.test.mjs). `utils/build-size.mjs` tracks raw/gzip/brotli of the min bundles — [engine repo](https://github.com/playcanvas/engine/blob/main/utils/build-size.mjs). The build is now `node build.mjs` on esbuild (`build:min:umd`, `build:min:esm`, `build:treemap`), no longer Rollup — [engine package.json](https://github.com/playcanvas/engine/blob/main/package.json).
- **Tree-shaken bundle sizes** `[measured]` (esbuild `--bundle --minify --format=esm --target=es2022`, `playcanvas@2.24.3`):

  | App | raw | gzip | brotli |
  | --- | --- | --- | --- |
  | `import * as pc` (everything) | 2,950,972 | 780,736 | 603,864 |
  | Minimal 3D (render, camera, light, script; texture/container/script handlers; `createGraphicsDevice` WebGL2) | 1,251,976 | 332,564 | 256,076 |
  | Same, `new WebglGraphicsDevice()` directly | 1,173,114 | 314,139 | 241,686 |
  | "Playable" set (+ screen, element, button, sound, audiolistener, anim, particles, sprite; font/audio/anim/sprite/scene/material/render/json handlers; `WebglGraphicsDevice`) | 1,543,579 | 403,161 | 311,886 |
  | Same with `createGraphicsDevice` | 1,617,196 | 418,278 | 324,213 |

  Composition of the minimal bundle: `scene/shader-lib` 426 KB, `platform/graphics` 276 KB. Even in the WebGL-only bundles, ~210–240 KB of **WGSL** shader chunks stay in, next to ~190–215 KB of GLSL. A WebGL-only playable therefore still carries WebGPU shader source. The CI test above only covers the feature modules, not the core chunk set. lz4js of the "playable" bundle: 644,062 B, so 858,752 B as base64.
- An Editor project cannot use tree shaking directly. Editor builds load the full engine, and the one-page tool inlines `playcanvas-stable.min.js` as is (see §2). From 2.24.0 Editor custom-engine builds come only from npm ("engine builds are no longer uploaded to `code.playcanvas.com`"). Projects with ESM scripts need the `.mjs` build — [Custom engine](https://github.com/playcanvas/developer-site/blob/main/docs/user-manual/editor/interface/launch-page/custom-engine.md).
- Pre-ESM custom builds (2022, engine 1.54): a user removed "animations, a large part of the UI, legacy components, collision, sprites and some others" and got "0.9-1 MB" raw, "400-500kb" after LZ4. Staff noted that the full engine was "1.2-1.3MB" raw, "713KB" LZ4 and "338KB" gzip. Our 1.54.0 measurement (base64(lz4) 720,792 B, gzip 332,355 B) suggests the forum's "LZ4" figure is the base64-encoded lz4 output as the tool emits it. Staff also said and that the savings may be "10s of KB after gzip" — [forum: Safe cutting of modules](https://forum.playcanvas.com/t/safe-cutting-of-modules/26730) [secondary].
- **Optional wasm modules** `[measured]` (files from `engine/examples/assets/wasm`, `main`):

  | Module | file | raw | gzip | brotli |
  | --- | --- | --- | --- | --- |
  | Ammo (physics) | `ammo.wasm.wasm` + glue `ammo.wasm.js` | 750,028 + 453,324 | 291,705 + 53,124 | 218,927 + 39,535 |
  | Ammo asm.js fallback | `ammo.js` | 2,010,408 | 451,939 | 325,214 |
  | Basis transcoder | `basis.wasm.wasm` + glue | 611,602 + 60,106 | 290,460 + 15,629 | 214,590 + 14,098 |
  | Draco decoder | `draco.wasm.wasm` + glue | 285,747 + 58,763 | 88,507 + 11,823 | 66,140 + 10,115 |

  Docs: physics "incurs an additional download cost of 379KB" — [Optimizing Load Time](https://developer.playcanvas.com/user-manual/optimization/load-time/). "The Basis WASM module will add 253KB of extra gzipped data" — [Texture Compression](https://developer.playcanvas.com/user-manual/optimization/texture-compression/). Both doc figures are older than our measurements. The physics integration lives in `src/framework/physics/ammo/`. Meshopt decoding (`EXT_meshopt_compression`) is supported via a separately loaded decoder module — [engine src](https://github.com/playcanvas/engine/tree/main/src/framework/parsers).
- How the Basis module loads: the glue is fetched and wrapped in a `Blob` for a Web Worker (`URL.createObjectURL(getWorkerBlob(...))`). The wasm is fetched with `fetch(config.wasmUrl)` + `WebAssembly.compileStreaming`, and falls back to `http.get(config.fallbackUrl)` — [src/framework/handlers/basis.js](https://github.com/playcanvas/engine/blob/main/src/framework/handlers/basis.js).
- The one-page tool's own limits: "Modules are not supported (Basis and Ammo)", "Texture compression formats are not supported", "Asset Bundles are not supported". Suggested physics alternatives are cannon.js, p2.js, or the engine's bounding-volume overlap tests — [playcanvas-rest-api-tools README](https://github.com/playcanvas/playcanvas-rest-api-tools#converting-a-project-into-a-single-html-file).

### Inferences
- For playables, none of the wasm modules matter in the official path: they are excluded. A PlayCanvas playable is JS engine + PNG/JPG/MP3/GLB/JSON assets, so the "wasm in a single HTML" problem never arises for PlayCanvas.
- With the current full engine (2.24.3), the official route via Editor and `compress_engine` costs ~1.6 MB of Meta's 2 MB single-HTML budget, leaving ~0.4 MB. In 2021 it cost ~0.63 MB. In practice, current PlayCanvas playables for 2 MB networks either pin an older engine or need a tree-shaken engine-only build. The official tool supports neither directly.
- Removing WGSL chunks from a WebGL-only build is an obvious further ~200 KB raw saving that the engine does not do by itself today (inferred from the bundle composition, not tested).

### Gaps
- No lz4 or gzip+base64 measurement of an actual current Editor export. The Editor build's engine file name and whether it is still the UMD `min.js` for 2.x Classic projects were not verified.
- Runtime decode cost of lz4js in a browser on a low-end phone was not measured. The tool's README gives ~180 ms for engine 1.x on a Pixel 2XL / Galaxy S7. In Node, lz4js decoded 2.9 MB in ~6 ms (not representative of phones).
- No official "engine-only" or "playable" preset build exists. The tree-shaking guide is generic.

## 2. Official playable-ad tooling: how `one-page` builds the HTML

### Takeaway
The official tool is a ~500-line Node post-processor (`one-page.js`). It downloads a normal Editor build via the REST API, then rewrites it with regexes. Every asset URL in `config.json` becomes a base64 data URI. The scene JSON becomes a data URI, `config.json` is embedded as a JS object literal, and all `<script src>` are inlined. Four small engine monkey-patches make the runtime cope. The key one replaces `pc.Http.prototype.get` (the engine's single XHR choke point) with a base64 decoder, so there are no XHR or fetch calls at all. Optionally the engine is lz4-compressed + base64 and unpacked by a JS lz4 decoder into a `<script>` at startup. Network variants are boolean flags (MRAID, Snapchat CTA, extern files), not profiles. There is no size check, only an optional per-asset size report. Officially only Facebook and Snapchat are documented. The tool breaks on ESM-script projects and has had no commits since August 2024.

### Cited Findings
- **Scope and status:**
  - The docs say: "You make one from an Editor project with the PlayCanvas REST API Tools … It downloads a build of your project and repackages it in the format each ad network accepts. The tool works only with projects whose scripts are all Classic scripts. It edits files that only their builds contain, such as `__settings__.js` and `__start__.js`."
  - Networks table: Facebook ("A single HTML file of up to 2 MB, or a ZIP file of up to 5 MB, uncompressed") and Snapchat (MRAID 2.0, assets in a separate folder). The docs add: "Other ad networks may work, but the PlayCanvas team hasn't tested them."
  - Source: [Playable Ads](https://developer.playcanvas.com/user-manual/editor/publishing/playable-ads/), rewritten 2026-11-21 ([commits](https://github.com/playcanvas/developer-site/commits/main/docs/user-manual/editor/publishing/playable-ads)).
  - There is no Editor-integrated "playable export". The Editor path is REST API download + this CLI.
- Repo activity: last commit 2024-08-15 ("Asset Size Report #54"), 30 stars. Open issues include:
  - #50 "Incompatible with ESM Projects" (2024-03-19, by PlayCanvas engineer marklundin): "The rest api tools perform string in-place string manipulations on code and therefore depend on exported projects having a specific structure. Bundled ESM projects … will not have a stable build output … Ideally these transforms are part of the bundling process."
  - #8 "Support other Playable Ad networks", with Unity and AppLovin unchecked.
  - #37 zipson for JSON: "Flappy Bird saves only 15% on the config.json, 65% on scene json".
  - #34 refactor to a reusable bin.
  - Open PR #44 "Provide Compatibility for Google Playable Ads" (2022-11-11).
  - Source: [issues](https://github.com/playcanvas/playcanvas-rest-api-tools/issues), [commits](https://github.com/playcanvas/playcanvas-rest-api-tools/commits/main).
- **Pipeline steps**, in order, from [one-page.js](https://github.com/playcanvas/playcanvas-rest-api-tools/blob/main/one-page.js) at `main`:
  1. Force `scripts_concatenate = false` and download the build ZIP via the REST API, then unzip it.
  2. Add engine patches as `<script>` tags right after `playcanvas-stable.min.js` (patches listed below).
  3. Remove `manifest.json`. Replace the `PRELOAD_MODULES`/`loadModules(...)` block in `__start__.js` by regex with `configure();`. With MRAID, this becomes `window.mraid&&"ready"!==mraid.getState()?mraid.addEventListener("ready",configure):configure();`. Change CSS injection to a new `<style>` element "for better compatibility with ad networks".
  4. Inline `styles.css` into `<style>`.
  5. For every asset in `config.json` with a file, read the file. Pick the MIME prefix by extension: png, jpg, json (binary octet-stream for `model`/`animation`), css/html/txt/glsl as `text/plain`, mp4, and `octet-stream` as default (e.g. mp3, glb, ttf). Script assets with `loadingType === 0` are minified with terser (`ecma: '5'`, `keep_fnames`). Set `asset.file.url = mime + ';base64,' + b64` and clear `asset.file.hash`.
  6. Remove `__loading__.js`, the default loading screen.
  7. In `__settings__.js`, replace `SCENE_PATH` with a JSON data URI. Replace `CONFIG_FILENAME` with `JSON.parse("<escaped config JSON>")`, so the large config is **not** base64-encoded. Comment: "so we don't need to Base64 the config.json and take another ~30% hit".
  8. With MRAID, rewrite `reflow` so CSS, not the authored resolution, sizes the canvas, and force `fillMode = "NONE"`.
  9. Optionally add the Snapchat CTA library.
  10. Optionally compress the engine (details below).
  11. Replace every `<script src="X">` with `<script>contents</script>`, minifying anything not ending in `.min.js`. With `extern_files`, keep them as files instead, optionally under a folder and a CDN prefix, and zip the result.
- **Engine patches** ([engine-patches/](https://github.com/playcanvas/playcanvas-rest-api-tools/tree/main/engine-patches)):
  - `one-page-http-get.js` (always): wraps `pc.Http.prototype.get`. If `url` is an object, it calls back with that object immediately. This is how the inlined config object bypasses loading.
  - `one-page-no-xhr-request.js` (`patch_xhr_out`): replaces `pc.Http.prototype.get` entirely. It does `atob` on the part after the comma. If the URL is `data:application/json` or the response type is JSON, it calls `JSON.parse`. `text/plain` is passed as a string. Everything else becomes `Uint8Array` → `ArrayBuffer`, and `data:image/*` additionally becomes a `Blob`. It also sets `graphicsDevice.supportsImageBitmap = false` in `Application#configure`, because images otherwise fail without XHR (commit #47, 2024-02-15).
  - `one-page-inline-game-scripts.js` (`inline_game_scripts`): overrides `pc.ScriptHandler.prototype._loadScript` to `atob` the data URI and insert it as an inline `<script>` text (`async=false`) "for some platforms that block base64 encoded JS URLs".
  - `one-page-mraid-resize-canvas.js` (`mraid_support`): overrides `pc.Application.prototype.resizeCanvas` to use `mraid.getMaxSize()` instead of `window.innerWidth/innerHeight`. `mraid_support` also inserts `<script src="mraid.js">` before the engine.
- **Engine compression** (`compress_engine`): `lz4js.compress(engine)` → base64 → wrapper `!function(){var e=new Buffer("[b64]","base64"),n=Buffer.from(lz4.decompress(e)).toString(),r=document.createElement("script");r.async=!1,r.innerText=n,document.head.insertBefore(r,…)}()`. A bundled browserified `lz4.js` (42 KB raw) provides `Buffer` and `lz4`. The README says it "Compresses the engine file to save 500KB … This should only be used if you need the extra space as it adds extra initialisation time … Google Pixel 2XL: ~180ms, Samsung Galaxy S7: ~180ms". Since 2024-02 it uses `lz4js` instead of the native `node-lz4` (#48, which fixed node-gyp build failures #46) — [README](https://github.com/playcanvas/playcanvas-rest-api-tools/blob/main/README.md), [one-page.js L365–392](https://github.com/playcanvas/playcanvas-rest-api-tools/blob/main/one-page.js).
- **Network variants** come from flag combinations in `config.json` → `one_page`:
  - FB single HTML: `patch_xhr_out: true, inline_game_scripts: true, extern_files: false`.
  - FB ZIP: same with `extern_files: true`.
  - Snapchat: `patch_xhr_out: false, inline_game_scripts: true, extern_files {enabled, folder_name: <GUID>, external_url_prefix: "https://rtb-ads.shadow.snapads.com/html5"}, mraid_support: true, snapchat_cta: true`.
  - Generic MRAID interstitial (test config): `inline_game_scripts + mraid_support`.
  - Sources: [FB docs](https://developer.playcanvas.com/user-manual/editor/publishing/playable-ads/fb-playable-ads/), [Snapchat docs](https://developer.playcanvas.com/user-manual/editor/publishing/playable-ads/snapchat-playable-ads/), [tests/configs-one-page](https://github.com/playcanvas/playcanvas-rest-api-tools/tree/main/tests/configs-one-page).
  - Snapchat CTA library: `window.snapchatCta = function(){ if (window.mraid) mraid.open('{{ .ClickTrackingUrl }}'); }`. The network substitutes the template at serve time — [library-files/snapchat-cta.js](https://github.com/playcanvas/playcanvas-rest-api-tools/blob/main/library-files/snapchat-cta.js). (`playable_ads.md` already notes that this Snapchat flow is outdated relative to Snap's current spec.)
- **CTA handling is left to the project**: FB checklist "Have you added the function call `FbPlayableAd.onCTAClick()`…". The tool injects nothing for Meta, Google, Unity or AppLovin. A staff answer (2024-10-09) on Unity Ads rejections ("missing mraid.open()") said you "still need to add the calls needed like `mraid.open()` on the CTA" and "may need to fork and modify the tool" — [forum](https://forum.playcanvas.com/t/playcanvas-playables-ads-for-unity-ads/37887) [secondary]. For Google, a 2022 community fork added `<meta name="ad.orientation">`, `<meta name="ad.size" content="width=320,height=480">` (required by the validator then) and the ExitApi script, and switched the CTA to `ExitApi.exit()`. The PR was never merged — [forum: Playable Ad Space Shooter](https://forum.playcanvas.com/t/release-playable-ad-space-shooter/28238) [secondary], [PR #44](https://github.com/playcanvas/playcanvas-rest-api-tools/pull/44).
- **Testing and validation:** "Please ignore the warning about the source may contain an `XMLHttpRequest` as the code path has been removed by this tool" (FB tester). There is no size enforcement. `npm run one-page --size-report` prints the base64 size of each asset, sorted, and a total — [FB docs](https://developer.playcanvas.com/user-manual/editor/publishing/playable-ads/fb-playable-ads/), [README](https://github.com/playcanvas/playcanvas-rest-api-tools#asset-size-report).

### Inferences
- PlayCanvas does **not** intercept `fetch`/XHR globally. It patches the engine's own loader entry point, `Http.get`, and data URIs flow through the normal asset pipeline. That works because the engine has one JS-level loader that everything goes through. The engine's `Http` still uses `XMLHttpRequest` in 2.x ([src/platform/net/http.js](https://github.com/playcanvas/engine/blob/main/src/platform/net/http.js)), which is why the patch exists.
- Per-asset base64 inside `config.json` means no cross-asset compression and the full +33 % on every binary. The only "smart" savings are embedding config as a JSON literal and optional lz4 of the engine. lz4 was chosen for JS decode speed, not ratio. On engine 1.39.4, lz4 gives 476 KB against 291 KB for gzip -9 `[measured]`.
- The tool is effectively in maintenance. String-regex post-processing of build output (`__start__.js` regex, `<script src="playcanvas-stable.min.js">` marker) breaks with ESM projects and is fragile against Editor output changes. PlayCanvas's own engineer recommends doing the transforms "as part of the bundling process".

### Gaps
- Whether the tool still works unmodified against current Editor builds with engine 2.24 (Classic scripts) was not tested. No issue reports it broken, but there are also no commits since 2024-08.
- No official AppLovin, Unity, Google, TikTok or Mintegral variant exists. I found no maintained third-party PlayCanvas-specific packager. Generic tools such as `@smoud/playable-scripts` are engine-agnostic and have no documented PlayCanvas support.

## 3. Asset size minimisation

### Takeaway
For playables, PlayCanvas's guidance is basic. Keep images small and run them through TinyPNG, budget ~500 KB of pre-base64 assets for Meta single HTML (~3 MB for ZIP/Snapchat), and avoid physics. Basis/KTX2 and Draco, which PlayCanvas recommends for normal web builds, are explicitly unavailable in the one-page path, because their transcoders are wasm modules that the tool cannot inline.

### Cited Findings
- "The minified PlayCanvas Engine code is ~1.2MB uncompressed and … Base64 … adds ~30% to the size of each asset file. … for a single HTML format, this leaves ~500KB for assets before they are encoded … For the ZIP format, this would be about ~3MB". "Try to keep images as small as possible in dimensions and use tools like TinyPNG" — [FB Playable Ad](https://developer.playcanvas.com/user-manual/editor/publishing/playable-ads/fb-playable-ads/). For Snapchat the page says "soft limit of 5MB (uncompressed)" and "~3MB for assets before the Base64 encoding" — [Snapchat Playable Ad](https://developer.playcanvas.com/user-manual/editor/publishing/playable-ads/snapchat-playable-ads/).
- General load-time guidance: AVIF < WebP < JPG/PNG; downsample textures (2048 → 1024/512); strip unused vertex attributes (second UV set, all-white vertex colours); physics costs 379 KB — [Optimizing Load Time](https://developer.playcanvas.com/user-manual/optimization/load-time/).
- Basis is described as a "'super-compressed' texture format … transcoded to the natively supported hardware compression format at runtime (ASTC, DXT, ETC2, ETC, PVR, ATC)". Example: a 512² JPG at 202 KB → 46 KB Basis (ETC mode), with 6× less VRAM. Basis is "~50% smaller" than legacy formats. Limits: PVR needs square POT textures; max 4096² — [Texture Compression](https://developer.playcanvas.com/user-manual/optimization/texture-compression/).
- The one-page tool says: "Texture compression formats are not supported"; "Modules are not supported (Basis and Ammo)" — [README](https://github.com/playcanvas/playcanvas-rest-api-tools#converting-a-project-into-a-single-html-file). Draco is a wasm module of the same kind (see §1), so it is equally excluded. Draco is documented for normal builds — [tutorial](https://developer.playcanvas.com/tutorials/loading-draco-compressed-glbs/).
- The JSON scene format can be optimised (`optimize_scene_format` in the download job config) — [config.template.json](https://github.com/playcanvas/playcanvas-rest-api-tools/blob/main/config.template.json). Zipson was investigated for JSON (−15 % config, −65 % scene) but never shipped — [issue #37](https://github.com/playcanvas/playcanvas-rest-api-tools/issues/37).

### Inferences
- In PlayCanvas playables, assets go in as plain PNG/JPG/MP3 base64, so the network-visible size is roughly the sum of source file sizes × 1.33 plus the engine. Mesh and texture GPU compression trade download size for wasm transcoder size, which is a bad trade under 2 MB.

### Gaps
- No PlayCanvas-specific audio guidance for playables was found (bitrate, format, mono). The MIME table treats mp3/ogg as `application/octet-stream`.
- No official numeric budget split between engine, assets and audio beyond the ~500 KB / ~3 MB figures.

## 4. Typical sizes of shipped PlayCanvas playables; studios

### Takeaway
The only hard number is the official Cube Jump example. Its Facebook single-HTML output is 1.42 MB raw (397 KB zipped), of which ~1.2 MB is engine 1.39.4. The Snapchat and IronSource ZIP variants contain a 1.22 MB engine plus a 245 KB `__settings__.js` with the inlined assets. No named studio case studies or public size statistics for PlayCanvas playables were found. PlayCanvas's marketing page names none.

### Cited Findings
- Official example outputs in the docs repo `[measured]` from [developer-site static/downloads](https://github.com/playcanvas/developer-site/tree/main/static/downloads):
  - `fb-playable-ad-cube-jump-html.zip` (397,700 B) contains `Cube Jumper.html` at **1,416,378 B** raw, with engine version string 1.39.4.
  - `is-playable-ad-cube-jump.zip` (420,396 B): `assets/playcanvas-stable.min.js` 1,227,245 B + `assets/__settings__.js` 245,588 B.
  - `sc-playable-ad-cube-jump.zip` (417,869 B): `<GUID>/playcanvas-stable.min.js` 1,218,550 B + `__settings__.js` 244,751 B.
  - The project is [Cube Jump for FB](https://playcanvas.com/project/354998/overview/cube-jump-playable-ad-for-fb). An IronSource variant exists in the repo but is not documented as a supported network.
- The PlayCanvas advertising page claims "higher LTV players, better conversion rates" and "We're already working with the best game developers in the world and some of the biggest Ad networks", with no names or numbers — [playcanvas.com/industries/advertising](https://playcanvas.com/industries/advertising) (vendor marketing).
- Community releases: a 2022 "Playable Ad Space Shooter" adapted for Google and Facebook, with no file size given — [forum](https://forum.playcanvas.com/t/release-playable-ad-space-shooter/28238) [secondary]. Forum threads show recurring issues: black screens fixed by `patch_xhr_out: true`, rejections by IronSource and Unity over missing MRAID calls — [forum search results](https://forum.playcanvas.com/t/playcanvas-playables-ads-for-unity-ads/37887) [secondary].
- PlayCanvas belongs to Snap. The ESM issue links an internal `github.sc-corp.net/Snapchat/playcanvas-monorepo` PR — [issue #50](https://github.com/playcanvas/playcanvas-rest-api-tools/issues/50). This explains the first-class Snapchat path.

### Inferences
- A realistic PlayCanvas playable today is 1.3–2 MB single HTML on an old 1.x engine, or about 2–3 MB on the 2.x full engine. The latter no longer fits Meta's 2 MB single HTML without `compress_engine` (~1.6 MB engine). Ad shops using PlayCanvas likely pin older engines or maintain forks. This is an inference; no public confirmation was found.

### Gaps
- No named studio, agency or ad network publicly attributes production playables to PlayCanvas in sources found as of 2026-11. No statistics on PlayCanvas's share of playables.

## 5. What transfers to a Godot/Bazel pipeline

### Takeaway
The transferable pattern is to **patch the runtime's single loader entry point so that it resolves inlined data instead of URLs**, rather than to intercept the network. Pass large structured data (config JSON, Godot's PCK) as an in-memory object or `ArrayBuffer`, not as a data URI that has to be decoded again. Ship the engine compressed with a tiny decoder. Express per-network variants as flags with a pinned CTA hook, and run the whole thing as part of the build rather than as a regex post-processor. What does not transfer is scale and format. PlayCanvas never inlines wasm, because its playable path excludes all wasm modules, and its engine is ~12× smaller compressed. For a wasm engine plus PCK, gzip via native `DecompressionStream` beats PlayCanvas's lz4, and one compressed PCK blob beats per-asset base64.

### Cited Findings (PlayCanvas facts the inferences rest on)
- The loader patch is `pc.Http.prototype.get` (data URI → `atob` → JSON, text, ArrayBuffer or Blob), plus the passthrough "if url is object, return it" — [engine-patches](https://github.com/playcanvas/playcanvas-rest-api-tools/tree/main/engine-patches).
- The config is embedded as `JSON.parse("…")` specifically to avoid the ~30 % base64 hit — [one-page.js L296–333](https://github.com/playcanvas/playcanvas-rest-api-tools/blob/main/one-page.js).
- Engine: lz4 + base64 + JS decoder + `<script>` injection, saving ~500 KB at ~180 ms on 2017-era phones — [README](https://github.com/playcanvas/playcanvas-rest-api-tools#compress-engine-code).
- Images are converted to `Blob`, and `supportsImageBitmap` is disabled when XHR is patched out — [one-page-no-xhr-request.js](https://github.com/playcanvas/playcanvas-rest-api-tools/blob/main/engine-patches/one-page-no-xhr-request.js).
- The scripts' data URIs are rewritten to inline `<script>` text for networks that block base64 JS — [one-page-inline-game-scripts.js](https://github.com/playcanvas/playcanvas-rest-api-tools/blob/main/engine-patches/one-page-inline-game-scripts.js).
- MRAID: gate startup on `mraid` `ready` and size from `mraid.getMaxSize()` — [one-page.js](https://github.com/playcanvas/playcanvas-rest-api-tools/blob/main/one-page.js), [mraid resize patch](https://github.com/playcanvas/playcanvas-rest-api-tools/blob/main/engine-patches/one-page-mraid-resize-canvas.js).
- Fragility: regex edits of build output break on ESM. "Ideally these transforms are part of the bundling process" — [issue #50](https://github.com/playcanvas/playcanvas-rest-api-tools/issues/50).
- The Basis module loads its wasm via `fetch(wasmUrl)` + `compileStreaming` and its glue via a Blob-URL worker — [basis.js](https://github.com/playcanvas/engine/blob/main/src/framework/handlers/basis.js). PlayCanvas has the hooks (URLs in `WasmModule` config) to pass a `data:` or `blob:` URL, but the official tool does not use them.

### Inferences
- **Loader hook rather than global fetch shim.** The Godot equivalent of patching `Http.get` is to hook the Emscripten/Godot loader at its entry points: supply the wasm through the Emscripten module's instantiate hook (or a `fetch` override restricted to the one `${base}.wasm` URL), and the PCK as an `ArrayBuffer` through the preload API. Both are already sketched in `playable_ads.md`. PlayCanvas's experience suggests keeping the hook narrow (one function) and making it a build-time option rather than a global `window.fetch`/XHR replacement. Moloco/Meta scanners flag the `XMLHttpRequest` token anyway, and PlayCanvas tells users to ignore Meta's warning, which is only acceptable when the code path is provably dead.
- **Pass objects, not data URIs, for big blobs.** PlayCanvas avoids re-encoding `config.json` by embedding it as a JS literal. For Godot, the PCK is the large blob. Embed it once (compressed, base64 or base122 for AppLovin), decode it to an `ArrayBuffer`, and hand it to the engine without a `data:` URL round trip. This also gives cross-asset compression that PlayCanvas's per-asset base64 lacks.
- **Compression choice.** PlayCanvas's lz4 made sense for a JS engine without native decompression (2019-era). On engine 1.39.4, lz4 gives 475,869 B against 290,978 B for gzip -9 `[measured]`, so lz4 is ~64 % larger. Our Godot wasm needs the best ratio available. Native `DecompressionStream('gzip')` costs no decoder bytes. zstd or brotli need a JS/wasm decoder (see `playable_ads.md` §6). lz4 is not a candidate.
- **Variants as data, size check as a test.** PlayCanvas's flags (`mraid_support`, `snapchat_cta`, `extern_files`, `patch_xhr_out`) map naturally to attributes of a per-network Bazel rule or macro. The gaps PlayCanvas left open are worth closing in our design: per-network CTA injection (Meta, Google ExitApi, Unity and AppLovin MRAID), a hard size assertion (a Bazel test on the output's counted size), and a per-asset size report, which PlayCanvas has as `--size-report` and which maps to a report action over PCK contents.
- **Build-integrated, not post-hoc.** PlayCanvas's own engineer names regex post-processing as the failure mode. In Bazel, the shell HTML, loader patch and inlining should be produced from structured inputs: our own HTML template and a JS loader we own. Regex edits of Godot's exported `index.html`/`godot.js` should be avoided.
- **Size gap.** PlayCanvas (current, tree-shaken, "playable" feature set) is ~0.40 MB gzip / ~0.31 MB brotli. Godot L2 is 5.2 MB gzip / 3.6 MB brotli, ~12× larger. PlayCanvas's budget advice ("~500 KB for assets in 2 MB") has no Godot analogue on Meta single HTML. On 5 MB networks Godot is at the limit before assets. PlayCanvas therefore provides mechanism precedent but no feasibility precedent for a wasm engine. For that, Defold (zstd + base64 wasm engine, < 1 MB) remains the relevant reference (`playable_ads.md` §5).
- **Tree shaking as a design analogue.** PlayCanvas's `AppBase` + explicit systems list is the JS counterpart of Godot's module or class disabling (`build_profile`, `disable_*`). The WGSL-chunks-in-WebGL-build observation is a reminder to check our L2 build for renderer code that is still linked but dead (e.g. shader sources of unused renderers). `minimal_engine_size.md` found ~0.29 MB of GLSL in the data section.

### Gaps
- None of the Godot-side mappings above was prototyped here. They depend on the experiments already listed in `playable_ads.md` ("Open points").
- No evidence of how ad-network scanners treat a `fetch` override vs. an Emscripten instantiate hook. PlayCanvas only provides the Meta `XMLHttpRequest` warning anecdote.
