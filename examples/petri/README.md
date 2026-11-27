# Petri

A petri dish on a phone screen. Tap it to drop a culture of a Gray-Scott
reaction-diffusion field and watch the culture grow into corals, fingerprints,
rings or dividing spots. Petri shows an application on a **source-built engine with a C++
module**: the simulation is `GrayScottField`, a class that the `reaction_diffusion` module of
the engine `simulation` adds, and the application packages that engine instead of the
official build. The engine lives apart from Petri, in
[`examples/engines/simulation/`](../engines/simulation), where any application can name it.

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

Run these commands from the repository root on macOS or Linux. Every Petri target
names the engine `simulation`, built from the Godot 4.7.2 sources with the module, so no
command needs a flag. The first command compiles that editor and runtime; Bazel caches
the result. With `--config=buildbuddy`, a Mac compiles Petri's Linux editor on
BuildBuddy's Linux executors and runs its editor actions there; the engine's lock file
pins every recipe, so no host configures them.

1. `bazel run //examples/petri:run` opens the dish. Tap it.
2. `bazel test //examples/petri/...` validates the scripts and runs the field, dish,
   layout and scene suites. All pass.
3. `bazel build //examples/petri:app --@autoload_rules_godot//godot:macos_signing=adhoc`
   on macOS, or without the signing flag on Linux, builds the desktop app with the
   source-built runtime. Find its bundle and archive under `bazel-bin/examples/petri/`.
4. `bazel run //examples/petri:edit` opens the project in the source-built editor;
   `bazel run //examples/petri:test_edit` opens the test context with GdUnit and the
   suites.
5. `bazel run //examples/petri:update` writes missing sidecars and node IDs into the
   checkout; `test_update` does the same for the tests.

`bazel test //examples/...` builds Petri with its engine beside the other examples on
the official engine `godot`, which has no `GrayScottField`, so a Petri target without
`engine = "simulation"` would fail to parse Petri's scripts.

## How the parts connect

| Part | Where | Role |
| --- | --- | --- |
| Module | [`examples/engines/simulation/modules/reaction_diffusion/`](../engines/simulation/modules/reaction_diffusion) | Godot's usual module layout: `config.py`, `SCsub`, `register_types` and the `GrayScottField` class |
| Engine | `godot_engines.engine(name = "simulation")` and its `build` tag in [`MODULE.bazel`](../../MODULE.bazel) | Every slot built from the 4.7.2 release sources, with `gdscript`, `text_server_fb`, `freetype`, `zip` and the module, Compatibility renderer only |
| Lock file | [`examples/engines/simulation/simulation.lock.json`](../engines/simulation/simulation.lock.json) | The build graph of every recipe; on a Mac, `bazel run @simulation//:pin --config=buildbuddy` rewrites them, configuring the Linux recipes on BuildBuddy's executors and the others on the Mac |
| Selection | `engine = "simulation"` in [`BUILD.bazel`](BUILD.bazel) and [`tests/BUILD.bazel`](tests/BUILD.bazel) | Each target that runs Godot selects the engine by name; `MODULE.bazel` registers it beside the official engine `godot` |
| Dish | `main/dish/` | The only scripts that name the module's class: steps the field, maps taps into it, paints the texture |
| HUD | `main/hud/` | Chips, buttons and stats inside the display's safe area |
| Tests | `tests/` | GdUnit suites for the field, the dish, the layout and the composed scene |

`GrayScottField` keeps the field on the CPU: the same seed and steps give the same
`checksum()` on every platform, the suites run without a GPU, and the dish works on
the Compatibility renderer. `get_image()` returns one RGBA8 `Image`, repainted on
each call with a fixed palette, so a script only updates an `ImageTexture`.
`get_value(x, y)` reads the second chemical of one cell.

The engine has a slot for every platform, and its lock file pins every recipe: Android and
iOS builds of Petri need no host configuration either. The
[engine guide](../../rules_godot/docs/public/engine.md#pin-the-recipes) explains pinning.

## Working on Petri

- `bazel test --build_tests_only //examples/petri/...` from the repository root validates the scripts and runs the suites.
- `main/petri.tscn` composes the dish, the scrims that keep the HUD legible over a
  full dish, and the HUD; `main/petri.gd` wires the HUD's requests to the dish.
- Change the module's code under `examples/engines/simulation/modules/reaction_diffusion/`; the next
  Petri build recompiles the module and relinks both engines. Any other change to the
  module, such as to `SCsub` or `config.py`, or an added or removed file, needs a repin with
  `bazel run @simulation//:pin --config=buildbuddy` on a Mac; until then the engine's
  recipes fail with that command.
- Add a preset in `main/dish/dish.gd`; the HUD builds its chips from that list.
- For target placement, read the [project layout guide](../../rules_godot/docs/public/project-layout.md).
