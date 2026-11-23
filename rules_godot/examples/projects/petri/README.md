# Petri

A petri dish on a phone screen. Tap it to drop a culture of a Gray-Scott
reaction-diffusion field and watch the culture grow into corals, fingerprints,
rings or dividing spots. Petri shows a **source-built engine with an owned C++ module**:
the simulation is `GrayScottField`, a class that the `reaction_diffusion` engine
module adds, and the application packages that engine instead of the official build.

```gdscript
var field := GrayScottField.new()
field.setup(270, 480, 7)         # a deterministic, empty dish
field.set_rates(0.0545, 0.062)   # feed and kill: coral
field.seed_disc(Vector2(135, 240), 14.0)
field.step(8)                    # once per frame
texture.update(field.get_image())
```

Petri fits when you want to see how a module, an engine recipe and an application
connect in rules_godot. It does not show native code as a GDExtension; the
[SQLite](../../addons/sqlite/README.md) and [Platform Paths](../../addons/platform_paths/README.md)
add-ons do that.

Tap or drag the dish to drop a culture. The chips switch between **Coral**,
**Fingerprints**, **Rings** and **Spots**, which are feed and kill rates of the
model. **Pause** freezes the dish and **Clear dish** empties it. The panel at the
top right shows the field size, the steps per frame and the frame rate.

## Getting started

Run these commands from `examples/` on macOS or Linux. Every Petri command
takes `--config=petri`, which selects the engine `petri`, built from the
Godot 4.7.2 sources with the module, in place of the prebuilt engine for that
invocation. The first command compiles that editor and runtime; Bazel caches the
result. With `--config=buildbuddy`, a Mac compiles Petri's Linux editor on BuildBuddy's
Linux executors and runs its editor actions there; the engine's lock file pins every
recipe, so no host configures one.

1. `bazel run //projects/petri:run --config=petri` opens the dish. Tap it.
2. `bazel test //projects/petri/... --config=petri` validates the scripts and runs the
   field, dish, layout and scene suites. All pass.
3. `bazel build //projects/petri:app --config=petri --@autoload_rules_godot//godot:macos_signing=adhoc`
   on macOS, or without the signing flag on Linux, builds the desktop app with the
   source-built runtime. Find its bundle and archive under `bazel-bin/projects/petri/`.
4. `bazel run //projects/petri:edit --config=petri` opens the project in the
   source-built editor; `bazel run //projects/petri:test_edit --config=petri` opens
   the test context with GdUnit and the suites.
5. `bazel run //projects/petri:update --config=petri` writes missing sidecars and
   node IDs into the checkout; `test_update` does the same for the tests.

Without `--config=petri` the prebuilt engine has no `GrayScottField`, so Petri's pack,
app and tests are incompatible and `bazel test //...` or `bazel build //...`
skip them, keeping the other examples on the prebuilt engine.

## How the parts connect

| Part | Where | Role |
| --- | --- | --- |
| Module | `engine/modules/reaction_diffusion/` | Godot's usual module layout: `config.py`, `SCsub`, `register_types` and the `GrayScottField` class |
| Engine | `godot_engines.source_build` in [`MODULE.bazel`](../../MODULE.bazel) | One recipe per Linux and macOS slot from the pinned 4.7.2 sources, with `gdscript`, `text_server_fb`, `freetype`, `zip` and the module, Compatibility renderer only |
| Lock file | [`engines/godot_petri.lock.json`](../../engines/godot_petri.lock.json) | Each recipe's build graph; `bazel run @godot_petri//:pin --config=buildbuddy` rewrites it |
| Selection | `build:petri` in [`.bazelrc`](../../.bazelrc) | `--extra_toolchains` registers the hub and `--@autoload_rules_godot//godot:engine=petri` selects its engine, which also marks Petri's targets compatible, through `source_engine.bzl` |
| Dish | `main/dish/` | The only scripts that name the module's class: steps the field, maps taps into it, paints the texture |
| HUD | `main/hud/` | Chips, buttons and stats inside the display's safe area |
| Tests | `tests/` | GdUnit suites for the field, the dish, the layout and the composed scene |

`GrayScottField` keeps the field on the CPU: the same seed and steps give the same
`checksum()` on every platform, the suites run without a GPU, and the dish works on
the Compatibility renderer. `get_image()` returns one RGBA8 `Image`, repainted on
each call with a fixed palette, so a script only updates an `ImageTexture`.
`get_value(x, y)` reads the second chemical of one cell.

The engine recipe covers Linux and macOS; the Android and iOS applications of this
module build the prebuilt engine, which lacks the module. The
[engine guide](../../../docs/public/engine.md#declare-a-source-build) explains how a
source build extends to those platforms.

## Working on Petri

- `python3 -m tools.ci.work run test:example:petri` from the repository root validates the scripts and runs the suites.
- `main/petri.tscn` composes the dish, the scrims that keep the HUD legible over a
  full dish, and the HUD; `main/petri.gd` wires the HUD's requests to the dish.
- Change the module's code under `engine/modules/reaction_diffusion/`; the next
  `--config=petri` build recompiles the module and relinks both engines. A changed
  `SCsub` or `config.py`, or an added or removed file, needs a repin with
  `bazel run @godot_petri//:pin --config=buildbuddy`; until then the engines fail with
  that command.
- Add a preset in `main/dish/dish.gd`; the HUD builds its chips from that list.
- For target placement, read the [project layout guide](../../../docs/public/project-layout.md).
