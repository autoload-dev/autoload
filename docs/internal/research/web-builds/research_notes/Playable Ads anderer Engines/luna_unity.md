# Luna / Unity Playworks: how Unity playable ads are built

Researched 2026-11-23. Primary sources are Luna's own docs (docs.lunalabs.io, now titled "Unity Playworks - Developer Docs", footer "© 2026 Unity Technologies"), its release notes and Unity's own pages. Most doc pages carry no date. The release notes do, so dated facts come from there. `[secondary]` marks third-party pages. Luna's Medium tech blog (`medium.com/luna-labs-ltd`) returned HTTP 403, and fetching it another way was refused. Statements only seen in search snippets are marked `[snippet]`.

Naming: the product was "Luna" / "Luna Playable". The plugin is now the "Playworks Plugin" and the web platform is "Unity Playworks" (playworks.unity.com, formerly playground.lunalabs.io). Release 6.1.0 (2024-09-03) lists "Luna renaming". API names such as `LunaPlaygroundField` remain.

## 1. Runtime: own JS engine with C# transpiled via Bridge.NET, not Unity's WebGL player

### Takeaway
Luna does not use Unity's WebGL/wasm player or the Unity build pipeline at all. The plugin exports the scene and asset data from the Unity Editor. It transpiles the project's C# scripts to JavaScript with Bridge.NET, plus Luna's own syntax-downgrading front end. Both run on Luna's own "Playable Game Engine", an HTML5/WebGL reimplementation of the Unity runtime API. That engine covers rendering, Mecanim animation, particles, 3D and 2D physics (its own engines; 2D physics in WASM since 2023), audio and UI. Its size is "~650kb compressed", roughly a fifth of our stripped Godot engine at 3.6 MB brotli.

