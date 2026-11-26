# simulation

The engine `simulation`: Godot 4.7.2 from its release sources with the
`reaction_diffusion` module, whose `GrayScottField` class steps a Gray-Scott
reaction-diffusion field. [Petri](../../petri/README.md) runs on it; any application in
the repository can name it with `engine = "simulation"`.

| Part | Where | Role |
| --- | --- | --- |
| Module | [`modules/reaction_diffusion/`](modules/reaction_diffusion) | Godot's usual module layout: `config.py`, `SCsub`, `register_types` and the class |
| Source build | `godot_simulation` in [`MODULE.bazel`](../../../MODULE.bazel) | One recipe per Linux and macOS editor and release runtime, with `gdscript`, `text_server_fb`, `freetype`, `zip` and the module, Compatibility renderer only |
| Lock file | [`godot_simulation.lock.json`](godot_simulation.lock.json) | Each recipe's build graph; `bazel run @godot_simulation//:pin --config=buildbuddy` rewrites it |

A changed `SCsub` or `config.py`, or an added or removed module file, needs that repin;
until then the engine's targets fail with the command.
