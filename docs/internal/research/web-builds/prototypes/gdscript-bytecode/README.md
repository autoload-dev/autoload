# GDScript bytecode ahead of time (prototype, stage A)

Compile a project's GDScript at build time and ship its bytecode, so the web runtime can
leave out GDScript's tokenizer, parser, analyzer and compiler. Throwaway code against
upstream Godot 4.8-beta1 (commit `4d10419`); not part of the ruleset.

## Result (2026-11-24)

Lichtpost runs from bytecode on a web engine without the GDScript compiler: menu, a run,
scoring and the game-over dialog, no console errors.

| Engine (Q2 settings: minimal modules, `-Oz`, `SIZE_EXTRA`, full LTO, build profile) | raw | gzip -9 | brotli 11 |
| --- | ---: | ---: | ---: |
| Q2, stock GDScript | 9.59 MB | 3.40 MB | 2.56 MB |
| A1, bytecode patch, compiler still present | 9.61 MB | 3.41 MB | 2.57 MB |
| A2, without the compiler (`GDSCRIPT_NO_COMPILER`) | 9.31 MB | 3.30 MB | 2.48 MB |

The engine loses 80 KB brotli (3 %). The bytecode PCK is 214 KB larger than the source
PCK (4.01 vs 3.80 MB raw): each function carries its own constant and name tables, while
the source text compresses well. Not measured: load time, which should improve since no
script is parsed or compiled at start.

## Tree shaking the bindings (2026-11-24)

