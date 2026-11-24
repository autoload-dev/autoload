extends RefCounted
## Fixed 60 Hz rules. Distances are millimetres; velocity is millimetres/tick.
## Rendering, engine physics, audio, wall time and persistent scores are not inputs.

const SPEED := 90
const BODY_WIDTH := 180
const BODY_HEIGHT := 900
const PIPE_WIDTH := 700
const PIPE_HEIGHT := 900
const FINISH := 180000
const BUFFER_TICKS := 8
const COYOTE_TICKS := 7

var seed_value: int
var tick := 0
var x := 0
var y := 0
var velocity := 0
var grounded := true
var status := "running"
var reason := ""
var score := 0
var collected := 0
var chain := 0
var best_chain := 0
var buffer := 0
var coyote := COYOTE_TICKS
var jump_age := 100
var gaps: Array[Vector2i] = []
var pipes: Array[int] = []
var lights: Array[LightState] = []
var events: Array[String] = []
var group_hits := 0
var group_index := 0
var speed: int = SPEED
var route_length: int = FINISH
var lights_per_group := 3


func _init(route_seed: int = 27, level: Dictionary = {}) -> void:
	speed = level.get("speed", SPEED)
	route_length = level.get("length", FINISH)
	seed_value = route_seed & 0x7fffffff
	var random_state := seed_value
	var patterns: Array = level.get("patterns", [])
	var heights: PackedInt32Array = level.get("light_heights", PackedInt32Array([1800, 3000, 2200]))
	lights_per_group = heights.size()
	for section in range(int(level.get("section_count", 12))):
		# Own small LCG: layout is independent of Godot's RNG implementation.
		random_state = (random_state * 1103515245 + 12345) & 0x7fffffff
		var pattern := (random_state >> 16) % (12 if patterns.is_empty() else patterns.size())
		var base: int = level.get("section_origin", 6000) + section * int(level.get("section_stride", 14000))
		var start: int = base + int(level.get("gap_offset", 7000))
		var gentle: bool = section < int(level.get("gentle_sections", 3))
		var gap_width := 1200 + (pattern % 2) * 200 if gentle else 1600 + (pattern % 4) * 200
		var has_pipe := pattern % 3 != 0
		if not patterns.is_empty():
			gap_width = int(patterns[pattern].gentle_gap_width if gentle else patterns[pattern].gap_width)
			has_pipe = bool(patterns[pattern].has_pipe)
		gaps.append(Vector2i(start, start + gap_width))
		if section > 0 and has_pipe:
			pipes.append(base + int(level.get("pipe_offset", 2000)))
		for item in range(heights.size()):
			var light_x := start + int(level.get("light_offset", -600)) + item * int(level.get("light_spacing", 900))
			lights.append(LightState.new(light_x, heights[item]))


func has_floor(at: int) -> bool:
	for gap in gaps:
		if at >= gap.x and at < gap.y:
			return false
	return true


func step(pressed: bool, held: bool) -> void:
	events.clear()
	if status != "running":
		return
	held = held or pressed
	tick += 1
	var previous_y := y
	buffer = BUFFER_TICKS if pressed else maxi(0, buffer - 1)
	coyote = COYOTE_TICKS if grounded else maxi(0, coyote - 1)
	if buffer > 0 and coyote > 0:
		velocity = 240
		grounded = false
		coyote = 0
		buffer = 0
		jump_age = 0
		events.append("jump")
	if not grounded:
		# Even a press and release between ticks receives the initial impulse.
		if not held and jump_age > 0 and velocity > 160:
			velocity = 160
		velocity -= 6 if held and jump_age < 10 else 12
		y += velocity
		jump_age += 1
	x += speed
	if grounded and not has_floor(x):
		grounded = false
		jump_age = 100
	if not grounded and previous_y >= 0 and y <= 0 and velocity <= 0 and has_floor(x):
		y = 0
		velocity = 0
		grounded = true
		events.append("land")
	for pipe in pipes:
		if x + BODY_WIDTH >= pipe and x - BODY_WIDTH <= pipe + PIPE_WIDTH and y < PIPE_HEIGHT:
			finish("lost", "pipe")
			return
	if y < -1500:
		finish("lost", "fall")
		return
	for light in lights:
		if not light.taken and absi(x - light.x) <= 450:
			if absi(y + 600 - light.y) <= 700:
				light.taken = true
				collected += 1
				group_hits += 1
				score += 10 * (1 + mini(chain, 3))
				events.append("light")
	if group_index < gaps.size() and x > gaps[group_index].y + 1500:
		if lights_per_group > 0 and group_hits == lights_per_group:
			chain += 1
			best_chain = maxi(best_chain, chain)
			events.append("group")
		else:
			chain = 0
		group_hits = 0
		group_index += 1
	if x >= route_length:
		finish("delivered", "")


func finish(result: String, cause: String) -> void:
	status = result
	reason = cause
	events.append(result)


func snapshot() -> Dictionary:
	return {
		"seed": seed_value, "tick": tick, "x": x, "y": y,
		"status": status, "reason": reason, "score": score,
		"collected": collected, "best_chain": best_chain,
	}


## A light along the route, in millimetres, and whether the courier took it.
class LightState:
	var x: int
	var y: int
	var taken := false

	func _init(at_x: int, at_y: int) -> void:
		x = at_x
		y = at_y
