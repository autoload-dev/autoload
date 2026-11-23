extends PanelContainer

signal retry_requested
signal new_route_requested


func _ready() -> void:
	$Content/RetryButton.pressed.connect(retry_requested.emit)
	$Content/NewRouteButton.pressed.connect(new_route_requested.emit)


func present_result(state: Dictionary, best: int, seed_value: int) -> void:
	$Content/Headline.text = "LIGHT DELIVERED" if state.status == "delivered" else "ONE MORE TRY?"
	var cause := "Hit a pipe. Jump to clear it." if state.reason == "pipe" else "Missed the landing. Hold to jump farther."
	$Content/Description.text = "%s\n%d points  ·  %d lights\nBest chain %d  ·  Personal best %d\nRoute %d" % [
		"The greenhouse glows again." if state.status == "delivered" else cause,
		state.score, state.collected, state.best_chain, best, seed_value,
	]


func contains_pointer(at: Vector2) -> bool:
	return visible and ($Content/RetryButton.get_global_rect().has_point(at) or $Content/NewRouteButton.get_global_rect().has_point(at))