The bytecode names everything a project calls in the engine. `bytecode_usage.py` lists it
(`usage.json` for Lichtpost): 44 method binds, 16 built-in methods, 16 utility functions,
43 operators and 172 names GDScript calls dynamically. `shake_bindings.py` then removes,
before the build, every `ClassDB::bind_method` (and static and vararg variant) of the
engine that is not kept. Kept are the bytecode's method binds, any method whose name is
in a name table (dynamic calls such as `new()` on a native class), every property's setter
and getter (scenes set properties through them; a class may use its parent's accessor),
every method starting with `_` (engine callbacks bound to be called by name) and the
GDScript module's own bindings. Of 15,081 bindings, 7,070 go.

| Engine (Q2 settings, no GDScript compiler) | raw | gzip -9 | brotli 11 |
| --- | ---: | ---: | ---: |
| A2, all bindings | 9.31 MB | 3.30 MB | 2.48 MB |
| T3, unused bindings removed | 7.78 MB | 2.87 MB | 2.19 MB |
| T4, also unused built-in methods (675 of 805) and utility functions (90 of 109) | 7.30 MB | 2.78 MB | 2.14 MB |
| T5, also `deprecated=no` (compatibility bindings) | 7.09 MB | 2.72 MB | 2.10 MB |
| T6, also the accessors and registrations of unused properties | 6.83 MB | 2.66 MB | 2.05 MB |

Lichtpost's three replays (`replays.sh`: delivery, fall, pipe) give identical results on
the stock engine with the source PCK and on the macOS build of T3 with the bytecode PCK
(score, tick, position), and the web build plays in the browser. First attempts failed
loudly, which is the point to keep: a missing binding shows as an error at load time
(`Invalid getter`, `unknown method` in the bytecode loader) or as a null object where a
dynamic call (`MeshInstance3D.new()`) lost its binding.

`shake_variant.py` also removes the built-in methods and utility functions
neither the bytecode nor a name table names. T4 and T5 pass the same replays (macOS builds
of the same configuration) and play in the browser.

**Properties (T6).** `dump_properties.gd` lists the properties the project's scenes store
on nodes, the storage properties of the resources they and the project settings use (the
input map's `InputEventKey`s need `physical_keycode`), and the methods their connections
name. `shake_bindings.py --properties` keeps only those properties' accessors, plus those
whose name the bytecode holds as a string constant (`tween_property(self, "position", …)`)
or calls, and removes the other properties' `ADD_PROPERTY` registrations: 13,342 of 15,081
bindings go. Replays stay identical, keyboard input works in the browser. The gain is
small (50 KB brotli): the engine still calls the accessors directly, and a method bind's
wrapper is a template per class and signature, so a wrapper only goes once no bound method
of that class shares its signature.

Code before `wasm-opt` (wasm-ld map, no LTO), Q2 against T5: MethodBind wrappers 2,480 →
743 KiB, `_bind_methods` 658 → 479 KiB, Variant built-ins 665 → 161 KiB, utilities 94 →
23 KiB; the GDScript VM stays at 49 KiB.

Remaining start-up noise: `set_method_flags` for removed methods and one property whose
`ADD_PROPERTY` the regex misses (`DPITexture.color_map`).

From the official template to T5, brotli: 7.10 MB (official 4.7.2) → 2.63 MB (4.7.2,
modules, `-Oz`, profile) → 2.56 MB (4.8) → 2.48 MB (no GDScript compiler) → 2.10 MB
(bindings, built-ins, utilities and compatibility shaken).

## How it works

`godot-4.8-beta1-gdscript-bytecode.patch` (modules/gdscript only):

- `gdscript_bytecode.{h,cpp}` saves a compiled script (inner classes, members, static
  variables, constants, signals, RPC config, every function with its bytecode, constants,
  types, lambdas) and restores it without the compiler. Function pointers into the engine
  (operators, setters and getters, built-in methods, constructors, utility functions,
  method binds) are saved as names and resolved when loading, so the compiling build and
  the loading build need the same classes and methods, not the same binary.
- `GDScript::reload()` loads bytecode found in a `.gdc` file instead of parsing;
  `GDScriptCache::get_shallow_script()` builds the inner classes from it.
- `GDScriptBytecodeWriter.compile(path)` exposes the saver to `dump_bytecode.gd`.
- `gdscript_no_compiler.cpp` and `SCsub` (`GDSCRIPT_NO_COMPILER=1`) build the runtime
  without tokenizer, parser, analyzer, compiler, code generator, linter and disassembler;
  18 entry points remain as failing stubs.

Three properties of Godot's bytecode had to change to make it portable between builds:

- **Globals by index.** `OPCODE_STORE_GLOBAL` indexes the language's global array, whose
  order depends on the classes a build registers. The code generator now emits
  `OPCODE_STORE_NAMED_GLOBAL`, and the VM falls back from autoloads to the global array by
  name.
- **Pointer-sized slots.** `OPCODE_OPERATOR` reserves `sizeof(pointer) / sizeof(int)`
  slots for a cached evaluator: two on 64-bit macOS, one on wasm32, so bytecode compiled on
  macOS misreads on the web. Fixed at two slots.
- **Caches in the bytecode.** The VM writes the cached operator signature and evaluator
  into the code. Compiling for the dump disables script execution, so no static
  initializer runs and no host pointer is saved.

## Reproduce

The scripts expect the session's layout (sources in `src48/godot`, emsdk 6.0.12 in
`emsdk/`, a venv with SCons, the 4.8 build profile in `profile48/`):

```sh
./buildmac48.sh A disable_path_overrides=no          # the compiler: a macOS template
./outmac48/A/godot.macos.template_release.arm64 --headless --main-pack <lichtpost>.pck \
  --script dump_bytecode.gd -- <bytecode dir>
python3 bytecode_pck.py <lichtpost>.pck <bytecode dir> index_bytecode.pck <rules_godot/tools>
GDSCRIPT_NO_COMPILER=1 ./build48.sh A2 lto=full optimize=custom "ccflags=-Oz -DSIZE_EXTRA" \
  linkflags=-Oz build_profile=<profile> disable_2d=yes
./mksite.sh A2 out48/A2/*.zip index_bytecode.pck     # then serve sites/A2
```

## Open points

- Bytecode is tied to a Godot minor and to the build's class set; a version or class-set
  check in the header is missing.
- Debug information (`stack_debug`, line opcodes of debug builds) is not saved.
- `get_global_class_name()` and other editor-facing queries parse source; they fail in the
  compiler-less runtime.
- Exact use: the bytecode names every engine method, built-in and utility it calls. That
  list is the input for stripping unused bindings (see the engine size notes).
