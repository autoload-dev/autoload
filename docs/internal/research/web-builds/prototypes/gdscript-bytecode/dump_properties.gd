extends SceneTree
# Writes, as JSON, the names of the properties the mounted project's scenes and resources
# set: every property a scene stores on a node, every storage property of a resource they
# or the project settings (such as the input map's events) use, and the methods their
# signal connections name. The first user argument is the output file.

var _names := {}
var _seen := {}


func _initialize() -> void:
	for path in _resources("res://"):
		_resource(ResourceLoader.load(path))
	for setting in ProjectSettings.get_property_list():
		_value(ProjectSettings.get_setting(setting["name"]))
	var file := FileAccess.open(OS.get_cmdline_user_args()[0], FileAccess.WRITE)
	var names := _names.keys()
	names.sort()
	file.store_string(JSON.stringify(names, "\t"))
	print("properties: %d names" % names.size())
	quit()


func _resource(resource: Resource) -> void:
	if resource == null or _seen.has(resource):
		return
	_seen[resource] = true
	if resource is PackedScene:
		_scene(resource.get_state())
		return
	for property in resource.get_property_list():
		if property["usage"] & PROPERTY_USAGE_STORAGE:
			_names[property["name"]] = true
			_value(resource.get(property["name"]))


func _scene(state: SceneState) -> void:
	for node in state.get_node_count():
		for index in state.get_node_property_count(node):
			_names[state.get_node_property_name(node, index)] = true
			_value(state.get_node_property_value(node, index))
	for connection in state.get_connection_count():
		_names[state.get_connection_method(connection)] = true


func _value(value: Variant) -> void:
	if value is Resource:
		_resource(value)
	elif value is Array:
		for element in value:
			_value(element)
	elif value is Dictionary:
		for key in value:
			_value(key)
			_value(value[key])


func _resources(dir: String) -> PackedStringArray:
	var found := PackedStringArray()
	for sub in DirAccess.get_directories_at(dir):
		if not sub.begins_with("."):
			found.append_array(_resources(dir.path_join(sub)))
	for file in DirAccess.get_files_at(dir):
		if file.get_extension() in ["tscn", "tres", "scn", "res"]:
			found.append(dir.path_join(file))
	return found