### Cited Findings
- "Playworks Plugin does not interact with the build target pipeline of Unity, nor does it use the Unity Tiny package." — [Playworks FAQ](https://docs.lunalabs.io/docs/playable/faq/)
- "In order to convert the source code of a Unity project, Unity Playworks Plugin uses C# to JavaScript transpiling … The output of this process is then run on the Unity Playworks Plugin game engine in the final build." — [Prepare your code: overview](https://docs.lunalabs.io/docs/playable/code/overview/)
- "Unity Playworks Plugin uses Bridge.NET to compile C# code into JavaScript."
  - A "Syntax Transformer" rewrites newer syntax into "an older version of C# that is supported by Bridge.NET". "The transformed sources are then compiled into JavaScript using Bridge.NET."
  - With it, C# 7.x, parts of 8.0 (`??=`, readonly members, using declarations, static local functions) and parts of 9.0 (target-typed `new`, lambda discards) work.
  - Records, init-only setters, indices/ranges, async streams, function pointers and top-level statements remain unsupported.
  - Source: [Unity C# Features / Syntax Transformer](https://docs.lunalabs.io/docs/playable/code/syntax-transformer)
- "Playable Compiler V2 … compiles C# 9.0 / 8.0 and downgrades the C# version of code" (opt-in checkbox) — [Advanced settings](https://docs.lunalabs.io/docs/playable/playable-setup/settings/advanced-settings)
- Luna uses a modified Bridge.NET; the release notes record Bridge changes:
  - "Updated version of `Bridge.NET` library" (0.4.0, 2020-01-15).
  - "Errors in coroutines should not break flow" (0.4.2, 2020-01-29).
  - "Optimisation of Bridge that allows passing structs as a reference, evading allocation" (0.8.4, 2020-09-16).
  - "Newtonsoft.JSON (Bridge.NET variant) is now included automatically" (0.2.0, 2019-11-22).
  - Source: [Release notes](https://docs.lunalabs.io/docs/playable/release-notes)
  - A Luna Medium post describes "a modified version of Bridge.NET" `[snippet]` — [Luna Tech Series: 5 Challenges of Writing in C# for a JavaScript Engine](https://medium.com/luna-labs-ltd/luna-tech-series-5-challenges-of-writing-in-c-for-a-javascript-engine-b8817f187150) (not readable, HTTP 403).
- Engine footprint: "The Playworks Plugin engine is ~650kb compressed", and this "can be decreased dramatically using Runtime Analysis code stripping." Graphics: "uses `WebGL1.0` as graphics library by default", WebGL 2 supported from 6.0.0; "Starting with Unity 6, only WebGL 2 is supported." — [FAQ](https://docs.lunalabs.io/docs/playable/faq/)
- "Your project will then be converted and run on the Playworks Playable Game Engine in your browser." It supports "rendering features, animations, particle systems, physics simulations and more". Device aim: "all devices, including the lowest-end ones (Android 4.0, iOS 9)" — [What is Playworks Plugin](https://docs.lunalabs.io/docs/playable/overview)
- Reimplemented subsystems, as evidenced by the release notes ([Release notes](https://docs.lunalabs.io/docs/playable/release-notes)):
  - 3D physics is Luna's own engine:
    - "Our 3D physics engine is now built using Google's closure compiler" (0.2.0, 2019-11-22).
    - "Support for Continuous Collision Detection in Physics engine!" (0.3.0, 2019-12-06).
    - "Support for body sleeping in 3D Physics" (0.3.1).
    - "Align joint's math with PhysX" (0.6.2, 2020-04-01).
    - "Physics engine minification to reduce … Engine footprint" (0.6.0).
  - 2D physics: "Physics2D shapecasts implemented" (0.6.0); "Platform effector 2D implementation" (1.0.1); "Implemented Physics2D WASM" (5.0.0, 2023-04-12).
  - Animation: "Half-precision floats for animation clips" (0.1.1); "Animator AnyState transitions" fix (0.7.0); "Animating material parameters" (0.8.1).
  - Particles: "Added a set of particle system API methods and properties" (0.4.0); "`ParticleSystem` memory allocation rework" (0.7.2).
  - Rendering:
    - "WebGL2 basic implementation" (5.3.0, 2023-10-04).
    - Linear color space "Only available for WebGL2" (6.0.0, 2024-06-17).
    - "WebGL1/2 shaders runtime switch support" (6.2.0, 2024-11-05).
    - SSAO and URP Render Objects (7.1.0, 2026-02-16).
    - Shader export time reduced "by up to 10%" (7.2.0, 2026-04-27).
  - Audio: `AudioSource` fixes and pooled audio sources (0.7–0.8).
- Unsupported, per [Supported Features / Limitations](https://docs.lunalabs.io/docs/playable/getting-started/limitations/):
  - HDRP ("no short term plans"); URP and Built-in are supported.
  - "DLLs are currently unsupported"; C++ plugins unsupported.
  - "NavMesh is currently unsupported" (on the roadmap).
  - Legacy Unity GUI (IMGUI); DOTS/ECS; ads and analytics SDKs.
  - "Shaders marked with Compiled code: none (Precompiled shaders)".
  - WebGL uniform locations / uniform buffers.
  - Destructors, `goto`, circular interface inheritance.
- 2D physics is weaker than 3D: the troubleshooting advice is to "use 3D physics counterparts for components and method call" `[snippet]` — [2D physics components](https://docs.lunalabs.io/docs/playable/common-issues/physics/2d-physics-components)
- Threads: Async/Await works "without multithreading due to limitations of the web platform" — [FAQ](https://docs.lunalabs.io/docs/playable/faq/)
- Supported Unity versions: "from 2021.3 up to 6000.0 inclusively" ([FAQ](https://docs.lunalabs.io/docs/playable/faq/)). 7.0.0 (2025-11-06) added "Unity 6 support" and 7.2.0 (2026-04-27) "Removed Unity 2020.3 support" ([Release notes](https://docs.lunalabs.io/docs/playable/release-notes)).
- **Conflict**: Unity's own marketing guide calls the builds "WebGL playables" and recommends Unity's managed stripping (High). That sits badly with the FAQ, which says the plugin does not touch Unity's build-target pipeline. Read "WebGL" there as "runs on WebGL", not "Unity WebGL player". Stripping is discussed in §2. — [Unity: How to create playable ads, dated 2026-09-30](https://unity.com/resources/how-to-create-playable-ads)

### Inferences
- Luna is a second implementation of the Unity runtime API in JS, fed with data the Editor exports: scenes, prefabs, meshes, animation clips and shaders. User code comes in as transpiled C#. Unity's real engine C++ never reaches the browser. This is why Luna's runtime fits in about 650 KB compressed. It also explains the long tail of unsupported features: every Unity feature had to be re-implemented, which took Luna years of releases from 2019 to 2026.
- Shaders are exported from Unity and converted for WebGL 1/2 (precompiled shaders are unsupported and the release notes speak of "shader export"). The exact conversion path, for example HLSL→GLSL cross-compilation in the Editor, is not documented on the pages read.
- Luna does use wasm selectively: 2D physics since 5.0.0 and a wasm brotli decoder since 6.x (§3). Luna is therefore "JS engine plus small wasm kernels where they pay off", not pure JS.

### Gaps
- Whether the engine core is written in TypeScript/JS, or in C# transpiled together with the user code, is not stated on any page read. The Medium tech-series article that probably answers it was not readable.
- Whether the 3D physics engine is a fork of an existing JS engine (cannon.js, ammo.js, Oimo) or written from scratch is not stated. "Built using Google's closure compiler" suggests JS sources.
- No uncompressed engine size, no per-module size table, and no date for the "~650kb compressed" figure.
- No page explicitly covers UI (uGUI) or TextMeshPro support. Font atlas options (§2) imply text rendering is reimplemented.

## 2. Size minimisation: stripping, asset processing, compression

### Takeaway
Luna reduces size on three levels.
- **Engine and user code:** dead-code elimination, a "Runtime Analysis" that instruments a dev build and strips classes and methods never hit (~30 % less code), module switches (Physics 3D/2D, particles, reflection, prefab, Mecanim) and minification.
- **Shaders:** the same runtime recording strips unused shader variants.
- **Assets:** an Editor-side pipeline with a 512 px texture cap, PNGQuant or JPEG, mono audio at a set bitrate and max duration, half-precision meshes and animations, mesh simplification, font-atlas alphabets and particle baking.

The packaged resources are then brotli-compressed ("Compress resources") and embedded as base122. Unity targets 2–5 MB per playable.

### Cited Findings
- The "Optimise Build Size" button sets these values — [Set Optimal Settings](https://docs.lunalabs.io/docs/playable/playable-setup/settings/set-optimal-settings/):
  - Textures: max 512 × 512, default format PNG32, compression "PNGQuant small size", JPEG quality 65.
  - Sounds: "mono", bitrate 128, "Sounds default duration" 30.
  - Meshes and animations stored in half-precision floats.
  - "Code minification" enabled; "Compress resources" enabled; "Force disable Anti Aliasing" enabled.
- Asset options — [Optimising Assets](https://docs.lunalabs.io/docs/playable/optimise-your-builds/optimising-assets/overview):
  - Per-folder or per-file texture max size; switching PNG to JPEG.
  - Audio bitrate ("Bitrate 0 k means max size") and mono.
  - Half precision cuts mesh and animation data by "about 50%".
  - Custom font alphabets: "Control which characters get rasterized into an atlas".
  - Baking particle systems into sprite animations.
  - Pruning shader variants.
- Further size work in the release notes ([Release notes](https://docs.lunalabs.io/docs/playable/release-notes)):
  - 7.0.0 (2025-11-06) added a "Mesh Simplification Tool".
  - "Revised PNG compression tools" (0.8.0, 2020).
  - "Remove name from component DTO (removes unused data from serialized build)" (0.4.2).
- Code stripping:
  - "Preview version of Dead Code Elimination" (0.3.0, 2019-12-06).
  - "Runtime Analysis - A tool that detects unused classes / modules in runtime and excludes them" (2.6.0, 2021-10-20).
  - "continuous Runtime Analysis for develop mode" (3.1.0, 2022-02-14).
  - "Remove all legacy and unused code from engine" (1.3.0, 2021-02-09).
  - Source: [Release notes](https://docs.lunalabs.io/docs/playable/release-notes)
- How Runtime Analysis works — [Runtime Analysis](https://docs.lunalabs.io/docs/playable/optimise-your-builds/runtime-analysis):
  - "we detect all c# classes, their methods and properties. We mark each of them as "unused" and place a hook inside." Every hook that fires during develop-build play marks its item as used.
  - It covers engine code as well as user code. Shaders go through the same process, with results in a "Plugin Shader Variant Collection".
  - Reported saving: "~30%" of playable code across tested projects. Disabling unused modules (Physics 3D/2D, Particle System, Reflection, Prefab, Mecanim) saves more, with no figure given.
  - Risks: code missed in the playthrough gets stripped, so developers must play every interaction. "Disable Code Stripping" and "Disable Shader Stripping" are escape hatches.
- A size breakdown "grouped by asset type" is shown in the plugin UI, including "Required JavaScript" (decompression routines, platform SDKs) and "Other" (plugin scripts and HTML) — [Size Breakdown](https://docs.lunalabs.io/docs/playable/optimise-your-builds/asset-size-breakdown).
- The command-line `STATS=1` / `STATS=2` flag adds a short or full size report — [Command line pipeline](https://docs.lunalabs.io/docs/playable/command-line/).
- The plugin added "build size breakdown" in 0.3.0 and "shaders' statistics in terms of size" in 0.3.1 ([Release notes](https://docs.lunalabs.io/docs/playable/release-notes)).
- Develop builds "[lack] asset compression, [serve] each file individually and [are] meant purely for testing purposes"; size work uses the breakdown and the per-network warnings after upload — [Optimise your builds](https://docs.lunalabs.io/docs/playable/optimise-your-builds/overview).
- Typical sizes:
  - Unity's guide recommends a 2–5 MB target and says files over 5 MB won't upload; load time under 5 s; template footage under 3.5 MB — [Unity: How to create playable ads (2026-09-30)](https://unity.com/resources/how-to-create-playable-ads).
  - A partner network's Luna page advises keeping total assets "BELOW 2.5MB" `[secondary][snippet]` — [Remerge help: Luna](https://help.remerge.io/hc/en-us/articles/8402317755676-Luna).

### Inferences
- Size budget, roughly: Luna's engine is ~0.65 MB compressed, and Runtime Analysis shrinks it further. That leaves ~4 MB of a 5 MB cap for code and assets. Our stripped Godot engine is ~3.6 MB brotli before any game data, about 5.5× Luna's footprint.
- Runtime Analysis is coverage-guided stripping at method granularity. A Godot analogue is coverage-guided class selection: record which classes a dev build instantiates or calls, then generate a `build_profile`. That works at class level, not method level, because the C++ is compiled ahead of time.
- The defaults (512 px, PNGQuant, JPEG 65, mono audio, 30 s cap, half floats) form a concrete, battle-tested asset policy for a playable profile, independent of the engine.

### Gaps
- No public per-category numbers for engine vs. code vs. assets in a typical Luna playable, and no published median playable size.
- Which minifier the engine and user code use (Closure Compiler is named only for the physics engine) is not stated.
- The audio output format (MP3/OGG/AAC) is not stated on the pages read.

## 3. Single-file packaging: base122 and brotli, one build to many networks

### Takeaway
The release build is a brotli-compressed resource archive. Since 3.4.0 the brotli build has no built-in dictionary, and since 6.x the decoder is compiled to wasm. Assets inside the HTML are encoded as base122 by default (since 2.7.0), with base64 as a fallback option, and a JS decoder unpacks everything at startup. The plugin produces one build. The Unity Playworks web platform then derives one creative per network, either single HTML or ZIP depending on the network, applies the network's store-click and lifecycle APIs, and flags builds that exceed a network's size limit.

### Cited Findings
- Encoding: "Unity Playworks Plugin encodes assets such as images and videos in **Base122**"; an option switches to Base64. Base122 saves "up to ~30%" over Base64 but needs a JS decoding library, which adds "a small startup delay" — [Advanced settings](https://docs.lunalabs.io/docs/playable/playable-setup/settings/advanced-settings).
- "Changed default assets encoding from base64 to base122" (2.7.0, 2021-11-09) — [Release notes](https://docs.lunalabs.io/docs/playable/release-notes)
- Compression ([Release notes](https://docs.lunalabs.io/docs/playable/release-notes)):
  - "Switched compression tool to a custom brotli build without a built-in dictionary" (3.4.0, 2022-04-01). This saved about 50–130 KB, depending on platform, and slightly improved startup. Dropping brotli's ~120 KB static dictionary shrinks the decoder that ships in the HTML.
  - 6.0.0 (2024-06-17) and 6.1.0 (2024-09-03) both note switching Brotli to a Wasm-compiled version.
  - "Fixed compression error producing corrupted archives" (3.9.0, 2022-06-09), which shows the resources are packed into an archive.
- The "Required JavaScript" category in the size breakdown includes "decompression routines and platform SDKs" — [Size Breakdown](https://docs.lunalabs.io/docs/playable/optimise-your-builds/asset-size-breakdown).
- Local pipeline stages ([Command line pipeline](https://docs.lunalabs.io/docs/playable/command-line/)):
  1. `unity:export` "Exports all assets from Unity project"
  2. `assets:bundle` "Compiles and compresses assets"
  3. `code:bundle` "Bridge engine compiles code from C# to JS"
  4. `package:bundle` "Bundles into HTML package"

  These are Jake (Node.js) tasks run with a bundled Node runtime. `TARGET_PLATFORM=playground` produces a "Unity Playworks archive" for upload.
- Per-network outputs — [Ad Networks overview](https://docs.lunalabs.io/docs/playable/ad-networks/overview):
  - "prepare a single playable scene, and a specific creative will be created" per network; 26 networks are listed.
  - Single HTML: AppLovin 5 MB, Unity Ads 5 MB, AdColony 2 MB, Snapchat 5 MB, InMobi 5 MB, generic MRAID.
  - Single HTML or ZIP: Meta 2 MB HTML / 5 MB ZIP, Mintegral 5 MB, Vungle 5 MB.
  - ZIP: Google Ads 5 MB; TikTok 3 MB, Tencent 3 MB, Liftoff 5 MB and Appreciate 4 MB as ZIP with resources.
  - Moloco: "Under 3KB, Single .txt file", presumably a hosted tag rather than the creative itself.
  - Per-network requirements named: "App Store Click API", "Game Ended API" (Mintegral, Vungle), TikTok language in the config file.
- Downloads — [Download Playables](https://docs.lunalabs.io/docs/playable/unityplayworks/download-playable):
  - Downloads happen in the web platform: "One creative for one ad network is equal to **one playable download**", metered against a usage balance.
  - The download page flags builds that exceed a network's size limit and enforces Facebook's "100 files or less" ZIP rule.
  - After upload, "Some networks options might have yellow of red warnings that indicate that the playable is too large for the network" ([Optimise your builds](https://docs.lunalabs.io/docs/playable/optimise-your-builds/overview)).
- Network settings in the plugin cover only Facebook (ZIP 5 MB or "single inlined HTML file (2Mb limit)"), TikTok/Tencent orientation and TikTok languages. Store URLs moved to the web front end — [Ad network settings](https://docs.lunalabs.io/docs/playable/playable-setup/settings/ad-network-settings).
- Variants without rebuilding: `LunaPlaygroundField` / `LunaPlaygroundAsset` mark editable fields and assets, and Pro allows "up to 256 variations in one playable file" — [Unity: How to create playable ads](https://unity.com/resources/how-to-create-playable-ads). The editor triggers "a reload of the playable preview" on value changes — [Create a Playable](https://docs.lunalabs.io/docs/playable/unityplayworks/create-playable).

### Inferences
- Per-network packaging happens server-side. Four facts point there: the local pipeline ends in one HTML package or one Playworks archive; downloads are per network and metered; the free plan restricts networks; and store URLs and variants are set in the web front end. The platform then injects the CTA adapter, store URLs and field values, and picks HTML or ZIP. The exact injection code is not documented.
- The pattern is base122 (AppLovin explicitly allows it) plus brotli with a small, dictionary-free decoder shipped as wasm. It confirms our own plan: compressed payload inside the HTML, decoded in JS or wasm at startup. Luna picked brotli over gzip even though gzip has a native `DecompressionStream`, so the extra decoder bytes pay off.

### Gaps
- Whether base122 is also used for networks that do not allow it (only AppLovin names base122) or switched per network, and whether the brotli archive holds code as well as assets, is not documented.
- The decoder's size, whether it is `brotli-dec-wasm` or a custom build, and its startup cost are not published.
- The CTA/MRAID adapter code and its per-network mapping are not public.

## 4. Workflow, licensing, ownership, status (late 2026)

### Takeaway
The workflow splits in two. Local: a Unity Editor plugin with a Node.js build pipeline produces develop builds (browser testing) and release archives. Cloud: Unity Playworks (playworks.unity.com) handles variants, previews, per-network downloads and API publishing. The free tier exports only to Unity Ads. All other networks need the paid plan, quoted at $15K per month on Luna's pricing page. Luna was bought by ironSource in February 2021, and ironSource merged into Unity in November 2022. The plugin is actively maintained (7.2.0, April 2026; Unity 6 support).

### Cited Findings
- Build paths: "Build and upload all from within the Playworks Plugin using one button", or build manually and add it — [Unity Playworks overview](https://docs.lunalabs.io/docs/playable/unityplayworks/overview)
- The CLI pipeline runs locally, but requires being signed into the plugin ("Authentication failed" otherwise). `project:deploy` uploads with `USER_EMAIL`/`USER_TOKEN` — [Command line pipeline](https://docs.lunalabs.io/docs/playable/command-line/)
- Pricing — [Pricing](https://docs.lunalabs.io/docs/playable/pricing):
  - FREE: unlimited exports, "Download to Unity Ads network only".
  - "$15K monthly": all networks, Insights, Creative Testing, support.
  - LevelPlay mediation clients get tailored quotes.
- Unity's guide (2026-09-30) says "Unity Ads is available on the free tier"; Pro gives downloads for "25 or more networks", 256 variations and Insights, with pricing applying from September 2026. Publishing via API goes to Unity Ads, Meta, AppLovin and AdColony. The plugin is installed via "Install Package from Disk" from the dashboard, and the dashboard shares its login with Unity Ads — [Unity: How to create playable ads](https://unity.com/resources/how-to-create-playable-ads)
- Ownership:
  - Luna Labs (UK; CEO Steven Chard) launched Unity-to-playable creation in 2019 — [TechCrunch, 2019-07-31](https://techcrunch.com/2019/07/31/luna-labs-creates-playable-ads-directly-from-unity/).
  - ironSource acquired Luna on 2021-02-23, terms undisclosed — [TechCrunch, 2021-02-23](https://techcrunch.com/2021/02/23/ironsource-acquires-luna-labs/).
  - Unity completed its merger with ironSource on 2022-11-07 — [Unity press release](https://unity.com/news/unity-completes-merger-ironsource).
- Current versions:
  - 7.0.0 (2025-11-06), 7.1.0 (2026-02-16), 7.2.0 (2026-04-27) — [Release notes](https://docs.lunalabs.io/docs/playable/release-notes).
  - Supported Unity versions are 2021.3–6000.0 ([FAQ](https://docs.lunalabs.io/docs/playable/faq/)).
  - The sunset of ironSource Ads and the ironSource Exchange (see `playable_ads.md`) does not touch Playworks on the pages read.
- Luna also supports "JavaScript Playables" (non-Unity HTML5 playables uploaded to the platform) — [Prepare your code](https://docs.lunalabs.io/docs/playable/code/overview/) (link list).

### Inferences
- Luna's cloud is not a build farm. Compilation, asset processing and packaging into an archive all run locally in the Editor and Node. The cloud adds the commercial and per-network layer: adapters, variants, metering and publishing APIs. A Bazel pipeline can own all of these locally.
- At $15K per month for non-Unity networks, the commercial model locks the multi-network output behind a subscription. Third-party packagers for other engines (see `playable_ads.md` §5) cover exactly that layer.

### Gaps
- No public statement on a 2026 roadmap, deprecation or rename beyond "Unity Playworks". There is no evidence of a change after 7.2.0 (April 2026). A newer release may exist past the part of the release notes that was read.
- The pricing page and Unity's guide disagree in naming ("Lite/Pro" vs "Free/$15K"). Whether $15K is still the list price after the September 2026 pricing change is unclear.

## 5. What transfers to a Godot/Bazel pipeline

### Takeaway
Luna's core trick does not transfer. It drops the real engine and runs on a separate lightweight JS runtime with transpiled scripts. For Godot that would mean reimplementing Godot's scene system, renderer, animation, physics and GDScript in JS, an engine-sized effort Luna spent seven years on and which still has a long unsupported list. What does transfer is everything around the runtime: coverage-guided stripping, an asset policy, brotli plus base122 with a small decoder, a size breakdown, one build with per-network adapters and size gates, and variant parameters injected without a rebuild.

### Cited Findings
- Luna's runtime is ~650 KB compressed ([FAQ](https://docs.lunalabs.io/docs/playable/faq/)). Our stripped 4.7.2 engine is 3.62 MB brotli / 5.15 MB gzip (`minimal_engine_size.md`, local measurement).
- Runtime Analysis: ~30 % less code by recording used classes and methods in a dev build ([Runtime Analysis](https://docs.lunalabs.io/docs/playable/optimise-your-builds/runtime-analysis)).
- Asset defaults: 512 px, PNGQuant, JPEG 65, mono 128 kbps 30 s, half floats ([Set Optimal Settings](https://docs.lunalabs.io/docs/playable/playable-setup/settings/set-optimal-settings/)).
- Brotli without dictionary, decoded in wasm, plus base122 assets ([Release notes](https://docs.lunalabs.io/docs/playable/release-notes), [Advanced settings](https://docs.lunalabs.io/docs/playable/playable-setup/settings/advanced-settings)).
- Per-network formats and size warnings ([Ad Networks overview](https://docs.lunalabs.io/docs/playable/ad-networks/overview), [Download Playables](https://docs.lunalabs.io/docs/playable/unityplayworks/download-playable)).

### Inferences
- **Not transferable:**
  - Transpiling to a reimplemented runtime. GDScript→JS would need a Godot API reimplementation in JS. Unlike Unity, Godot has no fixed C# surface to target, and the scene format plus the Compatibility renderer would have to be rebuilt.
  - Method-level dead-code elimination of the engine. Godot ships compiled C++/wasm, so stripping happens at build time (modules, `disable_*`, `build_profile`, LTO) or with wasm-level tools (`wasm-opt`, wasm-metadce), not by removing JS functions after a recorded run.
- **Transferable, in rough order of payoff:**
  1. Coverage-guided `build_profile`: an instrumented dev build or a scene/PCK scan records the `ClassDB` classes used, and Bazel generates the profile for the playable template. This is the Godot equivalent of Runtime Analysis, at class granularity. Like Luna, it needs an "untick" override list and the same risk warning about missed paths.
  2. A playable asset profile in the export or import step: texture max size and lossy WebP/JPEG instead of lossless (Lichtpost's 3.6 MB backgrounds), mono audio at a lower bitrate, font subsetting (Luna's custom alphabet ≈ dynamic font subsetting or MSDF with a reduced charset), and shader-variant pruning.
  3. A brotli payload with a slim decoder: Luna's choice of a dictionary-free brotli wasm decoder supports shipping the engine as brotli (3.6 MB) rather than gzip (5.15 MB), at a few tens of KB of decoder cost. Base122 only for AppLovin-style raw-HTML limits.
  4. A size-breakdown report as a Bazel output (engine, JS glue, PCK by resource type, decoder, network adapter), with per-network red/yellow thresholds as build-time checks instead of upload-time warnings.
  5. One build, many networks: a network-neutral HTML/archive plus per-network adapter targets (CTA API, Game-Ended API, HTML vs ZIP, file-count rule), mirroring Playworks' download step but local and free.
  6. Variants without a rebuild: a `LunaPlaygroundField` analogue, i.e. exported properties overridden from a small JSON blob injected at packaging time, so creative tests do not rebuild the PCK.
- **Strategic reading:** even Unity, which owns a wasm engine, chose a separate lightweight runtime for playables rather than shrinking Unity WebGL. For Godot the realistic route remains the stripped real engine (budget ~3.5 MB brotli) plus aggressive assets, viable mainly on networks that count ZIP bytes or allow 5 MB. A Luna-like reimplementation is out of scope.

### Gaps
- No public numbers for decode or startup time of Luna playables to compare with a Godot wasm compile on low-end Android.
- No information on whether Unity plans to move Playworks onto Unity's own web runtime (for example the Unity 6 web platform). No such statement was found.
