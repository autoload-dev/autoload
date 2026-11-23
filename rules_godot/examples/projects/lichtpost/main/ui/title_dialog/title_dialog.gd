extends PanelContainer

signal start_requested


func _ready() -> void:
	$Content/StartButton.pressed.connect(start_requested.emit)


func contains_pointer(at: Vector2) -> bool:
	return visible and $Content/StartButton.get_global_rect().has_point(at)
