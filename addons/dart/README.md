# Dart scripts add-on

Write Godot scripts in [Dart](https://dart.dev). A `.dart` file attaches to a node as a
`.gd` file does; Godot calls its lifecycle callbacks and its methods, and the script reaches
its node, other objects and Godot singletons. The build compiles a project's scripts ahead of
time with the Dart SDK and embeds the Dart VM in the project's extension:

```dart
import 'package:godot/godot.dart';

class Spinner extends Node2D with Process {
  Spinner(super.handle);

  @override
  void process(double delta) => rotation += delta;
}

final script = Script(Spinner.new);
```

## Getting started

1. Install Bazelisk and a native C/C++ toolchain: Xcode Command Line Tools on macOS or
   GCC/Clang on Linux. Bazel downloads the Dart SDK.
   From the repository root, run:

   ```sh
   bazel run //examples/addons/dart:run
   ```

   The first build compiles the Dart VM from its sources, several hundred C++ files.
2. The window shows **Dart says: Hello, Godot**, a button that counts its presses and a
   turning square, each driven by a Dart script.
3. Run the add-on's own tests without a graphical display:

   ```sh
   bazel test //dart/...
   ```

   They run the exported demo, GdUnit suites that check callbacks, values in both
   directions, calls into Godot and Dart functions as signal targets, and a native test of
   the embedded VM.

## Write scripts

A script file declares a class that extends the Godot class it attaches to and a top-level
`script`, a `Script` whose first argument is the class's constructor. `package:godot` provides views of `Node`, `CanvasItem`, `Node2D`, `Control`, `Label`,
`BaseButton`, `Button` and `SceneTree`, with `Input` and `DisplayServer` for singletons.
Every object answers Godot's names through `call`, `get` and `set`:

```dart
class Greeting extends Label with Ready {
  Greeting(super.handle);

  @override
  void ready() => text = greet('Godot');

  String greet(String name) => 'Dart says: Hello, $name';
}

final script = Script(
  Greeting.new,
  methods: {'greet': (Greeting greeting) => greeting.greet},
);
```

- **Callbacks.** Godot calls `_ready`, `_enter_tree`, `_exit_tree`, `_process`,
  `_physics_process` and `_input` only for a class that mixes in `Ready`, `EnterTree`,
  `ExitTree`, `Process`, `PhysicsProcess` or `InputHandler`, as it calls them only for a
  GDScript that defines them. `Process` and `PhysicsProcess` turn processing on.
- **Methods.** `methods` names what GDScript, scenes and signals may call, such as
  `greeting.call("greet", "Bazel")`. The map is explicit because AOT-compiled Dart has no
  reflection.
- **Values.** `null`, `bool`, `int`, `double`, `String`, `List`, `Map`, `Vector2`, `Color`
  and objects cross in both directions; a `StringName` or `NodePath` arrives as `String`.
  An object whose script is Dart arrives as that script's object, any other as a view of
  its most derived class with a view. A Dart function becomes a `Callable`, so `connect('pressed', () => ...)`
  connects a closure.
- **One object per instance.** Godot creates a script's Dart object when it instantiates
  the script, passing the constructor a `GodotHandle` that only `package:godot` issues and
  that serves one object, so Dart code cannot create a second object with its own state.
  Every way the Godot object reaches Dart, the constructor's own calls included, yields
  that object, and views of the same Godot object compare equal to it. When Godot frees
  the object or replaces its script, the Dart object stops working: its calls throw a
  `StateError`.
- **Output.** `print` writes to Godot's output; an uncaught exception is a Godot error
  with the Dart stack.

## Reuse the add-on

Declare a project's scripts with `godot_dart_extension` in the package of its
`project.godot`, and list the extension in the `deps` of the `godot_resources` whose scenes
use the scripts. A script's resource path is its path below that package, so declare the
scripts' resources with the `prefix` of their directory:

```starlark
load("//dart:defs.bzl", "godot_dart_extension")

godot_dart_extension(
    name = "dart",
    srcs = ["//examples/addons/dart/main:scripts"],
)
```

The macro writes an entry point that registers each script under its resource path,
compiles it with the scripts into an AOT snapshot with [rules_dart](https://github.com/aran/rules_dart),
and builds a `godot_cc_extension` whose library loads the snapshot from beside itself as
`libdart_scripts.so`. `deps` adds `dart_library` targets that scripts import. A project
has one Dart extension, since Godot registers one language per name.

## How it works

Dart does not distribute its VM as a library. The [module](MODULE.bazel) fetches the
Dart SDK sources of the release that rules_dart compiles with, and
[`dart_sdk.BUILD.bazel`](third_party/dart_sdk.BUILD.bazel) builds the SDK's precompiled
runtime and its `dart_engine.h` embedding API with rules_cc, from the source lists of the
SDK's own GN build. An AOT snapshot runs only on the runtime of its own release, which
checks this when the isolate starts. [`dart_sdk.patch`](third_party/dart_sdk.patch) drops an
unused BoringSSL include, so `dart:io` has no `SecureSocket`, and corrects the macOS
version the runtime reads on Darwin 25 and newer.

The extension's C++ code in [`native/`](dart/native) registers the script language, its
resource loader and saver, and script instances that forward Godot's calls to the Dart
objects; [`package:godot`](dart/godot/lib/godot.dart) holds the Dart side and the natives Dart
code calls Godot through.

## Limits

- The extension runs on macOS and Linux. It has no Android or iOS build; iOS also forbids
  loading a snapshot as a library.
- The editor shows Dart scripts as placeholders, as it does any script that is not a tool
  script, and offers no completion, errors or debugging; the build compiles the scripts and
  reports their errors. A script change takes effect after the next build.
- Scripts declare no exported properties or signals for Godot to list.

## Develop and package

Run from the repository root:

```sh
bazel run //examples/addons/dart:edit
bazel run //examples/addons/dart:update
bazel run //e2e/addons/dart:update
bazel build //examples/addons/dart:pack
```

The [project layout guide](../../rules_godot/docs/public/project-layout.md) explains the separate
add-on, demo and test packages.
