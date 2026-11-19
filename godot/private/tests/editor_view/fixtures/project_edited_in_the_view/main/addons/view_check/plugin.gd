@tool
extends EditorPlugin

# The editor view test reads these lines and checks the edits in the checkout.

func _enter_tree() -> void:
	var loaded := GDExtensionManager.is_extension_loaded("res://native/hello.gdextension")
	print("VIEW_CHECK extension_loaded=%s" % loaded)
	print("VIEW_CHECK icon_imported=%s" % ResourceLoader.exists("res://main/levels/icon.svg"))
	_write("res://main/main.gd", "extends Node2D\n")
	_write("res://main/levels/two.json", "{\"level\": 2}\n")
	_write("res://notes.gd", "extends Node\n")
	ProjectSettings.set_setting("application/config/description", "Edited in the view")
	ProjectSettings.set_setting("rules_godot/editor/contributed", 2)
	ProjectSettings.save()
	print("VIEW_CHECK done")
	get_tree().quit.call_deferred()


func _write(path: String, text: String) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(text)
	file.close()
