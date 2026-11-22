extends Control

const Results = preload("path_results.gd")

func _ready() -> void:
	_fit_safe_area()
	get_viewport().size_changed.connect(_fit_safe_area)
	$Margin/Scroll/Rows/Platform.text = "Platform Paths · %s" % OS.get_name()
	var valid := true
	for row in Results.collect():
		var label := Label.new()
		label.text = Results.describe(row)
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		$Margin/Scroll/Rows.add_child(label)
		print(label.text)
		valid = valid and Results.is_valid(row) and row.status in [PlatformPathResult.OK, PlatformPathResult.UNAVAILABLE]
	if DisplayServer.get_name() == "headless":
		if valid:
			print("PLATFORM_PATHS_OK")
		get_tree().quit(0 if valid else 1)


## Keeps the content out of notches and rounded corners: the display's safe area is in screen
## pixels, the layout in canvas units.
func _fit_safe_area() -> void:
	var safe := Rect2(DisplayServer.get_display_safe_area())
	if not safe.has_area():
		return
	var window_origin := Vector2(DisplayServer.window_get_position())
	var to_canvas := get_viewport().get_final_transform().affine_inverse()
	var top_left := to_canvas * (safe.position - window_origin)
	var bottom_right := to_canvas * (safe.end - window_origin)
	var visible := get_viewport_rect().size
	offset_left = maxf(top_left.x, 0.0)
	offset_top = maxf(top_left.y, 0.0)
	offset_right = minf(bottom_right.x - visible.x, 0.0)
	offset_bottom = minf(bottom_right.y - visible.y, 0.0)
