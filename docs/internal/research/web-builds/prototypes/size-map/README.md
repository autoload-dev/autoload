# Size map of a web bundle

A zoomable treemap of everything a web build of Lichtpost ships: the engine by area,
the pack by file, the loader and the page, as one HTML file, raw, or with Brotli. A
second view shows the engine's dominator tree: what removing a function would free.
Throwaway research tooling; not part of the ruleset.

`index.html` with `data.json` is the page as published on 2026-11-24 (R17 with lossy
backgrounds and stripped bytecode). Serve the directory and open it; it loads d3 from
cdnjs.

```sh
CXXFILT=llvm-cxxfilt python3 engine_tree.py <web.wasm.lto.o> <gdscript_native.gen.inc> engine.json
python3 bundle_tree.py <web export dir> engine.json data.json   # needs `pip install brotli`
```

- `engine_tree.py` reads the LTO object that `-Wl,--save-temps` leaves
  (`../wasm-retention/`), assigns every reachable symbol an area by its class or function
  name, and gives nameless tables and data to the code that alone keeps them (their
  immediate dominator). Compiled GDScript is grouped by script, using the `.inc`'s table.
- `bundle_tree.py` scales the engine's bytes before wasm-opt to the final wasm, raw and
  Brotli, reads every file of the pack, and adds the loader and the page.

The two scripts were rebuilt from the session after its scratch directory, with the
build outputs, was lost. `bundle_tree.py`'s pack reader ran against Lichtpost's pack and
`engine_tree.py` against a small synthetic graph; neither ran again on the R17 object,
which no longer exists.

## What the map showed

- Before the textures changed, three lossless 1536×1024 backgrounds were 3.68 MB of the
  4.0 MB pack, more than the whole engine after Brotli.
- After it, the engine is two thirds of the transfer (1.24 of 1.89 MB Brotli). Rendering
  (26 %) and Variant with the core (23 %) are its largest areas; compiled game code is
  under 2 %.
- The pack still held all script bytecode although every function runs as C++; see
  `../gdscript-cpp/strip_bytecode.py`.
