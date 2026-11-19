import 'package:godot/godot.dart';

/// The demo's root: checks that the other scripts ran, and ends a headless run with the
/// result, as the exported test runs it.
class DartDemo extends Control with Ready {
  DartDemo(super.handle);

  @override
  void ready() {
    // Godot readies children before their parent, so the greeting is in place.
    final greeting = getNode<Label>('Layout/Greeting');
    final success =
        greeting != null && greeting.text == 'Dart says: Hello, Godot';
    print(success ? 'DART_DEMO_OK' : 'Dart demo failed');
    if (DisplayServer.name == 'headless') {
      tree.quit(success ? 0 : 1);
    }
  }
}

final script = Script(DartDemo.new);
