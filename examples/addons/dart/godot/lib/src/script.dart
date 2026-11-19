import 'callbacks.dart';
import 'classes.dart';
import 'object.dart';

/// What Godot needs to know about a script class [T]: how to create an instance for a
/// Godot object, and the methods Godot may call by name besides lifecycle callbacks,
/// such as targets of signals connected in a scene.
///
/// ```dart
/// final script = Script(Counter.new, methods: {'increment': (Counter c) => c.increment});
/// ```
final class Script<T extends GodotObject> {
  /// Creates the script's object from the handle of the Godot object it is the script
  /// of: the script class's constructor, such as `Mover.new`.
  final T Function(GodotHandle handle) create;

  /// Godot-callable methods by Godot name: each entry returns the method of an instance.
  final Map<String, Function Function(T script)> methods;

  const Script(this.create, {this.methods = const {}});

  /// The Godot names of the lifecycle callbacks [T] implements.
  List<String> get callbacks => [
    if (<T>[] is List<Ready>) '_ready',
    if (<T>[] is List<EnterTree>) '_enter_tree',
    if (<T>[] is List<ExitTree>) '_exit_tree',
    if (<T>[] is List<Process>) '_process',
    if (<T>[] is List<PhysicsProcess>) '_physics_process',
    if (<T>[] is List<InputHandler>) '_input',
  ];

  /// The script's Godot base class, its callbacks and its methods.
  List<Object> describe() => [
    godotClassOf<T>(),
    callbacks,
    methods.keys.toList(),
  ];

  /// Calls the callback or method [name] of [script], which Godot knows it has.
  Object? dispatch(T script, String name, List<Object?> arguments) {
    switch ((name, script)) {
      case ('_ready', Ready s):
        s.ready();
      case ('_enter_tree', EnterTree s):
        s.enterTree();
      case ('_exit_tree', ExitTree s):
        s.exitTree();
      case ('_process', Process s):
        s.process(arguments[0] as double);
      case ('_physics_process', PhysicsProcess s):
        s.physicsProcess(arguments[0] as double);
      case ('_input', InputHandler s):
        s.input(arguments[0] as GodotObject);
      default:
        return Function.apply(methods[name]!(script), arguments);
    }
    return null;
  }
}
