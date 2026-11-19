extends Node3D
## Cosmetic pose only. The logical body remains in route_model.

const Primitives = preload("res://main/shared/primitives.gd")
@onready var body: Node3D = $Body
@onready var limbs: Array[Node3D] = [$Body/BackLeg, $Body/FrontLeg, $Body/BackArm, $Body/FrontArm]


func configure(palette: Resource) -> void:
	Primitives.apply_palette(self, palette)


func present(at: Vector3, grounded: bool, mode: String, delivered: bool, time: float, landing: float, reduced: bool) -> void:
	position = at
	var running := grounded and mode == "playing"
	var bounce := absf(sin(time * 18)) * 0.055 if running else 0.0
	body.position.y = bounce if not reduced else 0.0
	var squash := landing * 0.18 if not reduced else 0.0
	body.scale = Vector3(1 + squash, 1 - squash, 1 + squash)
	body.rotation.z = 0.0 if reduced else (-0.1 if not grounded else sin(time * 18) * 0.025)
	if mode == "result" and delivered and not reduced:
		body.position.y = absf(sin(time * 5)) * 0.14
	for index in range(limbs.size()):
		var stride := sin(time * 18 + index % 2 * PI) * 0.65 if running else -0.5
		limbs[index].rotation.z = 0.0 if reduced else stride
