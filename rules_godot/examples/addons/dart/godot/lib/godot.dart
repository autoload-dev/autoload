/// Dart scripts for Godot objects.
///
/// A script file declares one class that extends the Godot class it attaches to and a
/// top-level `script` that describes it:
///
/// ```dart
/// class Mover extends Node2D with Ready, Process {
///   Mover(super.handle);
///
///   @override
///   void ready() => print('Ready at $position');
///
///   @override
///   void process(double delta) => position = position + Vector2(10, 0) * delta;
/// }
///
/// final script = Script(Mover.new);
/// ```
///
/// Godot calls a lifecycle callback only when the class mixes in its interface, such as
/// [Ready] or [Process], as GDScript calls `_ready` only when a script defines it.
///
/// Godot creates the script object when it instantiates the script, passing the
/// constructor a [GodotHandle] that only package:godot issues and that serves one
/// object. So each script instance has exactly one Dart object, which holds its state.
library;

export 'src/callbacks.dart';
export 'src/classes.dart';
export 'src/object.dart';
export 'src/script.dart';
export 'src/values.dart';
