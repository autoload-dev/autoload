extends PanelContainer

signal mute_changed(value: bool)
signal motion_changed(value: bool)
signal closed


func _ready() -> void:
	$Content/MuteToggle.toggled.connect(mute_changed.emit)
	$Content/MotionToggle.toggled.connect(motion_changed.emit)
	$Content/BackButton.pressed.connect(closed.emit)


func set_values(muted: bool, reduced: bool) -> void:
	$Content/MuteToggle.set_pressed_no_signal(muted)
	$Content/MotionToggle.set_pressed_no_signal(reduced)


func contains_pointer(at: Vector2) -> bool:
	return visible and $Content.get_global_rect().has_point(at)
