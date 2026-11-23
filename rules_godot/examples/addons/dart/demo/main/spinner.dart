import 'dart:math';

import 'package:godot/godot.dart';

/// Turns once every two seconds, in Godot's process callback.
class Spinner extends Node2D with Process {
  Spinner(super.handle);

  @override
  void process(double delta) => rotation = (rotation + pi * delta) % (2 * pi);
}

final script = Script(Spinner.new);
