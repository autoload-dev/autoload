import 'package:godot/godot.dart';

/// Implements no callbacks, so Godot calls none.
class Plain extends Node {
  Plain(super.handle);
}

final script = Script(Plain.new);
