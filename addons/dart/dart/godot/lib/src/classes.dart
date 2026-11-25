// Typed views of a few Godot classes. Each is a GodotObject whose accessors call Godot by
// name; a script extends the class it attaches to. Classes without a view here are
// reached through GodotObject's call, get and set.

import 'natives.dart' as natives;
import 'object.dart';
import 'values.dart';

class Node extends GodotObject {
  Node(super.handle);

  String get name => get('name') as String;

  /// The node at [path], relative to this node, or null.
  T? getNode<T extends GodotObject>(String path) =>
      call('get_node_or_null', [path]) as T?;

  SceneTree get tree => call('get_tree') as SceneTree;
}

class CanvasItem extends Node {
  CanvasItem(super.handle);
}

class Node2D extends CanvasItem {
  Node2D(super.handle);

  Vector2 get position => get('position') as Vector2;
  set position(Vector2 value) => set('position', value);

  double get rotation => get('rotation') as double;
  set rotation(double value) => set('rotation', value);
}

class Control extends CanvasItem {
  Control(super.handle);
}

class Label extends Control {
  Label(super.handle);

  String get text => get('text') as String;
  set text(String value) => set('text', value);
}

class BaseButton extends Control {
  BaseButton(super.handle);

  /// Calls [callback] whenever the button is pressed.
  void onPressed(void Function() callback) => connect('pressed', callback);
}

class Button extends BaseButton {
  Button(super.handle);

  String get text => get('text') as String;
  set text(String value) => set('text', value);
}

class SceneTree extends GodotObject {
  SceneTree(super.handle);

  /// Ends the game with [exitCode] at the end of the frame.
  void quit([int exitCode = 0]) => call('quit', [exitCode]);
}

/// Godot's `DisplayServer` singleton.
abstract final class DisplayServer {
  static final GodotObject _server =
      natives.singleton('DisplayServer') as GodotObject;

  /// The display server's name: `headless` when Godot runs without a display.
  static String get name => _server.call('get_name') as String;
}

/// Godot's `Input` singleton.
abstract final class Input {
  static final GodotObject _input = natives.singleton('Input') as GodotObject;

  static bool isActionPressed(String action) =>
      _input.call('is_action_pressed', [action]) as bool;
}

/// A view and the Godot class it is of.
final class _View<T extends GodotObject> {
  final String name;
  final T Function(GodotHandle handle) create;

  const _View(this.name, this.create);

  /// Whether a script class of type [S] extends this view.
  bool isBaseOf<S>() => <S>[] is List<T>;
}

/// The views above, each after the views that extend it. Each names its type, which
/// [_View.isBaseOf] tests; inferred from the list's type it would be GodotObject.
const List<_View> _views = [
  _View<Button>('Button', Button.new),
  _View<BaseButton>('BaseButton', BaseButton.new),
  _View<Label>('Label', Label.new),
  _View<Control>('Control', Control.new),
  _View<Node2D>('Node2D', Node2D.new),
  _View<CanvasItem>('CanvasItem', CanvasItem.new),
  _View<SceneTree>('SceneTree', SceneTree.new),
  _View<Node>('Node', Node.new),
  _View<GodotObject>('Object', GodotObject.new),
];

/// The views by Godot class name, for objects that come from Godot.
final Map<String, GodotObject Function(GodotHandle handle)> views = {
  for (final view in _views) view.name: view.create,
};

/// The Godot class names that have views.
List<String> get viewNames => [for (final view in _views) view.name];

/// The Godot class a script class of type [T] extends: that of its most derived view.
String godotClassOf<T>() =>
    _views.firstWhere((view) => view.isBaseOf<T>()).name;
