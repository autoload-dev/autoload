extends CanvasLayer
## Routes component signals and screen visibility; owns no gameplay state.

signal start_requested
signal new_route_requested
signal pause_requested
signal options_requested
signal mute_changed(value: bool)
signal motion_changed(value: bool)
@onready var hud = $Root/Margin/Layout/Hud
@onready var title = $Root/Margin/Layout/Center/TitleDialog
@onready var result = $Root/Margin/Layout/Center/ResultDialog
@onready var options = $Root/Margin/Layout/Center/OptionsDialog
@onready var ui_margin: MarginContainer = $Root/Margin


func _ready() -> void:
	title.start_requested.connect(start_requested.emit)
	result.retry_requested.connect(start_requested.emit)
	result.new_route_requested.connect(new_route_requested.emit)
	hud.pause_requested.connect(pause_requested.emit)
	hud.options_requested.connect(options_requested.emit)
	options.closed.connect(options_requested.emit)
	options.mute_changed.connect(mute_changed.emit)
	options.motion_changed.connect(motion_changed.emit)
	get_viewport().size_changed.connect(_layout_safe_area)
	_layout_safe_area()


func _notification(what: int) -> void:
	# The safe area is in screen pixels, so a window move, also onto another screen, shifts it.
	if what == NOTIFICATION_WM_POSITION_CHANGED and is_node_ready():
		_layout_safe_area()


func show_screen(mode: String) -> void:
	title.visible = mode == "title"
	result.visible = mode == "result"
	options.visible = false


func begin_run() -> void:
	show_screen("playing")
	hud.reset()


func show_result(state: Dictionary, best: int, seed_value: int) -> void:
	result.present_result(state, best, seed_value)
	show_screen("result")


func show_options(muted: bool, reduced: bool) -> void:
	title.visible = false
	result.visible = false
	options.set_values(muted, reduced)
	options.visible = true


func options_open() -> bool:
	return options.visible


func contains_pointer(at: Vector2) -> bool:
	return hud.contains_pointer(at) or title.contains_pointer(at) or result.contains_pointer(at) or options.contains_pointer(at)


func set_paused(value: bool) -> void:
	hud.set_paused(value)


func update_run(collected: int, score: int, multiplier: int, progress: float) -> void:
	hud.update_run(collected, score, multiplier, progress)


func group_completed(multiplier: int, reduced: bool) -> void:
	hud.group_completed(multiplier, reduced)


func advance(delta: float) -> void:
	hud.advance(delta)


## Keeps the HUD and dialogs out of notches, rounded corners and system bars.
func _layout_safe_area() -> void:
	# The display's safe area is in screen pixels; the layout is in canvas units.
	var safe := Rect2(DisplayServer.get_display_safe_area())
	safe.position -= Vector2(DisplayServer.window_get_position())
	var to_canvas := get_viewport().get_final_transform().affine_inverse()
	var insets := Vector4(24, 20, 24, 20) + safe_insets(safe, to_canvas, get_viewport().get_visible_rect().size)
	for index in range(4):
		ui_margin.add_theme_constant_override(["margin_left", "margin_top", "margin_right", "margin_bottom"][index], int(insets[index]))


## Left, top, right and bottom insets that keep a visible canvas inside safe, a rectangle in
## window pixels that to_canvas maps into canvas units.
static func safe_insets(safe: Rect2, to_canvas: Transform2D, visible: Vector2) -> Vector4:
	if not safe.has_area():
		return Vector4.ZERO
	var lead := (to_canvas * safe.position).max(Vector2.ZERO)
	var trail := (visible - to_canvas * safe.end).max(Vector2.ZERO)
	return Vector4(lead.x, lead.y, trail.x, trail.y)


# Whether the game may choose its window size: not on mobile platforms, not in a browser,
# whose page owns the canvas size (resizing the window would only shrink the rendered area
# inside the canvas and offset pointer input), and not headless.
func _can_resize_window() -> bool:
	for feature in ["mobile", "web"]:
		if OS.has_feature(feature):
			return false
	return DisplayServer.get_name() != "headless"


func fit_desktop_window() -> void:
	if not _can_resize_window():
		return
	# Keep an explicit caller-selected resolution (including layout probes).
	if OS.get_cmdline_args().has("--resolution") or OS.get_cmdline_args().has("--fullscreen"):
		return
	var window := get_window()
	var usable := DisplayServer.screen_get_usable_rect(window.current_screen)
	if usable.size.x <= 0 or usable.size.y <= 0:
		return
	# The project's viewport shape, like the phone layout, at most 85% of the usable height.
	var aspect := float(ProjectSettings.get_setting("display/window/size/viewport_width")) / float(ProjectSettings.get_setting("display/window/size/viewport_height"))
	var height := int(minf(usable.size.y * 0.85, usable.size.x * 0.8 / aspect))
	window.size = Vector2i(int(height * aspect), height)
	window.position = usable.position + (usable.size - window.size) / 2
