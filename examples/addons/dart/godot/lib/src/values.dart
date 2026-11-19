// Godot's value types that Dart code reads and writes. The extension creates and reads
// them through their entry points.

/// A 2D vector, Godot's `Vector2`.
@pragma('vm:entry-point')
final class Vector2 {
  @pragma('vm:entry-point', 'get')
  final double x;
  @pragma('vm:entry-point', 'get')
  final double y;

  @pragma('vm:entry-point', 'call')
  const Vector2(this.x, this.y);

  Vector2 operator +(Vector2 other) => Vector2(x + other.x, y + other.y);
  Vector2 operator *(double factor) => Vector2(x * factor, y * factor);

  @override
  bool operator ==(Object other) =>
      other is Vector2 && other.x == x && other.y == y;

  @override
  int get hashCode => Object.hash(x, y);

  @override
  String toString() => '($x, $y)';
}

/// An RGBA color, Godot's `Color`.
@pragma('vm:entry-point')
final class Color {
  @pragma('vm:entry-point', 'get')
  final double r;
  @pragma('vm:entry-point', 'get')
  final double g;
  @pragma('vm:entry-point', 'get')
  final double b;
  @pragma('vm:entry-point', 'get')
  final double a;

  @pragma('vm:entry-point', 'call')
  const Color(this.r, this.g, this.b, [this.a = 1]);

  @override
  bool operator ==(Object other) =>
      other is Color &&
      other.r == r &&
      other.g == g &&
      other.b == b &&
      other.a == a;

  @override
  int get hashCode => Object.hash(r, g, b, a);

  @override
  String toString() => '($r, $g, $b, $a)';
}
