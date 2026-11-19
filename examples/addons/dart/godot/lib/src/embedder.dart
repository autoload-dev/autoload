/// The functions the Dart language extension calls. A project's generated entry point
/// registers its scripts here; the extension then describes and calls them. Script
/// objects are created in object.dart, which alone creates GodotHandles.
library;

import 'dart:async';

import 'classes.dart';
import 'natives.dart' as natives;
import 'object.dart';
import 'script.dart';

final Map<String, Script> _scripts = {};

/// Runs script code with `print` writing to Godot's output, and errors that no code
/// awaits, such as those of a callback's futures, reported as Godot errors.
final Zone _zone = Zone.current.fork(
  specification: ZoneSpecification(
    print: (self, parent, zone, line) => natives.godotPrint(line),
    handleUncaughtError: (self, parent, zone, error, stackTrace) =>
        natives.godotError('Dart: uncaught $error\n$stackTrace'),
  ),
);

/// Runs script code with [_zone]'s `print` and error handling.
R runScriptCode<R>(R Function() code) => _zone.run(code);

/// Registers the scripts of a project by resource path, such as `res://main/mover.dart`.
void registerScripts(Map<String, Script> scripts) => _scripts.addAll(scripts);

/// The script at [path] and its description, or null when no script is registered
/// there. The extension passes the script back to create and call its objects.
@pragma('vm:entry-point')
List<Object>? describeScript(String path) {
  final script = _scripts[path];
  return script == null ? null : [script, ...script.describe()];
}

/// Calls [name] on the object [object] of [script].
@pragma('vm:entry-point')
Object? callScript(
  Script script,
  GodotObject object,
  String name,
  List<Object?> arguments,
) => _zone.run(() => script.dispatch(object, name, arguments));

/// The names of the Godot classes package:godot has views of, for new scripts.
@pragma('vm:entry-point')
List<String> viewClasses() => viewNames;

/// Calls the Dart function [function], which Godot calls as a callable.
@pragma('vm:entry-point')
Object? callFunction(Function function, List<Object?> arguments) =>
    _zone.run(() => Function.apply(function, arguments));

/// The hash code of [object], which agrees with its `==`.
@pragma('vm:entry-point')
int hashOf(Object object) => object.hashCode;

/// A map of [keys] to [values], from a Godot dictionary.
@pragma('vm:entry-point')
Map<Object?, Object?> mapOf(List<Object?> keys, List<Object?> values) =>
    Map.fromIterables(keys, values);
