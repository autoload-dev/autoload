# simulation

The engine `simulation`: Godot 4.7.2 from its release sources with the
`reaction_diffusion` module, whose `GrayScottField` class steps a Gray-Scott
reaction-diffusion field. [Petri](../../petri/README.md) runs on it; any application in
the repository can name it with `engine = "simulation"`.

| Part | Where | Role |
| --- | --- | --- |
| Module | [`modules/reaction_diffusion/`](modules/reaction_diffusion) | Godot's usual module layout: `config.py`, `SCsub`, `register_types` and the class |
| Engine | `godot_engines.engine(name = "simulation")` and its `build` tag in [`MODULE.bazel`](../../../MODULE.bazel) | Every slot built from the release sources, with `gdscript`, `text_server_fb`, `freetype`, `zip` and the module, Compatibility renderer only |
| Lock file | [`simulation.lock.json`](simulation.lock.json) | The build graphs of the Linux and macOS recipes; `bazel run @simulation//:pin_linux --config=buildbuddy` and `bazel run @simulation//:pin_macos` rewrite them |

A changed `SCsub` or `config.py`, or an added or removed module file, needs those repins;
until then the engine's recipes fail with the command.
