extends Node

# Typed calls on a script, a tool script and a scene autoload.


func report() -> bool:
	var length: int = Tracker.track("start")
	var tooled: int = ToolTracker.track("start")
	var events: int = Tracker.events
	return Hud.show_hud(length + tooled + events)
