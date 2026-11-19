extends Control
## Composes the dish and the HUD and routes the HUD's requests to the dish.

const STATS_INTERVAL := 0.5

@onready var dish: TextureRect = $Dish
@onready var hud: MarginContainer = $Hud
var _stats_timer := 0.0


func _ready() -> void:
	fit_desktop_window()
	hud.set_presets(dish.PRESETS.map(func(entry: Dictionary) -> String: return entry.name), dish.preset)
	hud.preset_selected.connect(dish.apply_preset)
	hud.pause_toggled.connect(func(paused: bool) -> void: dish.paused = paused)
	hud.clear_requested.connect(dish.clear)
	hud.update_stats(dish.stats())


func _process(delta: float) -> void:
	_stats_timer += delta
	if _stats_timer >= STATS_INTERVAL:
		_stats_timer = 0.0
		hud.update_stats(dish.stats())


## A phone-shaped window on desktops, like the portrait viewport.
func fit_desktop_window() -> void:
	if OS.has_feature("mobile") or DisplayServer.get_name() == "headless":
		return
	if OS.get_cmdline_args().has("--resolution") or OS.get_cmdline_args().has("--fullscreen"):
		return
	var window := get_window()
	var usable := DisplayServer.screen_get_usable_rect(window.current_screen)
	if usable.size.x <= 0 or usable.size.y <= 0:
		return
	var aspect := float(ProjectSettings.get_setting("display/window/size/viewport_width")) / float(ProjectSettings.get_setting("display/window/size/viewport_height"))
	var height := int(minf(usable.size.y * 0.85, usable.size.x * 0.8 / aspect))
	window.size = Vector2i(int(height * aspect), height)
	window.position = usable.position + (usable.size - window.size) / 2
