extends Node

# Reports the extensions the engine loaded and quits with code 3.


func _ready() -> void:
	print("loaded extensions: %s" % ", ".join(GDExtensionManager.get_loaded_extensions()))
	get_tree().quit(3)
