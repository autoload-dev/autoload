extends Resource
## Level content and presentation references; this Resource selects no gameplay code.
## Keep length <= speed * 7200: live and replay runs share the existing
## 7200-tick (120-second) replay input budget.

const Palette = preload("res://main/shared/palette/palette.gd")
const Pattern = preload("res://main/run/section_pattern.gd")

@export var display_name := "Floating gardens"
@export var speed: int = 90
@export var length: int = 180000
@export var section_count: int = 12
@export var section_origin: int = 6000
@export var section_stride: int = 14000
@export var gap_offset: int = 7000
@export var pipe_offset: int = 2000
@export var gentle_sections: int = 3
@export var light_offset: int = -600
@export var light_spacing: int = 900
@export var light_heights := PackedInt32Array([1800, 3000, 2200])
@export var patterns: Array[Pattern] = []
@export var seed_min: int = 0
@export var seed_max: int = 2147483647
@export var palette: Palette
@export var environment: Environment
@export var sun_energy: float = 0.9
@export var sky: Texture2D
@export var far_gardens: Texture2D
@export var near_gardens: Texture2D


func rules_data() -> Dictionary:
	var variants: Array[Dictionary] = []
	for pattern in patterns:
		variants.append({
			"gap_width": pattern.gap_width,
			"gentle_gap_width": pattern.gentle_gap_width,
			"has_pipe": pattern.has_pipe,
		})
	return {
		"speed": speed, "length": length, "section_count": section_count,
		"section_origin": section_origin, "section_stride": section_stride,
		"gap_offset": gap_offset, "pipe_offset": pipe_offset,
		"gentle_sections": gentle_sections, "light_offset": light_offset,
		"light_spacing": light_spacing, "light_heights": light_heights,
		"patterns": variants,
	}


func initial_seed(value: int) -> int:
	return clampi(value & 0x7fffffff, seed_min, seed_max)


func next_seed(value: int) -> int:
	return seed_min + posmod(value - seed_min + 104729, seed_max - seed_min + 1)
