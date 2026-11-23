# Playable ads in other engines and single-file packing techniques

Researched 2026-11-23. This note extends `../Web Builds Entscheidungsgrundlagen/playable_ads.md` and `minimal_engine_size.md` and does not repeat their findings (network limits, Defold, PlayCanvas, Luna, base64 measurements on Godot's wasm, `DecompressionStream` browser baseline). `[secondary]` marks third-party blogs, vendor marketing, community repos and forum posts. Search-engine summaries were cross-checked by fetching the page where possible; where only a summary was available, the finding says so.

## Cocos Creator: playable support, feature cropping, engine size, single-file packing

### Takeaway
Cocos Creator has **no built-in playable-ad export**. Playables come from third-party packers that post-process the `web-mobile` build. The packers run in the editor and are either Cocos Store extensions (super-html, AdsCraft, plbx) or npm/CLI tools (playable-adapter-core). The engine side is a JS/TS runtime. Cocos's own Feature Cropping panel plus property mangling bring it to roughly 1.7 MB raw for a 2D playable. Wasm appears only for optional native modules (Box2D, Bullet, PhysX, Spine). For those, the build can choose `Wasm`, `AsmJS` or both, and it has an "Enable Wasm Brotli compression" option. So Cocos is a JS engine with optional wasm add-ons, not a wasm engine. Its playables fit because the core is JS that minifies and gzips well.

### Cited Findings
- Feature Cropping is a Project Settings tab: "The unchecked modules in the list will be cropped out when packaging and previewing", "to achieve the effect of reducing the package size of the released version of the engine"; Cocos recommends a full test after cropping — [Cocos Creator 3.8 manual: Project Settings](https://docs.cocos.com/creator/3.8/manual/en/editor/project/index.html).
- Build options relevant to size (3.8 manual):
  - "Bundle Mode Of Native Code": Wasm + AsmJS (default), Wasm, AsmJS. It "mainly affects the native module packing format of Physics, Spine, etc."
  - "Enable Wasm Brotli compression" (default Off) "will reduce the size of the wasm package, which will take slightly longer to load due to the need to decompress it at runtime".
  - "Mangle Engine Internal Properties" and "Inline Enums" (both 3.8.6+) are "effectively reducing code size"; mangling does not work on native platforms.
  - Source: [Cocos 3.8 General Build Options](https://docs.cocos.com/creator/3.8/manual/en/editor/publish/build-options.html). Which brotli decoder Cocos ships for its wasm, and how large it is, was **not found**.
- 3.8.6 (release 2025-04-02) added cropping options for RichText, Mask, Graphics, UISkew and AffineTransform in 2D projects, plus a Spine-version selector in the trimming panel. The mangle option saves "160 KB" on a default 2D WeChat Mini Game project. Source: the [3.8.6 release post](https://www.cocos.com/en/post/f539c7888e620701228458d6b89b80c7) title and listing; the 160 KB figure and option list come from search-engine excerpts of the release notes, because the fetched page only rendered the listing.
- 3.8.3 fixed web builds downloading both the WASM and ASMJS files. 3.8.5 added lazy loading of the WASM modules for Box2D, Spine, Bullet and PhysX — [Cocos 3.8.3 community test thread](https://discuss.cocos2d-x.org/t/cocos-creator-v3-8-3-community-test-version/60697) and [Custom Loading of Wasm/Asm Files](https://docs.cocos.com/creator/3.8/manual/en/advanced-topics/wasm-asm-load.html). Both claims come from search excerpts; the pages themselves were not read.
- Measured engine size, one 2D playable [secondary]:
  - Project: Cocos Creator 3.8.8. Feature Cropping left only 2D, UI, Mask, Graphics, Particle 2D, Tween, Audio and Animation, which took "the engine from 2.5 MB down to 1.7 MB".
  - Build: Web Mobile with "Merge All JSON", no compressed textures, MD5 cache off, then a custom `build_playable.js`. The script embeds all build files, unpacks them with **fflate** inside the HTML, and serves them through an in-page shim.
  - Final AppLovin HTML ≈ 2.2 MB.
  - Source: [pangeve703/playable-ads](https://github.com/pangeve703/playable-ads).
- super-html (Cocos Store extension by "magician-f") [secondary]:
  - Packs a web build into one HTML. A ZIP-compression option compresses resources, and "smarter" threshold-based compression was planned.
  - Supports Unity, AppLovin, ironSource, Facebook and Mintegral. Video was added in v1.1.0 (2022-09-27).
  - Early versions rewrote script `src` setters, which broke on Creator ≥ 3.3 and was flagged by a Mintegral reviewer (2022-11-18).
  - Users report Facebook's checker scanning for `XMLHttpRequest`.
  - On a Creator 3.6.1 build with wasm physics that failed, the maintainer advised "switching to another physics engine" (2022-10-11), so wasm modules were a weak spot.
  - Source: [Cocos forum super-html thread, p. 4](https://forum.cocos.org/t/topic/134727?page=4) and [p. 2](https://forum.cocos.org/t/topic/134727?page=2).
- Cocos 3.x changed single-file packing because the engine loads modules through SystemJS. Older 2.x single-HTML tools stopped working from 3.0 — [Cocos forum 111354](https://forum.cocos.org/t/topic/111354) [secondary, search excerpt].
- playable-adapter-core / cocos-pnp (npm) [secondary]:
  - Supports Creator ≥ 2.4.6 and ≥ 3.8.x and 11 networks: AppLovin, Facebook, Google, ironSource, Liftoff, Mintegral, Moloco, Pangle, Rubeex, TikTok, Unity.
  - Options: `isZip` (pako compression, default true) and TinyPNG compression with an API key. It "removes `XMLHttpRequest`" from the single HTML.
  - Since v1.0.0 it uses `URL.createObjectURL` (Blob URLs) instead of patching `System.__proto__.createScript`, to match the SystemJS in Creator 3.7. Builds opened from `file://` can fail because of object-URL restrictions.
  - Source: [playable-adapter-core README 1.2.4](https://cdn.jsdelivr.net/npm/playable-adapter-core@1.2.4/README.md).
- A Cocos 3.x 3D packer registers a WASM downloader for Bullet physics (already in the background note). Other commercial converters exist (AdsCraft, plbx, smartad.pro), but smartad.pro refused the connection.

### Inferences
- The Cocos pattern most relevant to Godot is the loader shim, not the size: decompress one archive (fflate/pako) in the HTML, then hand the engine Blob URLs or patched downloaders, so the engine's normal file loading keeps working.
- Cocos keeps wasm optional per module and offers asm.js as a fallback. That only works because the core is JS. Godot has no such split, because the whole engine is the wasm.
- A cropped Cocos 2D engine (~1.7 MB raw JS, which typically gzips to a few hundred KB) is about an order of magnitude below the stripped Godot wasm (17.7 MB raw / 5.2 MB gzip).

### Gaps
- No official Cocos number for a minimal `web-mobile` engine size, raw or gzip. The 2.5 → 1.7 MB figure is one project's self-report.
- The decoder that "Enable Wasm Brotli compression" ships, and its size, were not found.
- super-html's exact encoding (base64 of a ZIP? pako? JSZip?) is not documented on the pages read.

## Needle Engine: `playableAds` build profiles, inlining, CSP, adapters

### Takeaway
Needle (three.js + Vite) is the most complete **integrated** playable pipeline: a build profile per network, single-file output, a compliance report and a size gate. Its public reference documents the options, not the internals. Single HTML and strict resource encoding are on by default, there is a 5,000,000-byte gate, and URL literals and remote features are stripped. Its Meta profile switches embedded files from data URLs to Blob URLs because of Meta's CSP. The bridge exposes `open()`/`openStore()`, mapped per network. How it compresses or inlines wasm decoders (Draco, KTX2) is not documented.

### Cited Findings
- Shared options:
  - `singleHtml` (default on), `strictResourceEncoding` (default `true`), `makeFilesLocal` (on, with playable exclusions).
  - `stripRemoteRuntimeFeatures` (default `true`), `excludeOptionalModules` (default `[]`).
  - Profile-specific `failOnExternalUrls`, `stripExternalUrlLiterals`, `disallowWindowTop`.
  - `maxBytes` default `5_000_000`.
  - Source: [Needle reference: Playable Ad Build Profiles, last updated 2026-08-31](https://engine.needle.tools/docs/reference/playable-ads.html) [secondary: vendor docs].
- The compliance report lists "output path, upload size, HTML size, and limit", SHA-256 hashes of output and source build, external URLs, embedded files and bytes by MIME type, and "Base64 encoded, decoded, and expansion bytes". The Meta profile "rejects browser popups and `XMLHttpRequest`" and files above 5 MB — same source.
- The build first compresses "meshes, textures, scripts, and scene data", then packages and size-checks. It "removes offline-incompatible components. Examples are networking and WebXR components", and the build log lists each removed component.
- Outputs per profile: `dist/AppLovin/index.html`, `dist/UnityAds/index.html`, `dist/TikTok/playable.zip`, `dist/GoogleAds/playable.zip`, `dist/Meta/playable.zip`, `dist/Mintegral/MyGame.zip`, plus a WeChat mini-game folder.
- `openStore()` mapping: AppLovin and Unity → `mraid.open()`, TikTok → Playable SDK, Google → `ExitApi.exit()`, Meta → `FbPlayableAd.onCTAClick()`, Mintegral → `window.install()`. Only Mintegral uses the ready/end/retry notifications.
- Source for the last two bullets: [Needle: Build Playable Ads](https://engine.needle.tools/docs/how-to-guides/deployment/playable-ads.html) [secondary].
- Meta profile: the output is a ZIP with one self-contained `index.html`. Troubleshooting "CSP blocks a data URL → rebuild the Meta profile; the profile uses Blob URLs for embedded game files" — [Needle: Meta playable](https://engine.needle.tools/docs/how-to-guides/deployment/playable-ads/meta) [secondary].
- AppLovin profile checks "Resource encoding: Base64 or Base122" — [Needle: AppLovin](https://engine.needle.tools/docs/how-to-guides/deployment/playable-ads/applovin) [secondary, search excerpt].
- Related three.js evidence on wasm decoders in playables:
  - Inlining `draco_decoder.wasm` as base64 gave 404s, and the fix was Blob URLs via a `LoadingManager` URL modifier — [three.js forum](https://discourse.threejs.org/t/getting-error-not-found-when-using-base64-draco-decoder-wasm/72762) [secondary].
  - "GLTFLoader is not working on Facebook playable ad campaigns" — [three.js forum](https://discourse.threejs.org/t/gltfloader-is-not-working-on-facebook-playable-ad-campaigns/78073) [secondary, title only].
  - Needle builds once tried to fetch `draco_decoder.js` from the web — [Needle forum](https://forum.needle.tools/t/build-is-trying-to-fetch-draco-decoder-js-from-the-web/1425) [secondary].
  - Babylon.js KTX2 transcoding broke with an `EvalError` once `unsafe-eval` was removed — [Babylon forum](https://forum.babylonjs.com/t/csp-violation-during-ktx2-decoder-load/47937) [secondary].
  - PlayCanvas advises avoiding `.ktx2` (Basis) under strict CSP because it needs a wasm transcoder — [PlayCanvas forum: Compile Error (unsafe-eval)](https://forum.playcanvas.com/t/compile-error-unsafe-eval/40858) [secondary].

### Inferences
- Needle's report fields ("encoded/decoded/expansion bytes", hashes, external URL scan) are a good template for a rules_godot playable target's output report.
- Needle's per-network output paths match the "one target per network" design noted in the background.
- The Meta Blob-URL switch, plus the three.js and Babylon decoder failures, mean that even small wasm side-modules in JS engines run into CSP. A Godot playable, which is all wasm, depends entirely on the network's CSP allowing `wasm-unsafe-eval` (or `unsafe-eval`).

### Gaps
- Needle does not document whether it compresses the payload inside the HTML (gzip/brotli + decoder) or only base64-encodes, nor typical output sizes.
- Meta's actual CSP header for playables is still unpublished. Meta's [games CSP page](https://developers.facebook.com/documentation/games/build/content-security-policy) covers Instant Games hosting, not ads.

## Phaser / PixiJS / three.js / Babylon tooling and generic packers

### Takeaway
For JS engines the tooling is generic. A webpack or Vite build tree-shakes the engine, inlines assets as base64, injects a network adapter (MRAID / DAPI / FbPlayableAd / Mintegral / TikTok) and writes one artifact per network. Engine size is a non-issue: Phaser custom builds are ~70–110 KB gzip, PixiJS is about 0.5 MB raw. The tools spend their effort on adapters and asset compression, not on engine code. None of them handles a multi-megabyte wasm.

### Cited Findings
- `@smoud/playable-scripts` [secondary]:
  - MIT license, webpack-based, engine-agnostic with Pixi, Three.js and Phaser templates.
  - 28 ad networks plus preview. Protocols `none`, `mraid`, `dapi`. Optional `--zip`, `--vungle-legacy` (ES5). Console calls are dropped in production.
  - The README does not describe size checks or wasm handling.
  - Source: [smoudjs/playable-scripts](https://github.com/smoudjs/playable-scripts).
- Phaser custom builds:
  - "303 KB minified (about 78 KB gzipped)" with Loader and a few Game Objects — [Phaser Dev Log 170](https://phaser.io/devlogs/170).
  - "274KB minified, dropping to 71KB with gzip" — [Phaser newsletter 127](https://editor.phaser.io/newsletter/issue-127).
  - Phaser Compressor (May 2024) "can save over 60%", giving bundles "well below 150 KB (min+gz)" — [Phaser news 2024-05](https://phaser.io/news/2024/05/phaser-compressor-released).
  - The figures above come from search-engine excerpts of the pages.
- Phaser playable webpack template — [vardanyanlg/phaser3-webpack-playable](https://github.com/vardanyanlg/phaser3-webpack-playable) [secondary, not read].
- PixiJS 630 KB single-HTML measurement — already in the background note ([zednaked/playable-budget](https://github.com/zednaked/playable-budget)).
- Construct 3 users discuss the same constraints ([Construct forum: the size of playable ad](https://construct.net/en/forum/construct-3/general-discussion-7/size-playable-ad-164189) [secondary, not read]).
- Playbaker (playbaker.com) returned HTTP 521 during this research. Its "self-extracting HTML" claim is in the background note. "Playable Factory" turned up no primary source.

### Inferences
- The only design ideas worth borrowing from JS-engine tooling are the adapter matrix and the per-network output naming. Their packers assume a small engine and base64-inline assets without compression.
- The packers that do compress (Cocos fflate/pako, Playbaker gzip, PlayCanvas `compress_engine`, Defold zstd) are the ones whose engine is big relative to the budget.

### Gaps
- No primary source for Babylon.js playable tooling. Babylon appears only through CSP/KTX2 forum threads.
- "Playable Factory" could not be identified.

## Packing techniques compared: encodings, decoders, wasm instantiation, CSP

### Takeaway
There are three encoding choices: base64 (+33 %, universally accepted), base122 (about +14 %, AppLovin only), and Emscripten 4.0.19+'s new UTF-8 binary embedding in `SINGLE_FILE` mode, now the default. All three should wrap an already compressed payload. The decoder cost by format:

| Format | Decoder | Cost |
| --- | --- | --- |
| gzip / deflate | native `DecompressionStream` | 0 KB (fallback: fflate inflate ~3–4 KB min) |
| zstd | fzstd | 8 KB min / 3.8 KB gzip |
| brotli | pure-JS decoder (122 KB static dictionary dominates) | ~150 KB min, ~66 KB with the dictionary compressed |
| brotli | brotli-dec-wasm | ~200–300 KB |

So zstd gives brotli-class ratios for a ~4 KB decoder, and it is the format Defold chose. Wasm must be instantiated from bytes (`WebAssembly.instantiate(ArrayBuffer)`). Worklets and workers need Blob URLs, and Blob URLs are also the documented Meta-CSP workaround.

### Cited Findings
- Emscripten `SINGLE_FILE`:
  - "embeds all subresources (for example, the Wasm file) as strings in the generated JavaScript or HTML file".
  - "your Content Security Policy may need to be updated … using a Worker requires the child-src directive to allow blob:".
  - `SINGLE_FILE_BINARY_ENCODE` (default true): "binary Wasm content is encoded using a custom UTF-8 embedding instead of base64. This generates a smaller binary that compresses well". It requires UTF-8 serving and "will not work with the default legacy Windows-1252 encoding". Fallback: `-sSINGLE_FILE_BINARY_ENCODE=0`.
  - Source: [Emscripten settings reference (7.0.2-git)](https://emscripten.org/docs/tools_reference/settings_reference.html).
  - The binary encoding arrived in **Emscripten 4.0.19** (ChangeLog, 2025-11-04, PR #25599) — [Emscripten ChangeLog](https://chromium.googlesource.com/external/github.com/emscripten-core/emscripten/+/refs/heads/main/ChangeLog.md) and the [emscripten-discuss announcement](https://groups.google.com/g/emscripten-discuss/c/E_HmYqXGjN8). This comes from search excerpts; the exact overhead percentage was not stated.
  - Note: Godot 4.7.2 builds with emsdk 4.0.20 (background note), so this encoding is available to a Godot build. It embeds the *raw* wasm, though, not a compressed one.
- `MINIMAL_RUNTIME` "uses minimal sized runtime without POSIX features … to target the smallest code size possible", and `MINIMAL_RUNTIME=2` goes further. The docs call these opts "quite hacky" and say they "may not work in all generated programs" — same Emscripten page. `DYNAMIC_EXECUTION=0` removes `eval()`/`new Function()` from the glue — same page.
- Base122 (Kevin Albertson):
  - "~14% smaller than equivalent base-64". The example is a 1,429 B JPEG → 1,908 B base64 vs 1,635 B base122.
  - The minified browser decoder `decode.min.js` is 469 bytes.
  - The author says it is "not recommended for web pages": base64 gzips better and decoding carries a performance penalty. The web decoder is a proof of concept and the format is "experimental".
  - Source: [kevinAlbs/Base122](https://github.com/kevinAlbs/Base122).
  - AppLovin is the only network that names it (background note; Segwise 2026 also says "No other network on this list mentions it" — [Segwise specs 2026](https://segwise.ai/blog/playable-ad-specs-by-network-2026) [secondary]).
- fflate:
  - "8kB (3kB for inflate only)" minified vs pako 45.6 kB; GZIP/Zlib decompression estimate 4 kB, pako "11.4x larger".
  - Decompression "Up to 25% faster" than pako and about 30 % slower than native zlib.
  - The native Compression Streams API "usually performs between 30% faster and 10% slower than fflate" for large streams, and `CompressionStream` has "surprisingly poor performance on data already loaded into memory".
  - Source: [101arrowz/fflate](https://github.com/101arrowz/fflate).
- fzstd:
  - "8kB minified and 3.8kB after gzipping". WASM zstd ports are "about 30-40% faster". It streams, while most WASM ports do not and "allocate large amounts of memory that can't be freed".
  - Files at ultra levels (20+) that decompress to over 32 MB may fail. The README's "225 bytes" backreference limit reads as a typo for 2^25.
  - Source: [101arrowz/fzstd](https://github.com/101arrowz/fzstd).
- Brotli decoders:
  - Google's JS `decode.min.js` is about 151 KB in hosted copies. The 122 KB static dictionary is the bulk of it ("brotli brings a >100KB dictionary with it").
  - brotli-lib compresses the dictionary to 52 KB, for a 66 KB decode-only bundle.
  - `brotli-compress` lists a JS-only decompressor at 152 K and a WASM variant at 1.8 MiB. `brotli-dec-wasm` advertises "about 300KB 200KB".
  - Sources: [brotli Google Group](https://groups.google.com/g/brotli/c/Y28CS-a7QHo), [countertype/brotli-lib](https://awesome.ecosyste.ms/projects/github.com%2Fcountertype%2Fbrotli-lib), [brotli-compress](https://www.npmjs.com/package/brotli-compress), [brotli-dec-wasm](https://npmjs.com/package/brotli-dec-wasm). All from search excerpts [secondary].
- `DecompressionStream` in WebViews: MDN lists Android WebView 80 for the constructor. Base64 must be decoded first. MDN's example uses `Uint8Array.fromBase64`, which is much newer, so ad shells should decode manually or use `fetch('data:…')`, the latter subject to `connect-src` — [MDN DecompressionStream](https://developer.mozilla.org/en-US/docs/Web/API/DecompressionStream).
- CSP and wasm:
  - Compiling or instantiating wasm counts as eval. `'wasm-unsafe-eval'` in `script-src` enables it without JS eval.
  - Emscripten/asm.js fallbacks that use `new Function` break as well when `unsafe-eval` is disallowed.
  - Source: [PlayCanvas forum: Compile Error (unsafe-eval)](https://forum.playcanvas.com/t/compile-error-unsafe-eval/40858) [secondary, citing MDN].
  - Safari has reported the error even with the directive present — [Apple forums 764426](https://developer.apple.com/forums/thread/764426) [secondary, search excerpt].
- Engine loaders patched for single-file prior art:
  - Cocos playable-adapter-core switched from patching SystemJS `createScript` to `URL.createObjectURL` (see Cocos section).
  - pangeve703's Cocos build serves fflate-unzipped files through an in-page shim.
  - Defold's loader change to `script.src = src` (2025-07) broke the playable Gulp script until it was patched ([Defold forum p. 3](https://forum.defold.com/t/defold-for-playable-ads/68689?page=3) [secondary]).
  - Fragility point: every upstream loader change breaks the shim.

### Inferences
- For a Godot playable the cheapest strong option is likely **zstd -19/--ultra + fzstd (≈4 KB gzip)**, close to brotli/xz ratios. Brotli via JS costs 66–150 KB, which wipes out much of brotli's edge over zstd. Gzip via `DecompressionStream` is free but about 1.5 MB worse on the engine (5.2 vs ~3.6 MB, background measurement).
- Emscripten's new UTF-8 `SINGLE_FILE` embedding is attractive for raw-HTML-counted networks, but it embeds uncompressed wasm. For a 17.7 MB engine it cannot beat "compressed payload + small decoder". It also depends on the webview treating the creative as UTF-8, which Unity's minified-HTML rule and the networks' re-serving do not guarantee. The same UTF-8 trick could carry a zstd payload, but that would need a custom decoder. Measuring its overhead on high-entropy (compressed) data is open.
- Base122 only helps on AppLovin and costs some decode time. Its 469 B decoder is negligible.
- For Meta, use Blob URLs instead of `data:` URLs for anything that needs a URL (worklets, workers, scripts). Wasm bytes go straight into `WebAssembly.instantiate`, which still needs a CSP that allows wasm compilation.

### Gaps
- No measured comparison of fzstd vs `DecompressionStream` vs brotli-JS **decode time** for a ~17 MB wasm on low-end Android.
- The lz4 decoder size and ratio were not researched (lz4 ratios are far worse than gzip for wasm).
- The overhead of Emscripten's UTF-8 binary embedding on random/compressed bytes was not found.
- No ad network publishes whether its webview supports `wasm-unsafe-eval`, `DecompressionStream`, or `AudioWorklet` (secure context).

## Wasm-heavy engines in playables (Unity WebGL non-Luna, Unreal, Bevy, raylib, Godot)

### Takeaway
I found **no documented production playable** built with Unity WebGL (non-Luna), Unreal, Bevy, raylib or Godot. Defold remains the only wasm-engine playable pipeline with public network acceptance (background note).

- **Unity WebGL**: an empty minimum-size build is about 2.7–3.3 MB (Built-in RP) or 4.5–6.8 MB (URP), compression not stated. Real 2D playables land around 13 MB, Unity has no single-file output, and Unity itself steers users to Luna/Playworks.
- **Unreal**: dropped HTML5 in 4.24 and never brought it back in UE5.
- **Bevy**: about 12–13 MB raw / 3.9 MB compressed for small games (2023 numbers).
- **raylib**: small enough in principle, but nobody documents a raylib playable.
- **Godot**: no community playable tooling exists. Size reports for stripped web templates match ours (~2–4 MB brotli).

### Cited Findings
- Unity WebGL minimum-size builds:
  - Built-in RP: 2.64 MB (2021.3) to 3.29 MB (6000.6.0f1). URP: 4.48–6.76 MB.
  - Settings: code optimization Size, exceptions None, IL2CPP Master. The page does not say which compression the totals use; the server is set up for Brotli.
  - Source: [JohannesDeml/UnityWebGL-LoadingTest](https://www.github.com/JohannesDeml/UnityWebGL-LoadingTest) [secondary].
- Unity WebGL playable attempt (2025-11-03):
  - A 2D UI-only Unity 6.2 playable built at about 13 MB with Brotli, engine stripping and no audio. Google Ads recommends ≤ 5 MB.
  - A reply (2025-11-04): "it took some serious pulling to get below 5 MB even without any content in the project". Advice: High managed stripping, which "may crash", removing logo and splash, and reducing texture quality.
  - Nobody reports a shipped Unity WebGL playable.
  - Source: [Unity Discussions 1693502](https://discussions.unity.com/t/how-can-i-reduce-my-unity-webgl-playable-ad-build-from-13-mb-to-under-5-mb-for-google-ads/1693502) [secondary].
- Unity single-file: "Unity Editor/Engine itself doesn't support producing single-file builds". The single-file example discussed there was made with Unity Playworks — [Unity Discussions 1584163](https://discussions.unity.com/t/how-to-build-webgl-to-a-single-html-file/1584163) [secondary, search excerpt]. Luna notes "none of the playable platforms … validate build sizes taking [compression] into account" — [Luna: optimise your builds](https://docs.lunalabs.io/docs/playable/optimise-your-builds/overview) [search excerpt].
- Unreal: since 4.24, HTML5 "was migrated out of the engine to a public Platform Extension", maintained by the community. UE5 never got an HTML5 target. Community forks target 4.24/4.27 with Emscripten 3.1.2 — [Unreal forums: HTML5 not in 4.26](https://forums.unrealengine.com/t/html5-not-in-4-26/477510), [ufna/UE-HTML5](https://www.github.com/ufna/UE-HTML5) [secondary]. No size data found. Not a candidate.
- Bevy:
  - A 2023 maintainer comment reports an unoptimized-build fix giving 13 MB raw / 3.9 MB compressed. Size-focused settings (`opt-level="z"`, LTO, `wasm-opt`) can bring it to "12MB or less".
  - A small Bevy game reports 7.7 MB raw / 2.0 MB gzip.
  - `wasm-opt -Oz` halved one build from ~30 to 15 MB.
  - Source: [r/rust Bevy WebGPU thread, 2023-05-18](https://axebps-redlib.hf.space/r/rust/comments/13lb0h8/bevy_webgpu/jkpa8mx/?context=3) and [Bevy cheatbook (0.12, outdated)](https://bevy-cheatbook.github.io/platforms/wasm/size-opt.html). All [secondary, search excerpts]. No Bevy playable found.
- raylib: needs `USE_GLFW=3` and often `ASYNCIFY`, which grows the binary — [Wavedash raylib docs](https://docs.wavedash.com/engines/raylib) [secondary, search excerpt]. No measured raylib playable or single-file size found.
- Godot community size reports (beyond the background note):
  - JohannesDeml's Godot loading test lists release WebGL2 builds of 5.34 MB (4.3.0), 6.14 MB (4.4.1), 6.22 MB (4.5.2) and 6.33 MB (4.6.2), and calls 4.3 → 4.4 a +0.8 MB (≈15 %) jump. The page does not say whether these are compressed; the repo uses Brotli/Gzip precompression and `wasm-opt`. No custom templates were used — [JohannesDeml/Godot-Web-LoadingTest](https://github.com/JohannesDeml/Godot-Web-LoadingTest) [secondary].
  - An older Godot issue reports a heavily stripped custom template at a 9.75 MB wasm → ~2.1 MB brotli, ~1.8 MB 7z/LZMA2 — [godotengine/godot#20996](https://github.com/godotengine/godot/issues/20996) [secondary, search excerpt; version not stated, likely 3.x].
  - A Godot forum write-up on minifying builds (93 MB → 6.4 MB Windows exe) says the web build size "seems to be mostly unchanged after the 4.5 update" — [Godot forum 104965](https://forum.godotengine.org/t/how-to-minify-godots-build-size-93mb-6-4mb-exe/104965) [secondary, search excerpt].
  - Google's YouTube Playables Godot wrapper addresses size only through lazy-loaded `.pck` packs, noting the certification team "may waive the overall file size restrictions if this is properly done" — [YouTube Playables Godot wrapper](https://developers.google.com/youtube/gaming/playables/samples/godot_wrapper). YouTube Playables is not an ad format.
  - Searches (GitHub, Reddit, Godot forum) found no Godot playable-ad tool, template or production report as of 2026-11-23. [zednaked/playable-budget](https://github.com/zednaked/playable-budget) still states that no stripped Godot template was built.

### Inferences
- The market answer for wasm engines is "don't". Unity built Luna, a separate JS runtime, instead of shrinking WebGL builds. Unreal left the web. Only Defold, whose engine is designed small (<1 MB compressed), ships wasm playables.
- A stripped Godot engine (3.6 MB brotli, ~3.5 MB zstd expected) is in the same class as an empty Unity Built-in-RP build (~3 MB) and a small Bevy game (2–4 MB). Those are exactly the engines nobody ships as playables. So a Godot playable would be a first, and it competes against a 5 MB budget with ~1–1.5 MB left for game content. That budget only works on ZIP-counted networks or with a compressed payload plus a small decoder.
- Godot's levers beyond the background note are a class-level `build_profile`, Emscripten `DYNAMIC_EXECUTION=0` and glue trimming for CSP and token scans, and `wasm-opt`/Closure. Godot's web build already uses `-Oz`/LTO, so `wasm-opt` adds little after that (the background note shows `-Oz` cuts raw size, not compressed size). Nobody has published the combination.

### Gaps
- No size data for a Unity WebGL build specifically configured for playables (stripping High, no splash, Built-in RP) packed into one HTML.
- No raylib/Emscripten single-file playable measurements, and no current (2025–2026) Bevy minimum wasm size.
- No Godot community thread specifically about playable ads besides the 2024 Calinou answer in the background note. Reddit was not directly reachable through search.
