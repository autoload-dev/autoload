extends SceneTree

const Route = preload("res://main/rules/route_model.gd")


func _initialize() -> void:
	var run = Route.new(27)
	var actions: Array = []
	var held := false
	var release_at := 0
	while run.status == "running" and run.tick < 7200:
		var next := false
		for pipe in run.pipes:
			if run.x >= pipe - 1400 and run.x < pipe - 1400 + Route.SPEED:
				next = true
		for gap in run.gaps:
			if run.x >= gap.x - 1400 and run.x < gap.x - 1400 + Route.SPEED:
				next = true
		if next:
			release_at = run.tick + 8
		var next_held: bool = next or (held and run.tick < release_at)
		if next_held != held:
			actions.append([run.tick + 1, next_held])
		run.step(next_held and not held, next_held)
		held = next_held
	print("RECORD " + JSON.stringify({"version": 1, "seed": 27, "actions": actions}))
	print("EXPECT " + JSON.stringify(run.snapshot()))
	quit(0 if run.status == "delivered" else 1)
