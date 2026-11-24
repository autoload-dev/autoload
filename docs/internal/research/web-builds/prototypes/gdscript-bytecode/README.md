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
of the same configuration) and play in the browser. Until R15 it missed String's own
macros (`bind_string_method(name, sarray(), ...)`) and kept every String method.

`shake_operators.py` removes the operator evaluators nothing can call: those of
operators the engine evaluates on any type (comparisons, `+` and `-`) stay, the rest only
for the operand types the bytecode or the compiled code (`gen_cpp.py`'s `operators`)
evaluates them on. `Expression` evaluates any operator, so the build profile disables it
(see `../wasm-retention/README.md`).

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

**Bug in T4 to T6, fixed in R3.** `shake_variant.py` compared the C++ name of utility
functions, but `FUNCBINDR(_typeof, ...)` registers `typeof`. Without `typeof` every GDScript
`match` fails silently: `Palette.material()` returned null, and the platforms rendered with
the default white material. The replays did not notice, since the rules use no `match`; a
render comparison against the stock build did. The sizes of T4 to T6 stand within a few
hundred bytes (R3 against R2).

From the official template to R3, brotli: 7.10 MB (official 4.7.2) → 2.63 MB (4.7.2,
modules, `-Oz`, profile) → 2.56 MB (4.8) → 2.48 MB (no GDScript compiler) → 2.10 MB
(bindings, built-ins, utilities and compatibility shaken) → 2.05 MB (unused properties) →
1.87 MB (virtual function elimination, no RTTI).

## What the linker can remove (2026-11-24)

The engine exports 13 functions (`_main`, `malloc`, `free` and the runtime's own), so
exports keep nothing alive. What does: virtual functions, which every vtable references
whether or not anyone calls them, and RTTI. Full LTO with virtual function elimination
removes the vtable slots no virtual call reaches.

| Engine (T6 settings, typed Lichtpost's usage) | raw | gzip -9 | brotli 11 |
| --- | ---: | ---: | ---: |
| T7, as T6 | 6.82 MB | 2.66 MB | 2.05 MB |
| V1, `-fvisibility=hidden -fwhole-program-vtables -fvirtual-function-elimination` | 6.12 MB | 2.43 MB | 1.88 MB |
| R1, also `-fno-rtti` (`no_rtti.py`) | 6.03 MB | 2.41 MB | 1.86 MB |
| R3, also `-DTYPED_METHOD_BIND` | 6.09 MB | 2.42 MB | 1.87 MB |

V1 and R1 crash at start ("null function"): a method bind calls a virtual setter through
a member function pointer that Godot casts to `void (__UnexistingClass::*)(...)`, so one
wrapper serves every class with the same signature. Virtual function elimination tracks
calls through member function pointers by their class type; no vtable belongs to
`__UnexistingClass`, so the setters' slots look unused and are cleared. Godot's
`TYPED_METHOD_BIND` (the MSVC default) keeps the real class in the pointer's type and
makes elimination safe, for 10 KB: R3 passes the replays (macOS build with the same flags)
and plays in the browser. `-fno-rtti` needs `no_rtti.py`, which turns Godot's few
`dynamic_cast`s into checked or unchecked `static_cast`s; for a prototype only.

The rest of the data section (1.5 MB raw) is mostly fixed tables the code needs or
believes it needs: the Brotli dictionary (120 KB, WOFF2 fonts and `Compression`),
PCRE2's Unicode tables (118 KB, `RegEx` is in core), libc's `iconv` tables (136 KB), the
GLES3 area light lookup tables (128 KB), the default theme's font (63 KB) and FreeType's
PostScript glyph names (55 KB). None of them is reachable from what Lichtpost does, but
each is referenced from code the linker must keep; removing them needs engine options,
not linker flags.

## Static typing (2026-11-24)

Lichtpost's game scripts are now fully typed: `project.godot` treats untyped declarations
and unsafe property and method access in `main/` as errors. Replays stay identical on
4.7.2 from source and on the 4.8 bytecode patch. The bytecode barely changes:

| Opcodes in all functions | untyped | typed |
| --- | ---: | ---: |
| Calls by name (`OPCODE_CALL*`) | 215 | 198 |
| Property reads by name (`GET_NAMED`) | 248 | 242 |
| Property writes by name (`SET_NAMED`) | 87 | 85 |
| Native method binds | 136 | 131 |
| Validated operators | 311 | 346 |
| Variant operators | 73 | 38 |

The usage list hardly moves either: 172 → 168 names, 44 → 46 method binds; of the names
not declared by Lichtpost, 56 → 51. Godot's code generator only resolves calls on native
classes statically. Calls, property reads and writes on another script's instance
(`run.model.x`, `view.react(...)`) stay by name even when the variable is typed: a typed
script reference does not let the code generator use a member index or a direct call.
Typing pays off in arithmetic (validated operators) and in what a code generator outside
Godot's could know; the bytecode alone has dropped those types again.

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
