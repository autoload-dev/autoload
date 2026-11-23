extends Node3D
## Builds only the geometry of one generated island; endpoints are millimetres.

const Primitives = preload("res://main/shared/primitives.gd")
const MOSS := Color("83b493")
const ORANGE := Color("ef9b52")
var palette: Resource

func configure(left: int, right: int, colors: Resource) -> void:
	palette = colors
	var world := self
	var length := (right - left) / 1000.0
	var middle := (left + right) / 2000.0
	_box(world, Vector3(length, 0.7, 2.5), Vector3(middle, -0.55, 0), Color("805b51"))
	_box(world, Vector3(length, 0.25, 2.65), Vector3(middle, -0.125, 0), MOSS)
	# Edge blocks and dangling leaves keep the playable top surface unambiguous.
	for index in range(int(length / 0.8)):
		var x := left / 1000.0 + index * 0.8 + 0.4
		_box(world, Vector3(0.64, 0.25 + index % 3 * 0.12, 0.18), Vector3(x, -0.32, 1.28), MOSS)
		if index % 4 == 0:
			_sphere(world, 0.15, Vector3(x, -0.72, 1.3), Color("3f7979")).scale.y = 2
		if index % 2 == 0:
			_box(world, Vector3(1.3, 0.6 + index % 3 * 0.3, 2.1), Vector3(x, -1, -0.1), Color("6c514d"))
		if index % 5 == 2:
			for leaf in range(3):
				var plant := _sphere(world, 0.12, Vector3(x + leaf * 0.12, 0.05 + leaf * 0.03, -0.9), MOSS)
				plant.scale = Vector3(0.7, 1.8, 0.6)
				plant.rotation.z = -0.5 + leaf * 0.5
	if length > 4:
		var at := left / 1000.0 + 2
		_cylinder(world, 0.05, 1.7, Vector3(at, 0.85, -1.1), Color("805b51"))
		_sphere(world, 0.13, Vector3(at, 1.75, -1.1), ORANGE)

func _box(parent: Node3D, size: Vector3, at: Vector3, color: Color) -> MeshInstance3D:
	return Primitives.box(parent, size, at, color, palette)


func _sphere(parent: Node3D, radius: float, at: Vector3, color: Color) -> MeshInstance3D:
	return Primitives.sphere(parent, radius, at, color, palette)


func _cylinder(parent: Node3D, radius: float, height: float, at: Vector3, color: Color) -> MeshInstance3D:
	return Primitives.cylinder(parent, radius, height, at, color, palette)
