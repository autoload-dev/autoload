extends SceneTree
## Benchmark: steps Lichtpost's route model through as many runs as the first user argument
## says, held in a fixed rhythm. Uses only engine calls Lichtpost uses, so tree-shaken
## engines run it; time it from outside against zero runs.

const Route = preload("res://main/rules/route_model.gd")
const Level = preload("res://main/levels/level_01/level_01.tres")


func _initialize() -> void:
	var rules: Dictionary = Level.rules_data()
	var ticks := 0
	for run in range(int(OS.get_cmdline_user_args()[0])):
		var model := Route.new(27 + run, rules)
		while model.status == "running" and model.tick < 7200:
			var phase := model.tick % 50
			model.step(phase == 0, phase < 18)
			ticks += 1
	print("BENCH ", ticks)
	quit()
