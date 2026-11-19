extends MarginContainer
## Presets, buttons and stats inside the safe area; emits what the player asks for and owns
## no simulation state.

signal preset_selected(index: int)
signal pause_toggled(paused: bool)
signal clear_requested

const BASE_INSETS := Vector4(20, 16, 20, 16)
const CHIP_HEIGHT := 46

@onready var title_panel: PanelContainer = $Layout/Top/TitlePanel
@onready var stats_label: RichTextLabel = $Layout/Top/StatsPanel/Stats
@onready var hint: Label = $Layout/Bottom/Hint
@onready var presets: HBoxContainer = $Layout/Bottom/Presets
@onready var actions: HBoxContainer = $Layout/Bottom/Actions
@onready var pause_button: Button = $Layout/Bottom/Actions/Pause
@onready var clear_button: Button = $Layout/Bottom/Actions/Clear
var _preset_group := ButtonGroup.new()


func _ready() -> void:
	pause_button.toggled.connect(_on_pause_toggled)
	clear_button.pressed.connect(clear_requested.emit)
	get_viewport().size_changed.connect(_layout_safe_area)
	_layout_safe_area()


## One chip per preset name; the selected one stays pressed.
func set_presets(names: Array, selected: int) -> void:
	for chip in presets.get_children():
		chip.queue_free()
	for index in names.size():
		var chip := Button.new()
		chip.text = names[index]
		chip.toggle_mode = true
		chip.button_group = _preset_group
		chip.button_pressed = index == selected
		chip.focus_mode = Control.FOCUS_NONE
		chip.custom_minimum_size = Vector2(0, CHIP_HEIGHT)
		chip.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		chip.pressed.connect(preset_selected.emit.bind(index))
		presets.add_child(chip)


func set_paused(value: bool) -> void:
	pause_button.set_pressed_no_signal(value)
	_label_pause(value)


func update_stats(stats: Dictionary) -> void:
	stats_label.text = "[right]%d×%d cells\n[color=#f3d58a]%d[/color] steps/frame\n[color=#f3d58a]%.2f M[/color] cell updates/frame\n[color=#f3d58a]%d[/color] fps[/right]" % [
		stats.width, stats.height, stats.steps, stats.updates / 1e6, stats.fps,
	]


func _on_pause_toggled(paused: bool) -> void:
	_label_pause(paused)
	pause_toggled.emit(paused)


func _label_pause(paused: bool) -> void:
	pause_button.text = "Resume" if paused else "Pause"


## Keeps the controls out of notches, rounded corners and system bars on phones; a desktop
## window has none, and its screen's safe area would only reserve room for the Dock.
func _layout_safe_area() -> void:
	var insets := BASE_INSETS
	if OS.has_feature("mobile"):
		# The display's safe area is in screen pixels; the layout is in canvas units.
		var safe := Rect2(DisplayServer.get_display_safe_area())
		safe.position -= Vector2(DisplayServer.window_get_position())
		var to_canvas := get_viewport().get_final_transform().affine_inverse()
		insets += safe_insets(safe, to_canvas, get_viewport().get_visible_rect().size)
	for index in range(4):
		add_theme_constant_override(["margin_left", "margin_top", "margin_right", "margin_bottom"][index], int(insets[index]))


## Left, top, right and bottom insets that keep a visible canvas inside safe, a rectangle in
## window pixels that to_canvas maps into canvas units.
static func safe_insets(safe: Rect2, to_canvas: Transform2D, visible: Vector2) -> Vector4:
	if not safe.has_area():
		return Vector4.ZERO
	var lead := (to_canvas * safe.position).max(Vector2.ZERO)
	var trail := (visible - to_canvas * safe.end).max(Vector2.ZERO)
	return Vector4(lead.x, lead.y, trail.x, trail.y)
