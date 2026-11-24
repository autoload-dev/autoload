extends Control

func _ready() -> void:
	_fit_safe_area()
	get_viewport().size_changed.connect(_fit_safe_area)
	var database = SQLiteDatabase.new()
	var success: bool = database.open()
	success = success and database.execute("CREATE TABLE messages (text TEXT)")
	success = success and database.execute("INSERT INTO messages VALUES (?)", ["Hello from SQLite"])
	var rows: Array = database.query("SELECT text FROM messages")
	success = success and rows == [{"text": "Hello from SQLite"}]
	$Result.text = "SQLite says: %s" % rows[0]["text"] if success else database.get_last_error()
	database.close()
	if not success:
		push_error("SQLite demo failed")
	else:
		print("SQLITE_DEMO_OK")
	if DisplayServer.get_name() == "headless":
		get_tree().quit(0 if success else 1)


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
