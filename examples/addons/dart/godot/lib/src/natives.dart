// The functions the Dart language extension provides to Dart code. The extension resolves
// these symbols for this library; values cross as Dart objects, which the extension
// converts to and from Godot variants.

import 'dart:ffi';

/// Keeps this library in AOT snapshots, where the extension finds it to resolve its
/// natives.
@pragma('vm:entry-point')
void keepNatives() {}

@Native<Handle Function(Int64, Handle, Handle)>(
  symbol: 'godot_dart_object_call',
)
external Object? objectCall(int id, String method, List<Object?> arguments);

@Native<Handle Function(Int64, Handle)>(symbol: 'godot_dart_object_get')
external Object? objectGet(int id, String property);

@Native<Void Function(Int64, Handle, Handle)>(symbol: 'godot_dart_object_set')
external void objectSet(int id, String property, Object? value);

@Native<Handle Function(Handle)>(symbol: 'godot_dart_singleton')
external Object? singleton(String name);

@Native<Void Function(Handle)>(symbol: 'godot_dart_print')
external void godotPrint(String message);

@Native<Void Function(Handle)>(symbol: 'godot_dart_error')
external void godotError(String message);
