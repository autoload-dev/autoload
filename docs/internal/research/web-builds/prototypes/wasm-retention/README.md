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

## Cutting what nothing uses (R13), 2026-11-24

`cut_payload.py <godot source>` removes the reference that keeps each payload, after the
shaking of R12 and only for the web (`WEB_ENABLED`, or a class the build profile
disables). Two cuts are build options instead: `brotli=no`, and a build profile that also
disables `LineEdit` and `Expression`.

| Cut | How | Brotli saved |
| --- | --- | ---: |
| Brotli decoder and the default theme font | `brotli=no`: the font is WOFF2, Lichtpost brings its own TTF | 120 KB |
| `iconv` and its charsets | `OS::string_to_multibyte()` fails on the web | 106 KB |
| LTC lookup tables | zero tables: the profile disables area lights | 93 KB |
| RegEx and PCRE2 | no `RotatedFileLogger` on the web (file logging is off there) | 63 KB |
| FreeType modules other than TrueType, SFNT, autofit and the renderers | module list | 53 KB¹ |
| `LineEdit` | build profile | 42 KB |
| ZSTD compressor | the web cannot open compressed files for writing | 41 KB |
| `ParticleProcessMaterial` shaders | only built when the class is | 10 KB |

¹ Measured together with the GDExtension interface (`gdextension_setup_interface()`,
useless without dynamic linking) and `Expression`, added after the per-cut builds.

Each row is the difference to a build with every cut but that one. Together:

| Build | wasm | wasm, brotli |
| --- | ---: | ---: |
| R12: all GDScript compiled, no VM | 6,093,459 | 1,880,609 |
| R13: R12 and every cut | 4,552,182 | 1,271,069 |

R13 saves 610 KB (32 %). It plays in the browser without a console error: title, a run,
the result with the stored personal best, and the options. The cuts change only the web
build, so the game's macOS replays are unaffected.

FreeType reads its module list through a macro include that SCons does not scan, so
`cut_payload.py` also touches `ftinit.c`; without that, a cached object keeps every
module.

## Variant's tables (R14, R15), 2026-11-24

Variant registers every operator evaluator, constructor and built-in method at startup.
With all of Lichtpost's GDScript compiled to C++, few are called through those tables:

| Build | Change | wasm, brotli |
| --- | --- | ---: |
| R13 | | 1,271,069 |
| R14 | `shake_operators.py`: 405 of 728 operator evaluators | 1,261,815 |
| R15 | `shake_variant.py` also shakes String's methods; no bytecode writer without the compiler | 1,250,746 |

The operators that stay are those the engine evaluates on any type (sorting, `min()`,
`max()`, `clamp()`, hashing, tweens) and those the compiled code evaluates on untyped
values. Constructors stay: the engine converts values with the one-argument constructor
of any type, and the remaining multi-argument ones are small. R15's sources, built for
macOS, give the same replay results, and R15 plays in the browser without a console
error.

The resource loaders registered as instances are not worth cutting: no saver is reachable
any more, the binary and text loaders are needed (Lichtpost's pack holds `.tscn` and
`.tres` as text), and the rest (translations, JSON, crypto, shader includes) keep under
20 KB before wasm-opt.

What still dominates after R15: the text server with FreeType (340 KB before wasm-opt),
the default theme (`fill_default_theme()`, 144 KB, which Lichtpost's own theme mostly
overrides), the compiled game (166 KB) and the WebP decoder (63 KB).

## Where Lichtpost's web engine stands

| Build | wasm, brotli | |
| --- | ---: | --- |
| R3: shaken bindings and Variant, interpreter | 1,870,810 | `../gdscript-bytecode/` |
| R12: all GDScript compiled to C++, no VM | 1,880,609 | `../gdscript-cpp/` |
| R13: unused payload cut | 1,271,069 | above |
| R15: Variant's tables shaken | 1,250,746 | above |
| R17: compact compiled code | 1,243,693 | `../gdscript-cpp/` |

R17 is 34 % smaller than R12. Next in line by size is the default theme, which
Lichtpost's own theme mostly overrides.

## Reproduce R17

In the layout of `../gdscript-bytecode/` (Godot 4.8-beta1 in `src48/godot` with the
stage A to C patches, emsdk 6.0.12, `build48.sh`), with `typed.inc` and `typed.usage.json`
from `gen_cpp.py` and `usage.json` from `bytecode_usage.py --compiled typed.usage.json`:

```sh
cd src48/godot && git checkout -- .
cp typed.inc modules/gdscript/gdscript_native.gen.inc
python3 shake_bindings.py . usage.json --properties properties.json
python3 shake_variant.py . usage.json
python3 shake_operators.py . usage.json --compiled typed.usage.json
python3 no_rtti.py .
python3 cut_payload.py .
VF="-fwhole-program-vtables -fvirtual-function-elimination"
GDSCRIPT_NO_VM=1 GDSCRIPT_NO_COMPILER=1 ./build48.sh R17 brotli=no lto=full optimize=custom \
  build_profile=lichtpost48c.gdbuild disable_2d=yes deprecated=no \
  "ccflags=-Oz -DSIZE_EXTRA -fvisibility=hidden" "cxxflags=$VF -fno-rtti -DTYPED_METHOD_BIND" \
  "linkflags=-Oz -fvisibility=hidden $VF -Wl,--save-temps"
```

`lichtpost48c.gdbuild` is `lichtpost48.gdbuild` (research notes) plus `LineEdit` and
`Expression`. Restore the sources with `git checkout -- .` before the next variant: the
scripts rewrite them in place. A build of the same sources for macOS
(`buildmac48.sh`, same environment variables) runs the replays (`replays.sh`): delivery
1260 at tick 2000, fall at tick 161, pipe at tick 554.

## Lessons

- **Measure what keeps code alive, then cut the reference.** The dominator tree of the LTO
  object named every large payload and the one call that held it; most cuts were one
  `#ifdef` or a build option. Guessing from symbol sizes would have missed RegEx (kept by
  the file logger) and iconv (kept by one virtual of the web OS).
- **Measure each cut alone.** Builds take under a minute with SCons' cache, so a build
  without each cut costs little and showed which cuts matter (iconv, Brotli, LTC tables).
- **SCons does not see macro includes.** FreeType reads its module list through
  `#include FT_CONFIG_MODULES_H`; changing that header changed nothing until `ftinit.c`
  itself changed.
- **Keep the console clean.** Harmless errors from shaken lookups hid nothing yet, but
  would have hidden the next real one; they are fixed, not filtered.
- **Shaking Variant is safe only per operator.** The engine evaluates comparisons, `+`
  and `-` on values of any type (sorting, hashing, tweens), so only the other operators
  can be shaken by the types the game uses.
