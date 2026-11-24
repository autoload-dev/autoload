extends PanelContainer

signal start_requested
@onready var start_button: Button = $Content/StartButton


func _ready() -> void:
	start_button.pressed.connect(start_requested.emit)


func contains_pointer(at: Vector2) -> bool:
	return visible and start_button.get_global_rect().has_point(at)
