extends VBoxContainer

signal pause_requested
signal options_requested
var feedback_time := 0.0
var feedback_tween: Tween
@onready var pause_button: Button = $TopBar/PauseButton
@onready var options_button: Button = $TopBar/OptionsButton
@onready var points: Label = $Points
@onready var progress_bar: ProgressBar = $Progress
@onready var feedback: Label = $Feedback


func _ready() -> void:
	pause_button.pressed.connect(pause_requested.emit)
	options_button.pressed.connect(options_requested.emit)


func reset() -> void:
	feedback.text = ""
	pause_button.text = "Pause"


func set_paused(value: bool) -> void:
	pause_button.text = "Resume" if value else "Pause"
	points.text = "PAUSED · Resume / Esc" if value else ""


func update_run(collected: int, score: int, multiplier: int, progress: float) -> void:
	points.text = "☀ %d   ·   %d points   ·   ×%d" % [collected, score, multiplier]
	progress_bar.value = progress


func group_completed(multiplier: int, reduced: bool) -> void:
	feedback.text = "FULL GROUP  ·  ×%d" % multiplier
	feedback_time = 1.5
	if not reduced:
		if feedback_tween != null and feedback_tween.is_valid():
			feedback_tween.kill()
		feedback.scale = Vector2.ONE * 1.12
		feedback_tween = create_tween()
		feedback_tween.tween_property(feedback, "scale", Vector2.ONE, 0.25)


func advance(delta: float) -> void:
	feedback_time = maxf(0.0, feedback_time - delta)
	if feedback_time <= 0:
		feedback.text = ""


func contains_pointer(at: Vector2) -> bool:
	return pause_button.get_global_rect().has_point(at) or options_button.get_global_rect().has_point(at)
