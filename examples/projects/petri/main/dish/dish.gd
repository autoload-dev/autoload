extends TextureRect
## The petri dish: owns a GrayScottField, steps it every frame and turns pointer input into
## cultures. The texture covers the whole control, so taps map through the drawn rectangle.

const FIELD_WIDTH := 270
const FIELD_HEIGHT := 480
const STEPS_PER_FRAME := 8
const FIELD_SEED := 7
## Steps simulated before the first frame, so the dish opens with grown structure.
const WARM_UP_STEPS := 600
## Small cultures take hold under every preset; large discs collapse under some.
const TAP_RADIUS := 6.0
const DRAG_RADIUS := 4.0
## Feed and kill rates of the Gray-Scott model and the pattern each pair grows from a
## tapped culture; pairs near the edge of the pattern-forming region let small cultures die.
const PRESETS := [
	{"name": "Coral", "feed": 0.0545, "kill": 0.062},
	{"name": "Fingerprints", "feed": 0.037, "kill": 0.060},
	{"name": "Rings", "feed": 0.039, "kill": 0.058},
	{"name": "Spots", "feed": 0.018, "kill": 0.051},
]

var field := GrayScottField.new()
var paused := false
var preset := 0
var _dish_texture: ImageTexture
var _dragging := false


func _ready() -> void:
	field.setup(FIELD_WIDTH, FIELD_HEIGHT, FIELD_SEED)
	apply_preset(0)
	plant_initial_cultures()
	field.step(WARM_UP_STEPS)
	_dish_texture = ImageTexture.create_from_image(field.get_image())
	texture = _dish_texture


func _process(_delta: float) -> void:
	if paused:
		return
	field.step(STEPS_PER_FRAME)
	_dish_texture.update(field.get_image())


func plant_initial_cultures() -> void:
	field.seed_disc(Vector2(FIELD_WIDTH * 0.5, FIELD_HEIGHT * 0.46), 14.0)
	field.seed_disc(Vector2(FIELD_WIDTH * 0.32, FIELD_HEIGHT * 0.30), 8.0)
	field.seed_disc(Vector2(FIELD_WIDTH * 0.70, FIELD_HEIGHT * 0.62), 10.0)
	field.seed_disc(Vector2(FIELD_WIDTH * 0.40, FIELD_HEIGHT * 0.74), 6.0)


func clear() -> void:
	field.clear()
	_refresh()


func apply_preset(index: int) -> void:
	preset = index
	var rates: Dictionary = PRESETS[index]
	field.set_rates(rates.feed, rates.kill)


func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		_dragging = event.pressed
		if event.pressed:
			drop_culture(event.position, TAP_RADIUS)
	elif event is InputEventMouseMotion and _dragging:
		drop_culture(event.position, DRAG_RADIUS)


## Plants a culture around a control-local position; the radius is in field cells.
func drop_culture(at: Vector2, radius: float) -> void:
	field.seed_disc(to_field(at), radius)
	_refresh()


## Maps a control-local position to field cells through the covered texture rectangle.
func to_field(at: Vector2) -> Vector2:
	return covered_to_field(at, size, Vector2(FIELD_WIDTH, FIELD_HEIGHT))


## Where a point of a control falls in a texture that covers the control while keeping its
## aspect, as STRETCH_KEEP_ASPECT_COVERED draws it.
static func covered_to_field(at: Vector2, control_size: Vector2, field_size: Vector2) -> Vector2:
	var scale := maxf(control_size.x / field_size.x, control_size.y / field_size.y)
	var offset := (control_size - field_size * scale) / 2.0
	return (at - offset) / scale


func stats() -> Dictionary:
	return {
		"width": FIELD_WIDTH,
		"height": FIELD_HEIGHT,
		"steps": STEPS_PER_FRAME,
		"updates": FIELD_WIDTH * FIELD_HEIGHT * STEPS_PER_FRAME,
		"fps": Engine.get_frames_per_second(),
	}


## Shows the field now while paused; _process repaints a running dish anyway.
func _refresh() -> void:
	if paused and _dish_texture != null:
		_dish_texture.update(field.get_image())
