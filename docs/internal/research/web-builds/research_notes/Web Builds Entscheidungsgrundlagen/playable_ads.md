# Playable ads: ad network requirements and what they mean for a Godot 4.7 web export

Researched 2026-11-23. Network docs change without notice; each finding names the page and, where shown, its "last updated" date. `[secondary]` marks third-party blogs, vendor tools and spec aggregators. Everything else is a network's own page, an engine's own docs, or a local measurement.

Local measurements use the official 4.7.2 template `web_nothreads_release.zip` (`T47` in [export_shell_pwa_hosting.md](export_shell_pwa_hosting.md)), extracted to the session scratchpad. Godot source references point at 4.7.2 (`G47`, same file).

## Summary table

"Counted size" says which bytes the limit applies to. Raw HTML means the uploaded `.html` itself, with base64 overhead included. ZIP means the compressed archive.

| Network | Size limit | Counted size | Package | Required API / CTA | MRAID | External requests |
| --- | --- | --- | --- | --- | --- | --- |
| Google Ads (App campaigns, serves on AdMob too) | 5 MB, ≤ 512 files | ZIP | ZIP with HTML + relative files | `ExitApi.exit()` via hosted `exitapi.js`; `ad.orientation` meta | Optional ("or MRAID equivalent") | Forbidden except `exitapi.js`, Google Fonts, Google-hosted jQuery/GreenSock/CreateJS |
| Meta (FB, IG, Audience Network) | Single HTML 2 MB; ZIP 5 MB, < 100 files (conflict, see §1) | Raw HTML / ZIP | Single HTML with data URIs, or ZIP with root `index.html` | `FbPlayableAd.onCTAClick()` (upload fails without it) | Must work without `mraid.js` | Forbidden (no XHR, no JS redirects) |
| AppLovin (Axon) | 5 MB | Raw HTML | Single HTML, all resources base64 or base122 | `mraid.open()` after `ready` | Required, 2.0 | Forbidden |
| Unity Ads (and ironSource direct, sunset 2026-04-30) | < 5 MB | Raw HTML | Single minified `index.html`, assets base64 | `mraid.open()`, start on `ready` + viewable | Required, 3.0 (injected) | Forbidden (no XHR) |
| ironSource Exchange (programmatic, shuts down 2026-12-31) | 4 MB assets + code | Downloaded bytes | HTML/JS snippet, not a full document | `mraid.open(url)`, `mraid.getMaxSize()` | 2.0 | Absolute HTTPS URLs allowed |
| Mintegral | 5 MB | ZIP | ZIP → folder → HTML, identical names; non-JS/HTML files base64 | `window.install()`, `window.gameReady()`, `window.gameEnd()`; optional `gameStart`/`gameClose`/`gameRetry` | Not used | Forbidden ("no dynamical request") |
| Liftoff Accelerate (DSP) | HTML up to 5 MB (recommendation table) | not stated | Single HTML **or** ZIP with relative files on Liftoff's CDN | `mraid.open()` (preferred) or `Liftoff.open()` | Used when available | Relative files allowed; absolute URLs not |
| Vungle / Liftoff Monetize (direct) | 5 MB [secondary] | not verified | `ad.html` single file or ZIP [secondary] | not verified (Vungle help pages return 403) | — | — |
| TikTok + TikTok Ad Network (ex-Pangle) | < 5 MB "after compression" | ZIP | ZIP with root `index.html` + `config.json` | Hosted `playable-sdk.js` + `window.openAppStore()` | Must not be `mraid.js` format | Forbidden except the SDK script |
| Moloco | < 5 MB | Raw HTML | Single HTML, data URIs, **not** ZIP | `FbPlayableAd.onCTAClick()` | Must not include `mraid.js` | Forbidden; `XMLHttpRequest` token forbidden |
| Digital Turbine (DT Exchange) | Recommended 2 MB, no published max | — | MRAID 2.0 or HTML | `mraid.open()` (MRAID 2.0) | 2.0 optional; 3.0 not supported (rewarded) | not stated |
| Snapchat App Playables | 5 MB | ZIP | ZIP with root `index.html` + `config.json` (`1` = portrait) | `ScPlayableAd.onCTAClick()` | Must not require `mraid.js` | Forbidden |

## 1. Size limits, counted size, file count

### Takeaway
Every network caps at 5 MB or less. What differs is what the cap measures. Google, TikTok/Pangle, Mintegral, Snapchat and Meta's ZIP format cap the **compressed ZIP**. AppLovin, Unity, Moloco and Meta's single-HTML format cap the **raw HTML file**, so base64 overhead counts in full. Meta's single-HTML limit is 2 MB in its developer docs. The official 4.7.2 engine alone is 39.5 MB raw, 10.05 MB gzip -9 and 6.65 MB xz -9e, so it fits nowhere. Even a stripped engine (13–16 MB raw, about 2.4 MB brotli, about 3.4 MB gzip per secondary reports) fits only as a compressed payload under the 5 MB caps, and not under Meta's 2 MB single-HTML cap.

