@tool
extends EditorImportPlugin

func _get_importer_name() -> String:
	return "rules_godot.markdown"

func _get_visible_name() -> String:
	return "Markdown"

func _get_recognized_extensions() -> PackedStringArray:
	return PackedStringArray(["md"])

func _get_save_extension() -> String:
	return "res"

func _get_resource_type() -> String:
	return "Resource"

func _get_preset_count() -> int:
	return 1

func _get_preset_name(_preset_index: int) -> String:
	return "Default"

func _get_import_options(_path: String, _preset_index: int) -> Array[Dictionary]:
	return []

func _get_option_visibility(_path: String, _option_name: StringName, _options: Dictionary) -> bool:
	return true

func _get_priority() -> float:
	return 1.0

func _get_import_order() -> int:
	return 0

func _import(source_file: String, save_path: String, _options: Dictionary, _platform_variants: Array[String], _gen_files: Array[String]) -> Error:
	var text := Resource.new()
	text.set_meta("text", FileAccess.get_file_as_string(source_file).strip_edges())
	return ResourceSaver.save(text, "%s.%s" % [save_path, _get_save_extension()])
