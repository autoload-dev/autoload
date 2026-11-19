import 'package:godot/godot.dart';

/// Counts its presses: a Dart closure is the target of the button's `pressed` signal.
class Counter extends Button with Ready {
  Counter(super.handle);

  int presses = 0;

  @override
  void ready() => onPressed(() => text = 'Pressed ${++presses} times');
}

final script = Script(
  Counter.new,
  methods: {
    'presses': (Counter counter) =>
        () => counter.presses,
  },
);
