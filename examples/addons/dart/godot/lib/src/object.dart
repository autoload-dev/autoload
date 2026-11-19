import 'classes.dart';
import 'embedder.dart';
import 'natives.dart' as natives;
import 'script.dart';

/// The right to be the Dart object of a Godot object.
///
/// Only package:godot creates handles: one for each script object Godot instantiates, and
/// one for each view of an object without a Dart script. A handle serves one object, so a
/// Godot object has at most one script object, the one that holds the script's state.
final class GodotHandle {
  final int _id;
  bool _taken = false;
  bool _released = false;
  GodotObject? _object;

  GodotHandle._(this._id);

  void _take(GodotObject object) {
    if (_taken) {
      throw StateError(
        'A GodotHandle serves one object; Godot creates the script object of '
        'object $_id itself.',
      );
    }
    _taken = true;
    _object = object;
  }
}

/// A Godot object, addressed by its instance ID.
///
/// Methods and properties are reached by their Godot names, with arguments and results
/// converted between Dart and Godot values: `null`, `bool`, `int`, `double`, `String`,
/// [List], [Map], `Vector2`, `Color`, objects and, as callables, Dart functions.
///
/// A script object stops working when Godot ends its script instance, because the
/// object was freed or got another script: its calls then throw a [StateError].
@pragma('vm:entry-point')
class GodotObject {
  final GodotHandle _handle;

  /// Takes [handle], which package:godot passes to the constructor of a script class or
  /// view.
  GodotObject(GodotHandle handle) : _handle = handle {
    handle._take(this);
  }

  /// The object's instance ID, Godot's `get_instance_id()`.
  @pragma('vm:entry-point', 'get')
  int get id => _handle._id;

  int get _liveId {
    if (_handle._released) {
      throw StateError(
        '$runtimeType is no longer the script object of object $id: Godot '
        'freed the object or replaced its script.',
      );
    }
    return _handle._id;
  }

  /// Calls the Godot method [method].
  Object? call(String method, [List<Object?> arguments = const []]) =>
      natives.objectCall(_liveId, method, arguments);

  /// Reads the Godot property [property].
  Object? get(String property) => natives.objectGet(_liveId, property);

  /// Writes the Godot property [property].
  void set(String property, Object? value) =>
      natives.objectSet(_liveId, property, value);

  /// Connects [signal] to [callback], a Dart function taking the signal's arguments.
  void connect(String signal, Function callback) =>
      call('connect', [signal, callback]);

  /// Equal to every view of the same Godot object while neither is released.
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is GodotObject &&
          other.id == id &&
          !_handle._released &&
          !other._handle._released;

  @override
  int get hashCode => id.hashCode;

  @override
  String toString() => '$runtimeType#$id';
}

/// The handles of script objects whose constructors are running, by object ID.
final Map<int, GodotHandle> _constructing = {};

/// Creates the object of [script] for the Godot object [id], which Godot is giving a
/// script instance.
@pragma('vm:entry-point')
GodotObject _createScript(Script script, int id) {
  final handle = GodotHandle._(id);
  _constructing[id] = handle;
  try {
    return runScriptCode(() => script.create(handle));
  } finally {
    _constructing.remove(id);
  }
}

/// The Dart object of the Godot object [id], whose class and its ancestors are
/// [classes] and which has no Dart script instance: the script object its constructor
/// is creating, or its most derived view.
@pragma('vm:entry-point')
GodotObject _wrapObject(int id, List<Object?> classes) {
  final constructing = _constructing[id]?._object;
  if (constructing != null) {
    return constructing;
  }
  for (final name in classes) {
    final view = views[name as String];
    if (view != null) {
      return view(GodotHandle._(id));
    }
  }
  return GodotObject(GodotHandle._(id));
}

/// Releases [object], whose script instance Godot ended.
@pragma('vm:entry-point')
void _releaseScript(GodotObject object) => object._handle._released = true;
