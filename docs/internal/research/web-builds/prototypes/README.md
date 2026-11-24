# Web build prototypes

Throwaway research on how small and fast a Godot 4.8 web build of Lichtpost can get, and
whether it fits a playable ad. Nothing here is part of the ruleset; each directory's
README has its measurements and how to reproduce them.

| Directory | Question |
| --- | --- |
| `gdscript-bytecode/` | Ship precompiled bytecode instead of the compiler, and shake the engine's bindings to what the game uses |
| `gdscript-aot/` | Specialize the VM per function (stage B) |
| `gdscript-cpp/` | Compile GDScript to C++ from the typed syntax tree, with direct engine calls and no VM (stage C) |
| `wasm-retention/` | What keeps code alive in the wasm, and cutting it |
| `size-map/` | Where the size of the whole bundle comes from |
| `playable/` | One HTML file for the ad networks' limits |

## Where Lichtpost stands (2026-11-24)

| Step | Engine, Brotli | Whole bundle, Brotli | One HTML file |
| --- | ---: | ---: | ---: |
| R12: all GDScript compiled, no VM | 1.88 MB | | |
| R17: cuts, shaken Variant tables, compact code | 1.24 MB | 4.95 MB | 11.48 MB (naive base64) |
| plus lossy backgrounds, stripped bytecode | 1.24 MB | 1.89 MB | 7.16 MB (naive base64) |
| plus LZMA in the page (`playable/`) | | | **2.44 MB**, 1.84 MB zipped |

The single file fits every 5 MB network, counted raw or zipped; Meta's 2 MB single HTML
does not.

## Lessons

- **The script runtime was not the size lever; the engine around it was.** Compiling all
  of Lichtpost to C++ and dropping the VM left the engine within 1 % of the interpreter
  build. Cutting what the engine keeps for features the game never uses saved a third.
- **Find the reference that keeps a payload alive before cutting it.** The dominator tree
  of the LTO object (`wasm-retention/`) named each large payload and the one call holding
  it. Each cut was then one guard, build option or profile entry.
- **Look at the whole bundle, not only the engine.** Three lossless background images
  were larger than the engine after Brotli; lossy WebP at quality 0.8 shrank them sevenfold
  with no visible change.
- **Compress before encoding.** Base64 of an uncompressed payload was the single largest
  overhead of a one-file playable. LZMA with a small JS decoder beats zstd and Brotli once
  the decoder counts, and a denser text encoding than base64 only pays where the HTML is
  counted raw and the network allows it.
- **Verify every size change by behavior.** Each engine variant ran Lichtpost's replays on
  a macOS build of the same sources (identical score, tick and position) and played in
  the browser with a clean console.
- **Keep scratch work durable.** The session's scratch directory, with the Godot sources
  and builds, was wiped when the session restarted; only what was committed survived.