### Cited Findings
- Google App campaigns: upload a .ZIP, "maximum size of 5MB", "no more than 512 files", up to 20 ZIPs per ad group, UTF-8, explicit end tags, `ad.orientation` meta tag required — [Google Ads Help: About HTML5/Playable ads for App campaigns (answer 9981650, no date shown, fetched 2026-11-23)](https://support.google.com/google-ads/answer/9981650?hl=en). Answer 7584219 now shows the same content. Older figures of 1 MB / 40 files surfaced in search snippets of that page and are outdated.
- Google display HTML5 (not App campaigns): 600 KB, ≤ 40 files, ZIP may contain only "HTML and optionally CSS, JS, GIF, PNG, JPG, JPEG, SVG", and local storage methods are forbidden — [Uploaded display ads specifications (answer 1722096)](https://support.google.com/google-ads/answer/1722096?hl=en). The App-campaign page lists no allowed file types. Whether a `.wasm` or `.pck` inside the ZIP passes Google's validator is **unverified**; Defold's tool repeats the display file-type list for playables [secondary] ([defold-playable-ads README](https://github.com/indiesoftby/defold-playable-ads)).
- Meta developer docs, troubleshooting table: "Upload Too Large: Your zip file is larger than 5MB"; "Uploaded Bundle Too Many SubAssets: … more than 100 files"; "Uploaded File Is Too Large: Your single HTML file is larger than 2MB or the `index.html` file is larger than 2MB" — [Meta for Developers: Playable Ads for Mobile Apps](https://developers.facebook.com/docs/app-ads/formats/playable-ad).
- **Conflict (Meta)**: Meta's Business Help Center spec page ([412951382532338](https://www.facebook.com/business/help/412951382532338)) could not be fetched. Secondary summaries disagree on what it says. [Bolt Playables, checked 2026-10-28](https://boltplayables.com/playable-ad-specs/facebook/), [Genie Labs, verified 2026-09-30](https://www.genielabs.tech/learn/specs/meta) and [GenPlay, 2026-10-31](https://getgenplay.ai/guides/playable-ad-specs-by-network) say 5 MB for both formats. [Arc Studio, checked 2026-11-10](https://arc-studio.tech/meta-playable-ads) says 2 MB HTML / 5 MB ZIP. All [secondary]. The developer docs (primary) say 2 MB for the HTML, and 2 MB is the safe target.
- AppLovin: "Each ad file must be 5 MB or smaller", "Each ad must be a single HTML file" — [AppLovin Best practices & guidelines](https://support.applovin.com/en/growth/promoting-your-apps/creatives/best-practices-and-guidelines) (same content at support.axon.ai).
- Unity Ads: "A single HTML file (`index.html`)", "Less than 5 MB"; "The device downloads only the HTML file from the content delivery network (CDN), and Unity Ads ignores anything outside that file" — [Unity Playable specifications, last_updated 2026-10-28](https://docs.unity.com/en-us/user-acquisition/creatives/specifications/playable.md).
- ironSource Exchange: "All assets + code downloaded to the device must be up to 4MB max" — [Unity Grow: MRAID specifications and guidelines (ironSource Exchange)](https://docs.unity.com/en-us/grow/programmatic/ironsource-exchange/mraid-specifications-guidelines).
- Mintegral (Mindworks guideline, which Mintegral's help center routes to): "Zip file of the Playable should not by larger than 5M in size. All file names are only allowed letters, numbers, and underscores. Name of Zip File, Assets Folder, HTML, must be the same. The HTML file inside the ZIP needs to be openable locally." — [Mindworks Guideline – Playable Testing](https://www.playturbo.com/review/doc). Mintegral's own help center ([asset specs](https://helpcenter.mintegral.com/en/docs/ad-asset)) reportedly says "HTML (single file)", a contradiction noted by [Segwise, 2026-09-18](https://segwise.ai/blog/playable-ad-specs-by-network-2026) [secondary]; the help-center pages rendered without body text here.
- TikTok: "The Playable ad materials should be in .zip format", "smaller than 5MB (after compression)", `index.html` and `config.json` at top level — [TikTok Ads Help: About playable ads, "Last updated: September 2026"](https://ads.tiktok.com/help/article?aid=12099). TikTok Ad Network (ex-Pangle) lists the same file rules ([Bolt Playables, checked 2026-11-09](https://boltplayables.com/playable-ad-specs/tiktok/) [secondary]).
- Liftoff Accelerate: "Liftoff accepts creatives as either a single HTML file or a zip file containing a single folder with all the assets … Liftoff hosts these files on its content delivery network (CDN)"; recommendation table "HTML | Up to 5MB" — [Liftoff Interactive Ad Integration, updated 2026-10-01](https://support.accelerate.liftoff.io/hc/en-us/articles/52724569196699-Interactive-Ad-Integration) (old URL docs.liftoff.io/creative_integration_api redirects there).
- Vungle: "Format: Single html file (ad.html) or zip file with resources", "Size: Up to 5MB" — [Unity Playworks (Luna) docs: Vungle](https://docs.lunalabs.io/docs/playable/ad-networks/vungle/) [secondary: Unity's tool, not Vungle]. support.vungle.com returned HTTP 403.
- Moloco: "File size | Less than 5MB", "Ad file must not be compressed into `.zip` format for upload" — [Moloco Playable and IEC creative guide, updated 2026-09-22](https://help.moloco.com/hc/articles/24124525963799).
- Digital Turbine: "the recommended file size for Playables is 2 MB" — [DT docs: Playables](https://docs.digitalturbine.com/dt-ads-demand/ad-creative-types/playables).
- Snapchat: "Playable Ad should be in zip file", "File Size = Up to 5MB" — [Snapchat Business Help: App Playables](https://businesshelp.snapchat.com/s/article/app-playables?language=en_US).
- Local measurement, official 4.7.2 nothreads template: `godot.wasm` 39,514,754 B raw; `gzip -9` 10,054,769 B; `xz -9e` 6,645,384 B; base64 of raw 52,686,341 B; base64 of gzip 13,406,361 B. `godot.js` 279,815 B raw, 68,480 B gzip.
- Stripped-build size reports [secondary]: a Godot 4.3-era 2D build with `optimize=size`, 3D and almost all modules disabled, plus `wasm-opt`, gave 13 MB wasm, "2.4M min_brot.wasm.gz", "3.4M min_gzip.wasm.gz" ([amann.dev, 2025-01-05](https://amann.dev/blog/2025/godot_web_size/)). A Godot 4.5 build with `optimize=size_extra`, `lto=full`, `modules_enabled_by_default=no` and a build profile gave "15.6MB Uncompressed, and 3.69MB Compressed to a zip" ([Popcar's blog, 2025-03-11, 4.5 update](https://popcar.bearblog.dev/how-to-minify-godots-build-size/)). Our own stripped measurement is pending (see the caller's parallel work).
- An empty Godot 4.7.2 export is "19.0x Meta's cap, 7.6x a 5 MB cap"; the repo built no stripped template — [zednaked/playable-budget](https://github.com/zednaked/playable-budget) [secondary].

## 2. Single file, inlining, external requests, browser APIs

### Takeaway
Of the major networks, only Google (ZIP with relative files) and Liftoff Accelerate (ZIP hosted on its CDN) let the creative fetch sibling files. TikTok and Mintegral take ZIPs but still forbid HTTP requests. Mintegral additionally demands base64 for all non-JS files and an HTML file that opens locally. Everyone else wants one self-contained HTML file. No network page forbids WebAssembly, eval, Web Workers, AudioWorklet or WebGL2 by name. The practical traps are elsewhere: CSP on data URLs (Meta), static token scans (`XMLHttpRequest` on Moloco and Meta, JS redirects on Meta, TikTok and Snap), and Google's local-storage ban. The stock Godot JS glue contains several of those tokens. No network offers COOP/COEP, so threads are out, consistent with the nothreads default.

### Cited Findings
- Inlining:
  - AppLovin: "All resources must be embedded in either base64 or base122 format; external resources are prohibited", "External network calls are prohibited" — [AppLovin guidelines](https://support.applovin.com/en/growth/promoting-your-apps/creatives/best-practices-and-guidelines). Base122 is an AppLovin-specific allowance with about 14 % overhead instead of 33 %.
  - Unity: "Every image, audio, and video asset inlined as base64 data"; "No references to other files, folders, or assets through relative paths or remote URLs"; "The playable runs without network requests (XHR)" — [Unity Playable specifications](https://docs.unity.com/en-us/user-acquisition/creatives/specifications/playable.md).
  - Mintegral: "All files besides JS and HTML should be processed into base64", "make sure that there is no dynamical request" — [Mindworks guideline](https://www.playturbo.com/review/doc).
  - Moloco: "must not include the JavaScript object `XMLHttpRequest`", "must not make any external references such as dynamic asset loading through an external network and HTTP requests", "A single ad file containing all assets … must be data-URI-compressed prior to upload" — [Moloco guide](https://help.moloco.com/hc/articles/24124525963799).
  - TikTok: "No loading dynamic materials from external networks", no HTTP requests, no JS redirects. The page also recommends "breaking materials into smaller pieces and enabling parallel downloads", which suggests that files inside the ZIP may be loaded — [TikTok About playable ads](https://ads.tiktok.com/help/article?aid=12099). Whether a `fetch()` of a sibling file in the ZIP counts as a forbidden HTTP request is **unclear**.
  - Snapchat: "No dynamic asset loading through external network is permitted", "must not make any external http requests" — [Snapchat App Playables](https://businesshelp.snapchat.com/s/article/app-playables?language=en_US).
- Relative files allowed:
  - Google: "All code and assets must be referenced using a relative path to resources included in the .ZIP file" — [Google answer 9981650](https://support.google.com/google-ads/answer/9981650?hl=en).
  - Liftoff: "Always reference assets using relative paths"; Liftoff even documents a Blob-URL fallback for `new Worker()` because its "CDN does not expose Access-Control-Allow-Origin headers for JS files", and forbids `<iframe>` — [Liftoff Interactive Ad Integration](https://support.accelerate.liftoff.io/hc/en-us/articles/52724569196699-Interactive-Ad-Integration). Liftoff is the only network page that mentions Web Workers, and it treats them as allowed.
- Local storage: Google HTML5 rules "Local storage methods can't be used" (GWD restrictions on answer 9981650; display spec answer 1722096). Godot's JS glue mounts IDBFS: `indexedDB` appears 3× in `godot.js` (local scan). Whether IDBFS init even runs or fails gracefully in an ad webview, and whether Google's validator flags it, is **untested**.
- WebAssembly:
  - No network page mentions it. Prior art runs wasm inside accepted playables: Defold's tool inlines the engine wasm (`wasm-web`) zstd-compressed and base64-encoded, with Facebook, Unity and AppLovin marked "Supported ✅" ([defold-playable-ads, tool 1.5.4 / Defold 1.11.1](https://github.com/indiesoftby/defold-playable-ads)); a Cocos 3.x packer registers a WASM downloader for Bullet physics ([SABERBOY/CocosCreator3DPlayable](https://github.com/SABERBOY/CocosCreator3DPlayable)) [secondary].
  - The older Defold 2021 version still used asm.js instead of WASM ([Defold forum, 2021-06-22](https://forum.defold.com/t/defold-for-playable-ads/68689)), so the switch to wasm-in-playables there is recent.
- CSP and data URLs:
  - Needle's Meta profile troubleshooting: "CSP blocks a data URL | Rebuild the Meta profile. The profile uses Blob URLs for embedded game files", and Meta Playable Preview reports "package and CSP results" — [Needle Engine: Meta playable](https://engine.needle.tools/docs/how-to-guides/deployment/playable-ads/meta.html) [secondary: engine vendor].
  - Background: `fetch()` of a `data:` URL is checked against `connect-src`, and wasm compilation needs `'wasm-unsafe-eval'` (or `'unsafe-eval'`) when a CSP is present — [MDN script-src](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/script-src); example breakage in [coder/ghostty-web#188](https://github.com/coder/ghostty-web/issues/188).
  - The exact CSP each network sets is **not published**. Implication: decode base64 into an `ArrayBuffer` in JS and call `WebAssembly.instantiate(bytes)`, never `fetch('data:…')`. Use Blob URLs only where a URL is unavoidable (worklets).
- Godot 4.7.2 loader specifics relevant to inlining:
  - `Engine.load` always fetches `${loadPath}.wasm` through `preloader.loadPromise` → `fetch(file)` — [G47 platform/web/js/engine/engine.js:43-49](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/js/engine/engine.js#L43-L49), [preloader.js:29-45](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/js/engine/preloader.js#L29-L45). There is no option to pass wasm bytes; a shell must shim `fetch` or patch the loader.
  - `preloadFile` accepts an `ArrayBuffer` or typed-array view for the PCK — [engine.js:120-130](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/js/engine/engine.js#L120-L130), [preloader.js:103-121](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/js/engine/preloader.js#L103-L121).
  - Both worklet scripts are resolved through `locateFile` to `${loadPath}.audio(.position).worklet.js` and loaded with `ctx.audioWorklet.addModule(path)`, which needs a URL. The position worklet is added on every audio init, including nothreads builds — [config.js:294-327](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/js/engine/config.js#L294-L327), [library_godot_audio.js:1285-1286](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/js/libs/library_godot_audio.js#L1285-L1286). In a single file these must become Blob URLs. `AudioWorklet` is a secure-context API, and whether ad webviews (often `loadDataWithBaseURL` or `about:blank`) are secure contexts is **unverified**.
  - nothreads registers `AudioDriverWorklet` and then the `AudioDriverScriptProcessor` fallback — [os_web.cpp:303-306](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/os_web.cpp#L303-L306).
- Static token scan of official 4.7.2 nothreads `godot.js` (local):
  - `XMLHttpRequest` 5× (Emscripten's worker `readBinary` and lazy-file FS code);
  - `window.open` 1× (`_godot_js_os_shell_open`);
  - `eval(` 3× (`JavaScriptBridge.eval`);
  - `indexedDB` 3× (IDBFS);
  - `location.href` 1× (worker `_scriptName`);
  - `WebSocket` 13× and `RTCPeerConnection` 13× (module JS libraries).

  Moloco's checker rejects the `XMLHttpRequest` token outright, and Needle's Meta profile "rejects browser popups and `XMLHttpRequest`" ([Needle reference](https://engine.needle.tools/docs/reference/playable-ads.html) [secondary]). A playable build therefore needs Emscripten settings or post-processing that remove these paths, beyond module stripping.
- Threads/SharedArrayBuffer: none of the network pages offers COOP/COEP headers, and Unity/AppLovin/Moloco serve the HTML from their own CDN or webview. Godot's own docs say threaded exports need cross-origin isolation, "meaning no ads, nor third-party integrations" — [Godot docs: Exporting for the Web (4.7)](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_web.html). Playables are nothreads-only.
- WebGL: AppLovin "If using WebGL, provide a UI fallback if initialization fails or the context is lost" ([AppLovin guidelines](https://support.applovin.com/en/growth/promoting-your-apps/creatives/best-practices-and-guidelines)). Unity's minimum OS is "Android 5 or later, iOS 13 or later". Godot 4 needs WebGL 2.0, which Safari/WKWebView enabled only with iOS 15, so a Godot playable cannot meet Unity's iOS 13 floor and needs the fallback UI on old devices.
- Service workers and PWA: no network mentions them. They cannot work from a data/CDN-served single file in an ad webview and are irrelevant for playables (inference).

## 3. Required SDK/API integration and CTA

### Takeaway
There is no common API. MRAID networks (AppLovin 2.0, Unity 3.0, Liftoff, DT, ironSource Exchange) want `mraid.open()` after `ready`, and Unity additionally wants start and pause on viewability. Meta, Moloco and Snapchat forbid or do not need `mraid.js` and use `FbPlayableAd.onCTAClick()` or `ScPlayableAd.onCTAClick()`. Google uses `ExitApi.exit()`. TikTok/Pangle use a hosted SDK plus `window.openAppStore()`. Mintegral uses `window.install()` plus mandatory `gameReady()`/`gameEnd()` lifecycle calls. Every network forbids redirects without a user tap, and several forbid a redirect on the first tap. Tools solve this with one game-facing bridge (`install()`, `gameReady()`, `gameEnd()`) and a per-network adapter injected at packaging time.

### Cited Findings
- IAB MRAID 3.0:
  - The ad "must request the mraid.js script while the HTML ad is being loaded", must wait for `ready` when `getState()=='loading'`, and "When MRAID is used, all hyperlinks must use mraid.open()".
  - "The isViewable() method and viewableChange event are deprecated in MRAID 3.0" in favor of `exposureChange`; `audioVolumeChange` is new — [IAB MRAID 3.0 final, 2018-06-21](https://iabtechlab.com/wp-content/uploads/2018/06/MRAID_3.0_FINAL_June_2018.pdf).
  - The best-practices guide insists the script tag "must always be included" — [MRAID 3.0 Best Practices](https://iabtechlab.com/wp-content/uploads/2018/06/MRAID-3.0-Best-Practices-Guide.pdf).
- AppLovin: "HTML ads must support MRAID v2.0"; "Wait for the ready event (or confirm `mraid.getState()` is not `'loading'`)"; "Use `mraid.open()` for click-through actions" — [AppLovin guidelines](https://support.applovin.com/en/growth/promoting-your-apps/creatives/best-practices-and-guidelines).
- Unity:
  - Requires MRAID 3.0, injected by the webview, so "your playable doesn't need an MRAID script tag". This contradicts the IAB best practice above.
  - Start "Only after the MRAID `ready` event, and only when the ad is viewable", pause when not viewable (sample code uses the deprecated `viewableChange`/`isViewable`, which Unity still supports).
  - Store via `mraid.open`, only after gameplay and a player tap, never on the first tap. No custom close buttons; `expand`, `resize`, `sms`, `tel`, `calendar` and `storePicture` are unsupported.
  - Source: [Unity Playable specifications](https://docs.unity.com/en-us/user-acquisition/creatives/specifications/playable.md). Unity Exchange (programmatic) shows `<script src="mraid.js">` and documents `exposureChange`/`audioVolumeChange` — [Unity Exchange playable ads](https://docs.unity.com/en-us/grow/programmatic/unity-exchange/playable-ads).
- Liftoff:
  - `mraid.open()` (preferred) or `Liftoff.open()`, after `Liftoff.ready`/MRAID `ready`; "Do not use window.location".
  - "Some ad exchanges do not fire viewableChange events if the ad is already visible … always check mraid.viewable immediately after mraid.ready".
  - No close button in the creative; a 50×50 px top-corner region may be obscured.
  - Source: [Liftoff Interactive Ad Integration](https://support.accelerate.liftoff.io/hc/en-us/articles/52724569196699-Interactive-Ad-Integration).
- Google: include `exitapi.js` (tpc.googlesyndication.com) in `<head>` and call `ExitApi.exit()`. Without it "or an MRAID equivalent", Google adds an "Install" button itself — [Google answer 9981650](https://support.google.com/google-ads/answer/9981650?hl=en).
- Meta: "Missing CTA Click Function Call | The playable code does not use the JavaScript function `FbPlayableAd.onCTAClick()`", "Uploaded File Contains Redirect to External Link" — [Meta for Developers](https://developers.facebook.com/docs/app-ads/formats/playable-ad). Meta injects `FbPlayableAd`; guard with `typeof FbPlayableAd !== 'undefined'` ([PlayCanvas forum thread](https://forum.playcanvas.com/t/fbplayablead-onctaclick-not-found/13643)) [secondary].
- Moloco: call `FbPlayableAd.onCTAClick()` "without any parameters", and do not include `mraid.js` — [Moloco guide](https://help.moloco.com/hc/articles/24124525963799). Moloco's API path for DSP-uploaded HTML sets flags `MRAID2` instead ([Moloco Campaign Management API](https://developer.moloco.cloud/docs/campaign-management-api)), so the Ads Manager and API routes differ.
- Mintegral:
  - `window.install && window.install();` for every store or web redirect, with a CTA "visible throughout the entire playable".
  - `window.gameReady()` once all resources have loaded, and `window.gameEnd()` on win or fail.
  - Optional global `gameStart()`/`gameClose()` (Mintegral calls them) and `window.gameRetry()`.
  - Mintegral supplies the close button and the loading page ("please do not add it yourself"); do not override `console`; no auto-redirects.
  - The test tool runs in a desktop browser, so mouse input must work.
  - Source: [Mindworks guideline](https://www.playturbo.com/review/doc).
- TikTok/Pangle: include `Playable-sdk.js` at the bottom of `<body>` before own JS, call `window.openAppStore()`, "Don't use mraid.js format" — [TikTok About playable ads](https://ads.tiktok.com/help/article?aid=12099). The SDK URL differs in case between TikTok pages, and the capitalized one returned 404 on 2026-11-09 ([Bolt Playables](https://boltplayables.com/playable-ad-specs/tiktok/) [secondary]).
- Snapchat: "Must call ScPlayableAd.onCTAClick() when clicking on CTA"; `config.json` orientation must be 1 — [Snapchat App Playables](https://businesshelp.snapchat.com/s/article/app-playables?language=en_US). PlayCanvas's Snapchat page still describes MRAID 2.0 with a `snapchatCta()` hook and CDN-hosted external files, which is **outdated** relative to Snap's current page ([PlayCanvas Snapchat Playable Ad](https://developer.playcanvas.com/user-manual/editor/publishing/playable-ads/snapchat-playable-ads/)).
- ironSource: legacy playables used `dapi.openStoreUrl()` with `mraid.open` fallback ([Playbaker ironSource export, 2026-10-23](https://playbaker.com/networks/ironsource) [secondary]). ironSource Ads direct demand stopped serving on 2026-04-30 ([Unity: ironSource Ads sunset guide](https://docs.unity.com/en-us/grow/is-ads/ironsource-ads-sunset)). On 2026-11-16 Unity announced that the ironSource Exchange shuts down and the iAds SDK stops delivering ads on 2026-12-31 ([Unity: Sunsetting ironSource Ads FAQ](https://unity.com/products/ironsource-ads-sunset)). LevelPlay mediation continues, and playables for that inventory follow the Unity Ads spec.
- DT Exchange: Playables "use MRAID 2.0 or HTML ad protocols"; for rewarded, "VAST and MRAID 3.0 are not currently supported"; `mraid.open` fires click tracking — [DT Playables](https://docs.digitalturbine.com/dt-ads-demand/ad-creative-types/playables), [DT Rewarded Playables](https://docs.digitalturbine.com/dt-ads-demand/ad-creative-types/rewarded-playables), [DT MRAID 2.0](https://docs.digitalturbine.com/dt-ads-demand/ad-formats/mraid-2.0).
- Cross-network adapter pattern (prior art):
  - Defold: `window.Playable` with `gameLoaded()`, `gameEnd()`, `install()`, `retry()`; CTA checks `FbPlayableAd`, then Mintegral `window.install`, then `mraid.open`, then `ExitApi` ([defold-playable-ads](https://github.com/indiesoftby/defold-playable-ads)).
  - Needle maps one `openStore()` per profile, a table of `mraid.open()` / TikTok SDK / `ExitApi.exit()` / `FbPlayableAd.onCTAClick()` / `window.install()` ([Needle: Build Playable Ads](https://engine.needle.tools/docs/how-to-guides/deployment/playable-ads.html)).
  - Cocos `super-html` / `plbx_html` exposes `download()`, `game_ready()`, `game_end()` ([plbx-cocos-assistant](https://github.com/playbox-org/plbx-cocos-assistant)). All [secondary].

## 4. Other constraints: playtime, orientation, loading, audio, end card, naming

### Takeaway
Orientation is the main structural difference. Unity, AppLovin, Mintegral, Moloco and Liftoff want one responsive build for both orientations. Meta and Snapchat are portrait. Google and TikTok declare orientation via a meta tag or `config.json`. Audio must stay muted until the first interaction, must stop when hidden, and must use Web Audio (iOS mute switch); Godot already uses Web Audio. Few networks publish a playtime cap. Naming rules are strict where they exist: Mintegral's triple-identical names, TikTok's and Snap's `index.html` + `config.json`, Vungle's `ad.html`, Unity's `index.html`, ASCII-only names on Liftoff.

### Cited Findings
- Orientation:
  - Google: `<meta name="ad.orientation" content="portrait">` / `landscape` / `portrait,landscape` (or `ad.size` 320×480 / 480×320) — [Google answer 9981650](https://support.google.com/google-ads/answer/9981650?hl=en).
  - Unity: "Portrait and landscape, from a single responsive build", single-orientation "marked for deprecation"; keep interactive content out of top/bottom bands reserved for Unity's controls — [Unity spec](https://docs.unity.com/en-us/user-acquisition/creatives/specifications/playable.md).
  - AppLovin: "must function properly in both landscape and portrait orientations".
  - Mintegral: "must can be adapted to both landscape and portrait mode, and supported for free rotation".
  - TikTok: `config.json` `Playable_orientation` 0/1/2.
  - Snapchat: portrait only (`1`).
  - Moloco: "Both portrait and landscape".
- Audio:
  - AppLovin: "Audio must remain muted until the first user interaction" and must "stop or be muted when the ad closes or becomes hidden".
  - Google: sound must not start before interaction.
  - Liftoff: "Do not start audio automatically on page load".
  - Unity: silent under the iOS mute switch ("use the Web Audio API as the primary audio path … `HTMLAudioElement` ignores the iOS mute switch") and stop audio on `viewableChange`.
- Timing and playtime:
  - AppLovin: "Each ad's timer must start only after the first user interaction"; must not redirect "on the first tap/click"; "must fully load and become interactive in a reasonable time frame" (no number given).
  - DT shows a Close/Back button after 2 s for interstitial playables and after 30 s for rewarded ones ([DT Playables](https://docs.digitalturbine.com/dt-ads-demand/ad-creative-types/playables), [Rewarded](https://docs.digitalturbine.com/dt-ads-demand/ad-creative-types/rewarded-playables)).
  - No other primary page sets a maximum playtime.
- Loading:
  - Liftoff recommends progressive loading (a 10–20 KB bootstrap first) — [Liftoff](https://support.accelerate.liftoff.io/hc/en-us/articles/52724569196699-Interactive-Ad-Integration).
  - Mintegral wants all resources loaded at init, then `gameReady()`, and adds its own loading page.
  - Unity: "Don't start playable content on page load".
  - A Godot playable's startup cost (base64 decode + decompress + wasm compile of a 13–16 MB module on low-end Android) is **unmeasured**. Defold's tool warns to cut the heap to its 32 MB minimum "to allow your game to run on low-end Android devices" ([defold-playable-ads](https://github.com/indiesoftby/defold-playable-ads)); Godot's default `initial_memory` is 32 MiB with `ALLOW_MEMORY_GROWTH` ([G47 platform/web/detect.py:42, 162, 332](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/detect.py#L42)).
- End card:
  - Unity: playable end cards need "a call to action (CTA) button that opens the app store".
  - Mintegral: win/lose page download button must be highlighted.
  - TikTok generates its own end card.
  - DT: "The end card should be part of the ad itself".
  - The network or SDK owns the close button (Unity, AppLovin, Liftoff, Mintegral, ironSource).
- Naming:
  - Unity `index.html`.
  - Vungle `ad.html` [secondary].
  - Mintegral `X.zip/X/X.html` with `[A-Za-z0-9_]`.
  - TikTok and Snap root `index.html` + `config.json`.
  - Meta ZIP root `index.html`.
  - Liftoff ASCII-only, case-sensitive.
  - Google: any name, relative paths, UTF-8.
- Validators: AppLovin Playable Preview, Unity Ad Testing app, Meta Playable Preview Tool (checks CSP, file loads, CTA), Google HTML5 Validator, Mindworks Playable Test Tool ([playturbo.com/review](https://www.playturbo.com/review)), TikTok and Snap Ads Manager preview. All exist as web tools and could back an opt-in manual check, but none is a CLI.

## 5. Prior art: how other engines produce playables

### Takeaway
Every engine with a playable story uses a **post-build packager**. The packager takes the normal web build, inlines everything (base64 or Blob URLs), often compresses the engine or resources and decompresses at runtime, injects a per-network CTA/lifecycle adapter, and writes one HTML or ZIP per network with a size check. Engines with a small JS runtime (PlayCanvas ~1.2–1.7 MB raw, PixiJS ~0.5–0.8 MB, Luna's transpiled C#) have room for assets. Defold is the closest analogue to Godot (C++ engine → wasm) and fits under 1 MB with a stripped engine and zstd. Nobody publicly ships Godot playables. A Godot forum answer from 2024 said PCK embedding for web is unsupported, with no plans; a 2026 measurement repo calls the stock export 19× Meta's cap. A Godot playable would need a custom export template plus a custom packager. Such tooling would be new rather than an adaptation of existing tools.

### Cited Findings
- Defold (most relevant analogue):
  - Gulp script builds `wasm-web`, and "The binary of the Defold engine is compressed using Zstd and encoded with Base64"; example build "less than 1 megabyte!" with BasisU, physics and Live Update disabled; heap minimum 32 MB; supported: Facebook, Google Ads, Mintegral, Unity Ads, AppLovin; Moloco and Snapchat untested — [indiesoftby/defold-playable-ads](https://github.com/indiesoftby/defold-playable-ads).
  - A 2019 Defold playable was approved and live on Facebook at 1.99 MB, then asm.js; "Defold is too heavy for playable ad (in my opinion). PixiJS and any other lightweight JS engine are much better" (tool author, 2019) — [Defold forum](https://forum.defold.com/t/playable-ads-made-with-defold-for-facebook-ads/41773) [secondary].
- PlayCanvas (official tool):
  - `npm run one-page` inlines everything as base64, with optional `patch_xhr_out` (removes XHR), `inline_game_scripts`, `extern_files` (ZIP variant) and `compress_engine`. The last one "Compresses the engine file to save 500KB", at the cost of decompression of "~180ms" on Pixel 2XL / Galaxy S7.
  - Limitations: "Modules are not supported (Basis and Ammo)", i.e. no wasm modules in single-file mode.
  - Source: [playcanvas-rest-api-tools](https://github.com/playcanvas/playcanvas-rest-api-tools). PlayCanvas docs: engine "~1.2MB uncompressed", base64 "adds ~30%", leaving "~500KB for assets" in Meta's 2 MB single HTML ([PlayCanvas FB Playable Ad](https://developer.playcanvas.com/user-manual/editor/publishing/playable-ads/fb-playable-ads/)).
  - A community member cut the engine to ~0.9–1 MB by removing components, and lz4 brought it to 400–500 KB ([PlayCanvas forum, 2022](https://forum.playcanvas.com/t/safe-cutting-of-modules/26730)) [secondary].
- Unity → Luna / Unity Playworks: does **not** use Unity WebGL. It transpiles C# to JavaScript with Bridge.NET and runs it on its own JS engine, with a "Compress resources" option, half-precision meshes and a 512 px texture default — [Luna docs: code overview](https://docs.lunalabs.io/docs/playable/code/overview/), [Set Optimal Settings](https://docs.lunalabs.io/docs/playable/playable-setup/settings/set-optimal-settings/), [command line pipeline](https://docs.lunalabs.io/docs/playable/command-line/). This shows the shape Unity chose: a separate lightweight runtime rather than shrinking the real engine.
- Cocos Creator: community packers dominate. `super-html` (most used), `cocos-pnp-playable` (overrides `assetManager.downloader` to read base64), `plbx-cocos-assistant` (30+ networks, HTML/ZIP per network, size report, SDK mocks), and AdsCraft (Cocos Store, 21 network specs, per-network size guard). Cocos physics (Bullet) ships as wasm and is inlined — [smoudjs/playable-scripts#6](https://github.com/smoudjs/playable-scripts/issues/6), [plbx-cocos-assistant](https://github.com/playbox-org/plbx-cocos-assistant), [AdsCraft](https://store.cocos.com/dashboard/en/detail/9665), [CocosCreator3DPlayable](https://github.com/SABERBOY/CocosCreator3DPlayable) [secondary].
- Needle Engine (three.js-based, Vite): built-in `playableAds` profiles for AppLovin, Unity, TikTok, Google Ads, Meta, Mintegral and WeChat produce `dist/<Network>/index.html|*.zip`, a JSON compliance report ("Base64 encoded, decoded, and expansion bytes", external URLs) and a `maxBytes` default of 5,000,000; the profiles strip offline-incompatible components — [Needle: Playable Ad Build Profiles](https://engine.needle.tools/docs/reference/playable-ads.html) [secondary: vendor docs]. This is the closest design reference for a "build-system target per network".
- PixiJS: a measured single-HTML playable is 630 KB, of which 84 % is PixiJS (tree-shaken, WebGL-only); base64 inflated 71.7 KB of PNG to 95.9 KB (+33.8 %) — [zednaked/playable-budget](https://github.com/zednaked/playable-budget) [secondary].
- Generic SDKs: `@smoud/playable-sdk` and `playable-scripts` wrap MRAID, DAPI, Mintegral (`gameReady`, `gameEnd`, `install`, `mintGameStart`, `mintGameClose`) and others behind one API ([playable-sdk](https://github.com/smoudjs/playable-sdk/), [defines.d.ts](https://cdn.jsdelivr.net/npm/@smoud/playable-sdk@1.2.1/defines.d.ts)) [secondary].
- Godot:
  - "PCK embedding isn't supported when exporting to the web … no plans to implement" (Calinou, 2024-02-09, answering a Google Ads playable upload failure) — [Godot forum](https://forum.godotengine.org/t/embed-remove-pck-file-in-html-export/46796).
  - An open proposal adds an optional gzip of wasm/pck plus `DecompressionStream` in the preloader, motivated by hosting, not ads — [godot-proposals#12208](https://github.com/godotengine/godot-proposals/issues/12208).
  - Searches of GitHub, the Godot Asset Store and forums turned up Godot web plugins for portals (CrazyGames, Poki, Yandex, Playgama) but **no Godot playable-ad tool and no report of a Godot playable in production**. Aggregators call Godot "the cautionary tale: an empty export is already over the limit" ([Genie Labs](https://www.genielabs.tech/learn/playable-ad-file-size) [secondary]).

## 6. Base64 overhead vs. compression; compressed payload inside the HTML

### Takeaway
Shipping a compressed payload inside the HTML and inflating it in JS is established and accepted. Defold's engine is zstd+base64 and was accepted on Facebook. PlayCanvas's official `compress_engine` option, Luna's "Compress resources" and Playbaker's "self-extracting HTML" do the same, and AppLovin explicitly allows base122. Native `DecompressionStream` covers gzip, deflate and deflate-raw everywhere relevant (Chromium/Android WebView 80+, iOS 16.4+). Brotli is **not** in Chromium or Android WebView, so a brotli payload needs a JS or wasm decoder; zstd needs one too (Defold, `fzstd`). The base64 tax depends on the counted size. For raw-HTML networks it is a full +33 % (+14 % with base122 on AppLovin). For ZIP-counted networks, base64 of an already compressed payload almost disappears after the ZIP's deflate: we measured +0.8 %. Base64 of uncompressed wasm instead costs +43 % over plain gzip.

### Cited Findings
- Local measurement on the official 4.7.2 `godot.wasm`:
  - `gzip -9(wasm)` = 10,054,769 B;
  - `gzip -9(base64(wasm))` = 14,407,846 B (+43 %);
  - `gzip -9(base64(gzip -9(wasm)))` = 10,135,471 B (+0.8 %);
  - `xz -9(base64(wasm))` = 8,836,012 B vs `xz -9e(wasm)` = 6,645,384 B.

  For ZIP-counted networks (Google, TikTok, Mintegral, Snapchat, Meta ZIP), pre-compress then base64; the ZIP size then ≈ the compressed payload size. For raw-HTML networks the +33 % stays.
- `DecompressionStream`: gzip/deflate baseline since Chrome 80, Firefox 113, Safari 16.4 (deflate-raw Chrome 103) — [web-features compression-streams](https://github.com/web-platform-dx/web-features/blob/main/features/compression-streams.yml.dist). "brotli" only in Firefox 147+ and Safari/iOS 18.4+, not in Chrome, Chrome Android or Android WebView as of the caniuse snapshot — [caniuse: DecompressionStream brotli](https://caniuse.com/mdn-api_decompressionstream_decompressionstream_brotli). The WHATWG Compression standard (updated 2026-10-19) now lists brotli — [compression.spec.whatwg.org](https://compression.spec.whatwg.org/). MDN additionally lists `"zstd"`, but no support data was found; treat it as unavailable. Unity's iOS 13 floor predates `DecompressionStream` (16.4), so either a JS fallback (fflate/pako) or accepting iOS ≥ 16.4 is needed; Godot's WebGL2 requirement already implies iOS ≥ 15.
- Compressed-payload prior art accepted by networks:
  - Defold zstd+base64 engine — [defold-playable-ads](https://github.com/indiesoftby/defold-playable-ads).
  - PlayCanvas `compress_engine` (~500 KB saved, ~180 ms decode) — [playcanvas-rest-api-tools](https://github.com/playcanvas/playcanvas-rest-api-tools).
  - Luna "Compress resources" — [Luna optimal settings](https://docs.lunalabs.io/docs/playable/playable-setup/settings/set-optimal-settings/).
  - Playbaker ships builds over 5 MB "as a compressed self-extracting HTML: the game is gzipped inside the file and unpacked by the browser when the ad opens, and the network's script tags stay outside so its checker still finds them" — [Playbaker ironSource](https://playbaker.com/networks/ironsource) [secondary].
  - Moloco requires assets to be "data-URI-compressed", which means data-URI-encoded, not compressed.
- Network wording on compression: none forbids runtime decompression. TikTok's limit is explicitly "after compression" (the ZIP). Unity requires minification. AppLovin names base64 and base122 as the allowed embeddings.
- Base122: about 14 % overhead vs 33 % for base64, allowed by AppLovin ([AppLovin guidelines](https://support.applovin.com/en/growth/promoting-your-apps/creatives/best-practices-and-guidelines)). It needs a UTF-8 page and a decoder. Other networks do not mention it, so use it only on the AppLovin profile.
- Feasibility arithmetic (extrapolation, not measured on a Godot playable): with a stripped wasm of ~13–16 MB, gzip ~3.4 MB → base64 ~4.5 MB, which barely fits AppLovin/Unity/Moloco 5 MB raw with nothing left for the PCK. Brotli ~2.4 MB → base64 ~3.2 MB, but this needs a brotli decoder in JS. xz/zstd land near brotli (official template: xz 6.65 MB vs gzip 10.05 MB, i.e. −34 %). On ZIP-counted networks the same payload costs ~compressed size, so 2.4–3.4 MB leaves 1.6–2.6 MB for PCK + JS. Meta single-HTML at 2 MB is out of reach unless the engine compresses below ~1.4 MB.

## Open points and suggested experiments

- Measure our stripped 4.7.2 nothreads template: raw, gzip -9, zstd -19 and brotli -11 sizes, plus decode and compile time on a low-end Android WebView.
- Build a single-file shell prototype covering: base64 → `DecompressionStream('gzip')` → `fetch` shim for `${base}.wasm`; PCK passed as `ArrayBuffer` to `preloadFile`; worklets as Blob URLs. Then run it through AppLovin Playable Preview, Meta Playable Preview (CSP report), Mindworks Test Tool and the Google HTML5 Validator.
- Check whether `ctx.audioWorklet` exists in ad webviews (secure context). If not, check whether Godot's unconditional position-worklet `addModule` breaks audio init and whether the `ScriptProcessor` fallback engages.
- Decide how to remove `XMLHttpRequest`, `window.open`, `eval` and IDBFS from the JS glue, using Emscripten settings, a custom JS library or post-processing. Moloco's checker rejects the `XMLHttpRequest` token.
- Verify whether Google's playable validator accepts non-listed file types (`.wasm`, `.pck`) in the ZIP, and whether TikTok's "no HTTP requests" permits fetching sibling files in its ZIP.
