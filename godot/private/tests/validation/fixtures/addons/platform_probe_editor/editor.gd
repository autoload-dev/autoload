@tool
extends EditorPlugin


func _ready() -> void:
	add_child(PlatformProbe.new())
