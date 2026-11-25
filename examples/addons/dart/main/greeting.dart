import 'package:godot/godot.dart';

/// Greets from Dart, and answers GDScript's calls of `greet`.
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
