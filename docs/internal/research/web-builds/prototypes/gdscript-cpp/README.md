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

- **Engine calls are still by name.** Calls of engine methods and native property access
  go through `Variant::callp()` and `get_named()`, so they need the method binds and gain
  nothing for tree shaking yet. The next step is to call them through member function
  pointers (`call_with_variant_args` and friends with `&Class::method`), taken from the
  `ClassDB::bind_method()` statements `shake_bindings.py` already parses; then a compiled
  project needs only the bindings that scenes, resources and the remaining dynamic calls
  name, and once every function compiles, not the GDScript VM.
- **Coverage.** Not yet compiled: property writes on native objects (18 functions, mostly
  `label.text = ...`), signals as values, `self`, inherited native properties, casts,
  `match`, typed array literals, lambdas, `await`.
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
python3 gen_cpp.py <syntax tree dir> src48/godot/modules/gdscript/gdscript_native.gen.inc
GDSCRIPT_NO_COMPILER=1 ./build48.sh R5 ...           # R3's arguments
```
