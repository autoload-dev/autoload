# What keeps code and data alive in a WebAssembly build

`retention.py` answers "why is X still in the binary" for a fully optimized web build.
Throwaway research tooling; not part of the ruleset.

## How

Link with `-Wl,--save-temps`: wasm-ld then leaves the LTO result next to the output
(`<output>.wasm.lto.o`), a relocatable WebAssembly object after inlining,
devirtualization and virtual function elimination, but before garbage collection and
wasm-opt. It still has a symbol table and relocations (`wasm_object.py` reads them):

- nodes are functions, and ranges of data cut at every data symbol (vtables, tables,
  strings), so overlapping alias symbols (`__typeid_*`) do not merge everything;
- edges are relocations: calls, taken function addresses (a vtable or a registration
  table holding a method), and data addresses;
- roots are the static constructors, `main`, `malloc`, `free`, and anything marked
  exported or no-strip.

On that graph it computes the dominator tree (Cooper, Harvey and Kennedy) and each node's
retained size: what only it keeps alive. `--cut REGEX` removes the matching nodes and
reports what becomes unreachable, for roots that share what they keep. `--path NAME`
prints one chain from a root. Sizes are before wasm-opt (6.0 MB code and 1.6 MB data
reachable, against 4.3 and 1.5 MB in the final binary), so they rank rather than predict.

```sh
python3 retention.py <output>.wasm.lto.o --top 60
python3 retention.py <output>.wasm.lto.o --cut '^RegEx::|^pcre2_'
python3 retention.py <output>.wasm.lto.o --path '.rodata.LTC_LUT1'
```

Set `CXXFILT` to `llvm-cxxfilt` for demangled names.

## Lichtpost's engine (R12: all GDScript compiled, no VM), 2026-11-24

What removing one root frees (before wasm-opt), and what keeps it:

| Root | Frees | Kept by |
| --- | ---: | --- |
| RegEx and PCRE2 | 269 KB | `RotatedFileLogger`, which Main::setup creates for log files |
| FreeType modules other than TrueType and SFNT | 245 KB | `ft_default_modules`: every built-in font driver registers |
| `FileAccessCompressed::_close()` (ZSTD compressor) | 231 KB | the class's destructor; the binary resource loader reads compressed files |
| `LineEdit` | 183 KB | its registration as a creatable class |
| Brotli decoder and dictionary | 165 KB | `Compression::decompress()`, which switches on a runtime mode |
| `iconv` and its charsets | 145 KB | `OS_Unix::string_to_multibyte()`, a virtual of the web OS |
| LTC lookup tables | 131 KB | `RasterizerSceneGLES3::render_scene()` |
| Default theme font | 64 KB | `Main::setup2()` |
| `ParticleProcessMaterial` | 50 KB | `register_scene_types()` |

The largest dominators are the engine's own startup (`Main::setup` keeps 4.2 MB), the
text server with FreeType (610 KB), the binary resource loader (258 KB), the GLES3 scene
renderer and shader compiler, and Variant's registration tables (435 KB). The compiled
GDScript of the whole game keeps 166 KB.
