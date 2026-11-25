extends Node3D
## Transient effects own their lifetimes; none of these values feed gameplay.

const Primitives = preload("res://main/shared/primitives.gd")
const Palette = preload("res://main/shared/palette/palette.gd")
const IVORY := Color("fff1d2")
const MOSS := Color("83b493")
const ORANGE := Color("ef9b52")
const CORAL := Color("d76866")

var palette: Palette
var reduced_motion := false
var landing := 0.0
var kick := 0.0
var route_length := 180000
var sparks: Array[Spark] = []
var parcel_tweens: Array[Tween] = []


func configure(colors: Palette, finish: int) -> void:
	palette = colors
	route_length = finish
	landing = 0.0
	kick = 0.0
	clear()


func clear() -> void:
	for tween in parcel_tweens:
		if tween.is_valid():
			tween.kill()
	parcel_tweens.clear()
	for child in get_children():
		child.queue_free()
	sparks.clear()


func set_reduced(value: bool) -> void:
	reduced_motion = value
	if value:
		clear()


func react(event: String, at: Vector3) -> void:
	match event:
		"jump": _burst(at, IVORY, 5)
		"land":
			landing = 1.0
			_burst(Vector3(at.x, 0.1, 0), MOSS, 6)
		"light": _burst(at + Vector3(0, 0.8, 0), ORANGE, 5)
		"lost":
			kick = 1.0
			_burst(Vector3(at.x, maxf(0.0, at.y) + 0.5, 0), CORAL, 10)
		"delivered":
			_burst(Vector3(at.x + 1, 2, 0), ORANGE, 18)
			if not reduced_motion:
				var parcel := _sphere(self, 0.2, Vector3(at.x, 1.3, 0), ORANGE)
				var tween := create_tween().bind_node(parcel)
				parcel_tweens.append(tween)
				tween.tween_property(parcel, "position", Vector3(route_length / 1000.0 + 2, 2.5, 0.6), 0.65).set_trans(Tween.TRANS_SINE)
				tween.tween_callback(parcel.queue_free)


func advance(delta: float) -> void:
	landing = move_toward(landing, 0.0, delta * 4)
	kick = move_toward(kick, 0.0, delta * 4)
	_animate_sparks(delta)


func _burst(at: Vector3, color: Color, count: int) -> void:
	if reduced_motion:
		return
	for index in range(count):
		var mote := _sphere(self, 0.06, at, color)
		var angle := float(index) * TAU / count
		sparks.append(Spark.new(mote, Vector3(cos(angle), absf(sin(angle)) + 0.5, 0.2) * 2))


func _animate_sparks(delta: float) -> void:
	for index in range(sparks.size() - 1, -1, -1):
		var spark: Spark = sparks[index]
		if not is_instance_valid(spark.node):
			sparks.remove_at(index)
			continue
		spark.life -= delta
		spark.node.position += spark.velocity * delta
		spark.velocity.y -= delta * 5
		spark.node.scale = Vector3.ONE * maxf(0.0, spark.life * 2)
		if spark.life <= 0:
			spark.node.queue_free()
			sparks.remove_at(index)


func _sphere(parent: Node3D, radius: float, at: Vector3, color: Color) -> MeshInstance3D:
	return Primitives.sphere(parent, radius, at, color, palette)


## A mote of a burst, flying until its life runs out.
class Spark:
	var node: MeshInstance3D
	var life := 0.5
	var velocity: Vector3

	func _init(mote: MeshInstance3D, start: Vector3) -> void:
		node = mote
		velocity = start
