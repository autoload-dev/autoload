# GDScript ahead of time, specialized VM (prototype, stage B)

Turn a project's GDScript bytecode (stage A, `../gdscript-bytecode/`) into C++ compiled
into the engine, by specializing Godot's own VM for each function. Throwaway code against
Godot 4.8-beta1 with the stage A patch; not part of the ruleset.

## Result (2026-11-24)

Lichtpost runs specialized on macOS and in the browser. Its three replays give the same
results as the interpreter, and the web build plays.

| Engine (R3 settings: tree-shaken, VFE, no RTTI) | raw | gzip -9 | brotli 11 |
| --- | ---: | ---: | ---: |
| R3, interpreter | 6.09 MB | 2.42 MB | 1.87 MB |
| R4, Lichtpost's 137 functions specialized | 6.35 MB | 2.50 MB | 1.93 MB |

Speed, macOS arm64, `bench.gd` (3,000 runs of Lichtpost's route model, 459,000 ticks, best
of five, less a run with zero runs):

| Engine | GDScript time | |
| --- | ---: | ---: |
| MB0, interpreter | 983 ms | 1.00× |
| MB1, Lichtpost specialized | 793 ms | 1.24× |
| MB2, Lichtpost and the benchmark loop specialized | 783 ms | 1.26× |

Specializing costs 60 KB brotli and buys a quarter. A sample of MB2 shows why it buys no
more: the VM's dispatch is gone, but its work is not. About 23 % of the time is the setup
of `GDScriptFunction::call()` for calls by name, and about 40 % is `Dictionary` and named
access: hashing `StringName`s and `Variant`s for `light.x`, `light.taken` and members of
other scripts' instances. The bytecode does not know the types those accesses could use;
it lost them in Godot's code generator (see stage A's notes on static typing). A compiler
that removes this work has to start from the typed syntax tree, where `light` would be a
class with fields and `step()` a direct call, and would then also call engine methods
directly instead of through method binds, which is what makes their registrations
removable.

## How it works

`gen_aot.py <godot source> <bytecode dir> <output dir>` writes three includes that
`godot-4.8-beta1-gdscript-aot.patch` (on top of stage A) pulls into `gdscript_vm.cpp`:

- every instruction becomes a copy of its opcode's body from `gdscript_vm.cpp`, behind
  its own label inside `GDScriptFunction::call()`; the generator finds the instructions
  with lengths derived from Godot's disassembler (`opcodes.py`) and reads the bytecode
  with stage A's reader (`read_bytecode.py`);
- the copies use `aot_ip`, a local set to each instruction's literal address. The VM's
  `ip` cannot serve: its address goes to `GDScriptLanguage::enter_function()`, so the
  compiler must reload it after every call. `aot_ip` is written back to `ip` before the
  copies leave (errors, `await`, fallback to the interpreter);
- `_code_ptr` names a `static const` copy of the function's code, so operand reads, stack
  addresses and jump targets fold to constants. Only `OPCODE_OPERATOR`, which caches into
  the code, keeps reading the live code;
- `DISPATCH_OPCODE` jumps to a per-function `switch (aot_ip)` of direct `goto`s, which a
  constant `aot_ip` reduces to a direct jump. A first version dispatched through tables of
  label addresses (`goto *table[ip]`): clang merges all indirect gotos of a function into
  one block with every label as successor, and with 3,000 labels did not finish
  compiling in ten minutes. With switches the file compiles in under a minute;
- the bytecode loader looks up each loaded function's code among the copies (exact
  comparison); a match starts at its labels, anything else runs in the interpreter.

Release builds only: the copies use the release definitions of the VM's operand macros.

## Reproduce

In the stage A layout, with the AOT patch applied:

```sh
python3 gen_aot.py src48/godot <bytecode dir> src48/godot/modules/gdscript
GDSCRIPT_NO_COMPILER=1 ./build48.sh R4 ...      # R3's arguments, see stage A's notes
```

`bench.gd` needs a pack with it next to Lichtpost's scripts, compiled to bytecode like the
rest; it uses only engine calls Lichtpost uses, so tree-shaken engines run it. Time it
from outside with `--script res://bench.gd -- <runs>`.
