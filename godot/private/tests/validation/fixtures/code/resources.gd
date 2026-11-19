extends RefCounted

# Preloads resources of custom resource scripts, which loading the script instantiates.

const SETTINGS = preload("res://code/settings.tres")
const TOOL_SETTINGS = preload("res://code/tool_settings.tres")


func resources() -> Array[Resource]:
	return [SETTINGS, TOOL_SETTINGS]
