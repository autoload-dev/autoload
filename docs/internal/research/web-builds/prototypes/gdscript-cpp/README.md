# GDScript compiled to C++ from the typed syntax tree (prototype, stage C)

Compile GDScript functions to C++ from the syntax tree Godot's analyzer produces, with
every expression's static type, instead of from bytecode (stage B, `../gdscript-aot/`).
Throwaway code against Godot 4.8-beta1 with the stage A and B patches; not part of the
ruleset.

## Result (2026-11-24)

53 of Lichtpost's 105 functions compile, among them the whole route model, the game flow
and most of the HUD and interface; the rest stay bytecode. Lichtpost's three replays give
the same results as the interpreter on macOS, and the web build plays.

Speed, macOS arm64, `bench.gd` from stage B (3,000 runs of the route model, 459,000 ticks,
best of five, less a run with zero runs):

| Engine | GDScript time | |
| --- | ---: | ---: |
| Interpreter, lights as `Dictionary` | 1,056 ms | 1.00× |
| Stage B, specialized VM (for comparison, earlier build) | | 1.24× |
| Route model compiled, lights as `Dictionary` | 579 ms | 1.82× |
| Interpreter, lights as a typed class | 969 ms | 1.09× |
| Route model and benchmark compiled, lights as a class | 385 ms | 2.74× |
| The same, instances and string constants cached | 290 ms | 3.64× |

Factors are against the first row; against the interpreter with the same class, the last
row is 3.3 times as fast.

Size, web, brotli 11: R3 (stage A and the linker settings, interpreter only) 1.87 MB, R5
(R3 with Lichtpost's 53 functions compiled) 1.88 MB. Stage B cost 60 KB for the same scripts;
compiled C++ costs 10 KB.

Two changes to Lichtpost came with it: its route model keeps lights as a small class with
typed fields instead of dictionaries (`light.x` was a hashed lookup on every tick for
every light), and the layout test turns them back into dictionaries for its frozen hashes.

## Direct engine calls (2026-11-24)

With Godot's sources (`gen_cpp.py ... --godot <source>`), calls of engine methods and
reads and writes of engine properties no longer go by name. The dump records, for every
call and property whose object has a static engine class, what the engine resolves it to
(the binding class, argument count and default values; the property's setter, getter and
index). `cpp_engine.py` reads the sources once: the member function pointer each
`bind_method()` binds, every class's header, namespace, parent and public methods. A call
becomes `GDScriptNative::invoke(object, &Class::method, {...})`, the binder's own
argument conversion (`call_with_variant_args` and friends) on that pointer: no MethodBind,
no lookup by name. Methods bound from a class's protected or private part, vararg methods
and defaults the generator cannot write stay calls by name.

69 of Lichtpost's functions compile (more than before: property writes such as
`label.text = ...` and `body.position.y = ...` and `Class.new()` now work), with 87
direct engine calls against 25 remaining calls by name. Replays match on macOS with the
shaken engine below, and the web build plays.

`bytecode_usage.py --compiled <gen_cpp's usage.json>` leaves out the compiled functions,
whose bytecode no longer runs, and `gen_cpp.py` adds every name its code still looks up.

| Engine (R3 settings) | bindings removed | raw | brotli 11 |
| --- | ---: | ---: | ---: |
| R5, 53 functions compiled, engine calls by name | 13,330 | 6.13 MB | 1.88 MB |
| R7d, 69 compiled, engine calls direct, shaken without the compiled functions | 13,411 | 6.12 MB | 1.88 MB |

The size does not move. 81 more bindings go, but each direct call instantiates the binder's
conversion for its own member function pointer, about what the method bind it replaces
cost. The bindings that stay are kept by the properties scenes store and by the bytecode
of the 36 functions that do not compile yet.

Found on the way:

- The bytecode loader resolved the method binds of every function in a file, compiled or
  not, and refused the script when one was missing: compiled functions now accept missing
  ones. Without that, the shaken build looped until it ran out of memory.
- A builtin type the generator did not know (`PackedByteArray()`) fell back to a call by
  name on the script's own object and returned null; unknown constructors now keep the
  function as bytecode, and methods on typed builtin values do too, since calling them on
  a `Variant` copy would lose the change.
- `TextureRect.new()` is neither a singleton nor a static method: engine classes are now
  created through `ClassDB::instantiate()`.

What would make direct calls pay: calling with typed C++ arguments instead of boxed
`Variant`s (`object->set_text(value)`), so no conversion template is instantiated per
method, and compiling every function, so neither the bytecode's tables nor the VM remain.

## How it works

`dump_ast.gd`, run on an engine with the compiler and the patch, writes per script the
analyzed syntax tree as JSON (`GDScriptBytecodeWriter.ast()`): every node with its
`type_constraint` (kind, builtin type, native class, script class, whether the type is
static), identifiers with their source (local, member, constant, native class, ...), and
the compiled script's member indices.

`gen_cpp.py <syntax tree dir> <output .inc> [script prefix ...]` writes
`gdscript_native.gen.inc`, which the patched `gdscript_bytecode.cpp` includes:

- statically typed locals and parameters are C++ values (`int64_t`, `double`, `bool`,
  `String`, `Vector2i`, `Array`, `Dictionary`, ...), arithmetic and comparisons on them
  plain C++;
- members, of the script itself and of other script instances whose class is static, are
  read and written in place by index, typed members through `VariantInternal` without a
  type check; a script-typed local caches its instance;
- calls to compiled functions are direct C++ calls with typed arguments; utility
  functions like `absi` call `VariantUtilityFunctions` directly;
- everything else, values without a static type, engine methods, singletons and static
  native methods, goes through the runtime by name, as the VM does (`GDScriptNative` in
  `gdscript_native.h`);
- a function with a construct the generator does not cover stays bytecode, and a call to
  it from compiled code is a call by name. The generator repeats until the set of
  compiled functions is stable.

At load, the bytecode loader looks a function up by its class's fully qualified name and
its name; `GDScriptFunction::call()` runs a match instead of the bytecode. Each compiled
function has a typed body and a `Variant` entry that converts arguments and defaults.

Constants that must stay alive (string literals, constants written as text) are built
once and never freed: static `Variant`s and resources were destroyed after the engine at
exit and crashed it. Resources are loaded on use from the resource cache.

## What is missing

- **Engine calls without boxing.** Direct engine calls (see above) still pass `Variant`s.
- **Coverage.** Not yet compiled: signals as values, `self`, casts, `match`, methods on
  typed builtin values, typed array literals, lambdas, `await`.
- **Matching by name only.** A compiled function runs whenever a loaded function has its
  class and name, whatever its code; a check against the source's hash is missing.
- **Errors.** Invalid accesses print an error and continue with a default value; the VM
  would stop the function. A null script-typed value is not checked before member access.

## Reproduce

In the stage A layout, with the stage A, B and C patches applied:

```sh
./buildmac48.sh AC disable_path_overrides=no          # an engine with the compiler
./outmac48/AC/godot.macos.template_release.arm64 --headless --main-pack <lichtpost>.pck \
  --script dump_ast.gd -- <syntax tree dir>
python3 gen_cpp.py <syntax tree dir> src48/godot/modules/gdscript/gdscript_native.gen.inc \
  --godot src48/godot
GDSCRIPT_NO_COMPILER=1 ./build48.sh R5 ...           # R3's arguments
```
