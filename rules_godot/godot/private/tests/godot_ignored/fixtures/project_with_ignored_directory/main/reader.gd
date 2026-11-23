extends SceneTree

## Reads a file of the directory Godot ignores, as a plugin's report writer does.


func _initialize() -> void:
	var text: String = FileAccess.get_file_as_string("res://report/template.html")
	if not text.contains("report"):
		push_error("res://report/template.html is not readable from the sources")
		quit(1)
		return
	for entry: Dictionary in ProjectSettings.get_global_class_list():
		if entry["class"] in ["IgnoredHelper", "DemoHelper"]:
			push_error("Godot registered a class of an ignored directory")
			quit(1)
			return
	print("read the ignored report template")
	quit()
