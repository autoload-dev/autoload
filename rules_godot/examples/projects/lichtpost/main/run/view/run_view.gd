extends Node3D
## Composes scene components. Reads the model; never advances or changes it.

const Platform = preload("res://main/components/platform/platform.tscn")
const Pipe = preload("res://main/components/pipe/pipe.tscn")
const Light = preload("res://main/components/light/light.tscn")
const PlatformNode = preload("res://main/components/platform/platform.gd")
const PipeNode = preload("res://main/components/pipe/pipe.gd")
const LightNode = preload("res://main/components/light/light.gd")
const Courier = preload("res://main/components/courier/courier.gd")
const Greenhouse = preload("res://main/components/greenhouse/greenhouse.gd")
const Parallax = preload("res://main/components/parallax/parallax.gd")
const Effects = preload("res://main/components/effects/effects.gd")
const Palette = preload("res://main/shared/palette/palette.gd")
const LevelDefinition = preload("res://main/run/level_definition.gd")
const Route = preload("res://main/rules/route_model.gd")
## Metres the camera keeps visible at least: the route ahead across, the jump arc upward.
const VIEW_WIDTH := 13.0
const VIEW_HEIGHT := 12.0
## Share of the visible width behind the courier; the rest shows the route ahead.
const COURIER_LEAD := 0.2
## Height of the ground line above the bottom edge, as a share of the visible height.
const GROUND_LINE := 0.4
@onready var course: Node3D = $Course
@onready var courier: Courier = $CourierRobot
@onready var camera: Camera3D = $Camera
@onready var greenhouse: Greenhouse = $Greenhouse
@onready var parallax: Parallax = $Parallax
@onready var effects: Effects = $RunEffects
var light_nodes: Array[LightNode] = []
## Metres the camera shows, and the ground line's height on screen; set on resize.
var view_size := Vector2(VIEW_WIDTH, VIEW_HEIGHT)
var ground_y := 0.0
var visual_time := 0.0
var reduced_motion := false


func _ready() -> void:
	get_viewport().size_changed.connect(_frame_camera)
	_frame_camera()


func configure(level: LevelDefinition, model: Route) -> void:
	for child in course.get_children():
		course.remove_child(child)
		child.queue_free()
	light_nodes.clear()
	var palette := level.palette
	var sun: DirectionalLight3D = $Sun
	($Environment as WorldEnvironment).environment = level.environment
	sun.light_color = palette.ivory.albedo_color
	sun.light_energy = level.sun_energy
	courier.configure(palette)
	greenhouse.configure(palette)
	greenhouse.position.x = model.route_length / 1000.0
	parallax.configure(level)
	effects.configure(palette, model.route_length)
	effects.set_reduced(reduced_motion)
	var previous := -5000
	for gap in model.gaps:
		_add_platform(previous, gap.x, palette)
		previous = gap.y
	_add_platform(previous, model.route_length + 8000, palette)
	for at in model.pipes:
		var pipe: PipeNode = Pipe.instantiate()
		course.add_child(pipe)
		pipe.position.x = at / 1000.0
		pipe.configure(palette)
	for item in model.lights:
		var light: LightNode = Light.instantiate()
		course.add_child(light)
		light.position = Vector3(item.x / 1000.0, item.y / 1000.0, 0)
		light_nodes.append(light)


func _add_platform(left: int, right: int, palette: Palette) -> void:
	var platform: PlatformNode = Platform.instantiate()
	course.add_child(platform)
	platform.configure(left, right, palette)


func set_reduced(value: bool) -> void:
	reduced_motion = value
	effects.set_reduced(value)


func react(events: Array[String], model: Route) -> void:
	for event in events:
		effects.react(event, Vector3(model.x / 1000.0, model.y / 1000.0, 0))


## Shows the model with the courier at at, in metres, which may lie between two ticks.
func present(model: Route, at: Vector2, mode: String, paused: bool, delta: float) -> void:
	if not paused:
		visual_time += delta
		effects.advance(delta)
	courier.present(Vector3(at.x, at.y, 0), model.grounded, mode, model.status == "delivered", visual_time, effects.landing, reduced_motion)
	camera.position.x = at.x + view_size.x * (0.5 - COURIER_LEAD)
	camera.h_offset = 0.0 if reduced_motion else sin(visual_time * 65) * effects.kick * 0.07
	parallax.follow(at.x, ground_y)
	for index in range(light_nodes.size()):
		light_nodes[index].present(model.lights[index].taken, visual_time)
	greenhouse.set_delivered(model.status == "delivered")


## Fits VIEW_WIDTH x VIEW_HEIGHT into the viewport, so portrait phones keep the route
## ahead and wide windows keep the jump arc, and puts the ground line at GROUND_LINE.
func _frame_camera() -> void:
	var viewport := get_viewport().get_visible_rect().size.max(Vector2.ONE)
	view_size = viewport * maxf(VIEW_WIDTH / viewport.x, VIEW_HEIGHT / viewport.y)
	camera.size = view_size.y
	# The tilted orthographic camera sees the ground below its centre; lift that line.
	var ground := Vector3(0, -camera.position.y, -camera.position.z).dot(camera.basis.y)
	camera.v_offset = ground + view_size.y * (0.5 - GROUND_LINE)
	ground_y = viewport.y * (1.0 - GROUND_LINE)
