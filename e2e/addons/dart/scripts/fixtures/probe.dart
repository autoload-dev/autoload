import 'dart:async';

import 'package:godot/godot.dart';

/// Records what Godot does with a Dart script and answers the suites' calls.
class Probe extends Node2D
    with Ready, EnterTree, ExitTree, Process, PhysicsProcess, InputHandler {
  Probe(super.handle) : _handle = handle {
    early = getNode<Node>('.');
  }

  static Probe? remembered;

  final GodotHandle _handle;

  /// What the constructor got when it asked Godot for its own node.
  Node? early;

  int readies = 0;
  int entries = 0;
  int exits = 0;
  int frames = 0;
  int physicsFrames = 0;
  List<String> inputs = [];
  int renames = 0;
  int microtasks = 0;
  int timers = 0;

  @override
  void ready() {
    readies++;
    connect('renamed', () => renames++);
  }

  @override
  void enterTree() => entries++;

  @override
  void exitTree() => exits++;

  @override
  void process(double delta) => frames++;

  @override
  void physicsProcess(double delta) => physicsFrames++;

  @override
  void input(GodotObject event) =>
      inputs.add(event.call('get_class') as String);

  Map<String, Object> counts() => {
    'readies': readies,
    'entries': entries,
    'exits': exits,
    'frames': frames,
    'physics_frames': physicsFrames,
    'inputs': inputs,
    'renames': renames,
    'microtasks': microtasks,
    'timers': timers,
  };

  void schedule() {
    scheduleMicrotask(() => microtasks++);
    Timer(const Duration(milliseconds: 1), () => timers++);
  }

  void onVisibilityChanged() {}

  /// Connects a method's tear-off, and disconnects it with another tear-off of the method:
  /// whether it was connected before and after.
  List<bool> reconnect() {
    connect('visibility_changed', onVisibilityChanged);
    final before = call('is_connected', [
      'visibility_changed',
      onVisibilityChanged,
    ]);
    call('disconnect', ['visibility_changed', onVisibilityChanged]);
    final after = call('is_connected', [
      'visibility_changed',
      onVisibilityChanged,
    ]);
    return [before as bool, after as bool];
  }

  /// Constructs a second Probe with this one's handle: the error's type.
  String clone() {
    try {
      Probe(_handle);
      return 'created';
    } on StateError {
      return 'StateError';
    }
  }

  /// Uses [remembered], whose script instance the suite ended: whether it still works.
  String useRemembered() {
    try {
      remembered!.get('name');
      return 'works';
    } on StateError {
      return 'released';
    }
  }

  Vector2 move(double x) => position = position + Vector2(x, 0);

  String? childName(String path) => getNode<Node>(path)?.name;
}

final script = Script(
  Probe.new,
  methods: {
    'counts': (Probe probe) => probe.counts,
    'schedule': (Probe probe) => probe.schedule,
    'echo': (Probe probe) =>
        (Object? value) => value,
    'move': (Probe probe) => probe.move,
    'reconnect': (Probe probe) => probe.reconnect,
    'same': (Probe probe) =>
        (Object? a, Object? b) => [identical(a, b), a == b],
    'early_is_self': (Probe probe) =>
        () => identical(probe.early, probe),
    'clone': (Probe probe) => probe.clone,
    'remember': (Probe probe) =>
        () => Probe.remembered = probe,
    'use_remembered': (Probe probe) => probe.useRemembered,
    'child_name': (Probe probe) => probe.childName,
    'accepting': (Probe probe) =>
        () => Input.isActionPressed('ui_accept'),
    'myself': (Probe probe) =>
        () => probe,
  },
);
