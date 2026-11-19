// Godot's lifecycle callbacks. A script class mixes in the ones it implements; Godot then
// calls them, and turns on processing for Process and PhysicsProcess, as it does for a
// GDScript that defines _process or _physics_process.

import 'object.dart';

/// Godot's `_ready`.
mixin Ready on GodotObject {
  void ready();
}

/// Godot's `_enter_tree`.
mixin EnterTree on GodotObject {
  void enterTree();
}

/// Godot's `_exit_tree`.
mixin ExitTree on GodotObject {
  void exitTree();
}

/// Godot's `_process`.
mixin Process on GodotObject {
  void process(double delta);
}

/// Godot's `_physics_process`.
mixin PhysicsProcess on GodotObject {
  void physicsProcess(double delta);
}

/// Godot's `_input`.
mixin InputHandler on GodotObject {
  void input(GodotObject event);
}
