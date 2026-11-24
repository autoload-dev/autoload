extends RefCounted
## Primitive helpers for variable-length platforms and transient effects.

const Palette = preload("res://main/shared/palette/palette.gd")


static func apply_palette(root: Node3D, palette: Palette) -> void:
	for node in root.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		if mesh.has_meta("palette"):
			mesh.material_override = palette.get(mesh.get_meta("palette") as String) as Material

static func sphere(parent: Node3D, radius: float, at: Vector3, color: Color, palette: Palette) -> MeshInstance3D:
	var node := MeshInstance3D.new()
	var mesh := SphereMesh.new()
	mesh.radius = radius
	mesh.height = radius * 2
	node.mesh = mesh
	node.material_override = palette.material(color)
	node.position = at
	parent.add_child(node)
	return node

static func cylinder(parent: Node3D, radius: float, height: float, at: Vector3, color: Color, palette: Palette) -> MeshInstance3D:
	var node := MeshInstance3D.new()
	var mesh := CylinderMesh.new()
	mesh.top_radius = radius
	mesh.bottom_radius = radius
	mesh.height = height
	mesh.radial_segments = 12
	node.mesh = mesh
	node.material_override = palette.material(color)
	node.position = at
	parent.add_child(node)
	return node

static func box(parent: Node3D, size: Vector3, at: Vector3, color: Color, palette: Palette) -> MeshInstance3D:
	var node := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh.size = size
	node.mesh = mesh
	node.material_override = palette.material(color)
	node.position = at
	parent.add_child(node)
	return node
