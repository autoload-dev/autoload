extends VBoxContainer

signal pause_requested
signal options_requested
var feedback_time := 0.0
var feedback_tween: Tween


func _ready() -> void:
	$TopBar/PauseButton.pressed.connect(pause_requested.emit)
	$TopBar/OptionsButton.pressed.connect(options_requested.emit)


func reset() -> void:
	$Feedback.text = ""
	$TopBar/PauseButton.text = "Pause"


func set_paused(value: bool) -> void:
	$TopBar/PauseButton.text = "Resume" if value else "Pause"
	$Points.text = "PAUSED · Resume / Esc" if value else ""


func update_run(collected: int, score: int, multiplier: int, progress: float) -> void:
	$Points.text = "☀ %d   ·   %d points   ·   ×%d" % [collected, score, multiplier]
	$Progress.value = progress


func group_completed(multiplier: int, reduced: bool) -> void:
	$Feedback.text = "FULL GROUP  ·  ×%d" % multiplier
	feedback_time = 1.5
	if not reduced:
		if feedback_tween != null and feedback_tween.is_valid():
			feedback_tween.kill()
		$Feedback.scale = Vector2.ONE * 1.12
		feedback_tween = create_tween()
		feedback_tween.tween_property($Feedback, "scale", Vector2.ONE, 0.25)


func advance(delta: float) -> void:
	feedback_time = maxf(0.0, feedback_time - delta)
	if feedback_time <= 0:
		$Feedback.text = ""


func contains_pointer(at: Vector2) -> bool:
	return $TopBar/PauseButton.get_global_rect().has_point(at) or $TopBar/OptionsButton.get_global_rect().has_point(at)
