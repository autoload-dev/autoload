extends PanelContainer

signal retry_requested
signal new_route_requested
@onready var retry_button: Button = $Content/RetryButton
@onready var new_route_button: Button = $Content/NewRouteButton
@onready var headline: Label = $Content/Headline
@onready var description: Label = $Content/Description


func _ready() -> void:
	retry_button.pressed.connect(retry_requested.emit)
	new_route_button.pressed.connect(new_route_requested.emit)


func present_result(state: Dictionary, best: int, seed_value: int) -> void:
	headline.text = "LIGHT DELIVERED" if state.status == "delivered" else "ONE MORE TRY?"
	var cause := "Hit a pipe. Jump to clear it." if state.reason == "pipe" else "Missed the landing. Hold to jump farther."
	description.text = "%s\n%d points  ·  %d lights\nBest chain %d  ·  Personal best %d\nRoute %d" % [
		"The greenhouse glows again." if state.status == "delivered" else cause,
		state.score, state.collected, state.best_chain, best, seed_value,
	]


func contains_pointer(at: Vector2) -> bool:
	return visible and (retry_button.get_global_rect().has_point(at) or new_route_button.get_global_rect().has_point(at))
