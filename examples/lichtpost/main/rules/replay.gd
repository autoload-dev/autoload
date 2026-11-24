extends RefCounted
## A replay records changes to the held button at numbered simulation ticks.
## Version 1 JSON contains seed and actions: ordered [tick, held] pairs, beginning
## with a press and alternating press/release. Tick 1 is the first simulation step.
## Fixtures may carry an expected snapshot; the game only reads seed and actions.

var seed_value := 27
var actions: Dictionary = {}
var error := ""


func read_file(path: String) -> bool:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		error = "Cannot read replay: " + path
		return false
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if not parsed is Dictionary or (parsed as Dictionary).get("version") != 1:
		error = "Replay needs version 1"
		return false
	var data: Dictionary = parsed
	var route_seed: Variant = data.get("seed")
	if not route_seed is float and not route_seed is int:
		error = "Replay needs an integer seed"
		return false
	if route_seed != int(route_seed) or route_seed < 0 or route_seed > 2147483647:
		error = "Replay seed is outside 0..2147483647"
		return false
	seed_value = int(route_seed)
	var entries: Variant = data.get("actions")
	if not entries is Array or (entries as Array).size() > 7200:
		error = "Replay needs an actions array (at most 7200 entries)"
		return false
	var previous := 0
	var held := false
	for item: Variant in entries as Array:
		if not item is Array or (item as Array).size() != 2:
			error = "Each action is [tick, held]"
			return false
		var entry: Array = item
		if not (entry[0] is float or entry[0] is int) or not entry[1] is bool:
			error = "Action tick must be an integer and held must be boolean"
			return false
		var at := int(entry[0])
		if entry[0] != at or at <= previous or at > 7200 or entry[1] == held:
			error = "Actions must alternate and have increasing ticks in 1..7200"
			return false
		actions[at] = entry[1]
		previous = at
		held = entry[1]
	return true
