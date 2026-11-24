extends PanelContainer

signal mute_changed(value: bool)
signal motion_changed(value: bool)
signal closed
@onready var content: VBoxContainer = $Content
@onready var mute_toggle: CheckButton = $Content/MuteToggle
@onready var motion_toggle: CheckButton = $Content/MotionToggle
@onready var back_button: Button = $Content/BackButton


func _ready() -> void:
	mute_toggle.toggled.connect(mute_changed.emit)
	motion_toggle.toggled.connect(motion_changed.emit)
	back_button.pressed.connect(closed.emit)


func set_values(muted: bool, reduced: bool) -> void:
	mute_toggle.set_pressed_no_signal(muted)
	motion_toggle.set_pressed_no_signal(reduced)


func contains_pointer(at: Vector2) -> bool:
	return visible and content.get_global_rect().has_point(at)
