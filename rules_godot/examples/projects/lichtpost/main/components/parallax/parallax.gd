extends CanvasLayer
## Scenery is cosmetic: scrolling never feeds back into the route model.

const LevelDefinition = preload("res://main/run/level_definition.gd")

## Garden band height per viewport width; landscape windows use their full height.
const BAND_ASPECT := 1.2
## Height in the garden textures where the islands' tops sit, as a share of the band.
const ISLAND_LINE := 0.6
@onready var sky: TextureRect = $Sky
var layers: Array[TextureRect] = []
var tile_count := 0


var far_texture: Texture2D
var near_texture: Texture2D


func configure(level: LevelDefinition) -> void:
	sky.texture = level.sky
	far_texture = level.far_gardens
	near_texture = level.near_gardens
	for rect in layers:
		rect.queue_free()
	layers.clear()
	tile_count = 0


func _texture(texture: Texture2D) -> TextureRect:
	var rect := TextureRect.new()
	rect.texture = texture
	rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(rect)
	return rect


## Scrolls the gardens by distance and keeps their islands near ground_y on screen.
func follow(distance: float, ground_y: float) -> void:
	var viewport := get_viewport().get_visible_rect().size
	sky.size = viewport
	var height := minf(viewport.y, viewport.x * BAND_ASPECT)
	var top := clampf(ground_y - height * ISLAND_LINE, 0.0, viewport.y - height)
	var width := height * 1.5
	var needed := ceili(viewport.x / width) + 3
	if needed != tile_count:
		for rect in layers:
			rect.queue_free()
		layers.clear()
		tile_count = needed
		for texture: Texture2D in [far_texture, near_texture]:
			for index in range(tile_count):
				var rect := _texture(texture)
				rect.flip_h = index % 2 == 1
				layers.append(rect)
	for index in range(layers.size()):
		var depth := index / tile_count
		var speed := 3.0 if depth == 0 else 9.0
		var rect := layers[index]
		rect.size = Vector2(width, height)
		# Mirrored pairs meet at identical edge pixels, including the wrap.
		rect.position = Vector2((index % tile_count - 1) * width - fposmod(distance * speed, width * 2), top)
		rect.modulate = Color(0.58, 0.72, 0.84, 0.65) if depth == 0 else Color(0.8, 0.9, 1, 0.85)
