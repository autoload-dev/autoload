# Minimal web engine: measured sizes (2026-11-23)

How small a Godot 4.7.2 web template gets with Godot's own switches, and whether
Lichtpost (`rules_godot/examples/projects/lichtpost`, a 3D runner without physics or
navigation) still runs on it. Built outside Bazel with SCons and emsdk 4.0.20, the
Emscripten version of the official 4.7.2 templates, on an Apple-silicon Mac with `-j12`.

## Build

Common SCons arguments of every variant:

```
platform=web target=template_release threads=no production=yes
modules_enabled_by_default=no module_gdscript_enabled=yes
module_text_server_fb_enabled=yes module_freetype_enabled=yes
disable_physics_2d=yes disable_physics_3d=yes disable_navigation_2d=yes
disable_navigation_3d=yes disable_xr=yes disable_advanced_gui=yes
```

| Variant | Extra arguments | Build time |
| --- | --- | ---: |
| L | (none: `optimize=size`, `lto=thin` from Godot's web defaults) | 80 s |
| M | `disable_3d=yes` | 61 s |
| L+ | `optimize=size_extra lto=full` | 126 s |
| L2 | `optimize=size_extra lto=full module_webp_enabled=yes` | 69 s |

Build times are incremental where sources were shared, but even the first full build
took under a minute and a half: the minimal module set compiles little.

## Sizes of `godot.wasm`

| Variant | raw | gzip -9 | brotli 11 | xz -9e |
| --- | ---: | ---: | ---: | ---: |
| Official `web_nothreads_release` | 39.51 MB | 10.05 MB | 7.10 MB | – |
| L | 23.38 MB | 5.50 MB | 3.79 MB | – |
| M (2D only) | 21.16 MB | 5.04 MB | 3.50 MB | – |
| L+ | 17.48 MB | 5.05 MB | 3.54 MB | – |
| L2 (runs Lichtpost) | 17.71 MB | 5.15 MB | 3.62 MB | 3.47 MB |

`godot.js` stays at 0.25 MB raw, 0.06 MB gzip. Lichtpost's PCK is 3.80 MB raw and
3.65 MB gzip, 3.59 MB brotli: mostly lossless (WebP) background textures that do not
compress further.

Observations:
- Module selection and the `disable_*` switches halve the engine: brotli 7.10 → 3.79 MB.
- `disable_3d` saves little compressed (−0.3 MB brotli); the Compatibility renderer and
  the scene core dominate.
- `-Oz` with full LTO shrinks the raw wasm by a quarter (23.4 → 17.5 MB) but the
  compressed size by only ~7 %. Raw size matters for parse/compile time and for limits
  that count raw bytes.
- L2's sections: code 14.87 MB, data 2.65 MB. Printable runs of at least 40 bytes in the
  data total 1.07 MB, of which ~0.29 MB are GLSL shader sources; license texts such as
  the MPL are embedded too.
- A per-function breakdown failed: Godot's web link drops the name section even with
  `linkflags=--profiling-funcs` or `-g2`, and `--emit-symbol-map` trips an assertion in
  emcc's post-link. Which classes make up the 14.9 MB of code is still open.

## Lichtpost on the minimal engine

- Variant L runs the game, but three background textures fail to load
  (`load_image_from_file … img.is_null()`): their import (`compress/mode=0`, lossless)
  stores WebP, and the `webp` module was off. Nothing fails before the browser.
- L2 adds `webp`; the game loads and plays without console errors (checked in the
  browser after starting a run).

So the engine modules a pack needs depend on how its resources were imported, not only
on the classes its scenes use. The import results are known at build time (the `.ctex`
data format, the importer and its options), so a missing decoder module could be a
build-time error instead of missing textures at run time.

## Playable-ad budget

Against the ~5 MB limits in `playable_ads.md` (L2 engine plus Lichtpost):

| Payload | gzip | brotli / xz |
| --- | ---: | ---: |
| Engine (wasm + js) | 5.21 MB | ~3.5–3.7 MB |
| Lichtpost PCK | 3.65 MB | ~3.6 MB |
| Total | 8.86 MB | ~7.2 MB |

- With gzip, which `DecompressionStream` decodes natively, the stripped engine alone
  exceeds 5 MB. Brotli, xz or zstd need a JS decoder shipped in the HTML.
- For networks that count the raw HTML (AppLovin, Unity, Moloco), base64 adds a third:
  ~4.7 MB for the brotli engine alone, leaving almost nothing for the game.
- Playables therefore need a further engine cut (class-level `build_profile`, which
  rules_godot's source recipes reject today) and an asset budget (Lichtpost's lossless
  backgrounds alone are 3.6 MB).

## Not done

- Per-class or per-module attribution of the remaining code.
- A `build_profile` generated from the project's class usage.
- Lichtpost's PCK with lossy or smaller textures.
- Startup time and memory of the minimal engine on a mobile browser.
