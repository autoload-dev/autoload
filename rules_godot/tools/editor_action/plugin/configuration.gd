@tool
extends "export.gd"

# The configuration export's plugin; the record export.gd writes carries its facts.
# The export of the staged project without its files yields the project.binary of a
# pack that a build writes without Godot. Record what that build needs from Godot
# besides it: the export's feature tags, which select the imported variants, the
# settings naming files the runtime reads raw, and the translations, which decide
# the text server's support data. Write that data where the action says, and skip
# every file.


func _export_begin(features: PackedStringArray, is_debug: bool, path: String, flags: int) -> void:
	super(features, is_debug, path, flags)
	var preset: EditorExportPreset = get_export_preset()
	var translations: PackedStringArray = preset.get_project_setting("internationalization/locale/translations")
	facts = {
		"features": Array(features),
		"icon": preset.get_project_setting("application/config/icon"),
		"boot_splash": preset.get_project_setting("application/boot_splash/image"),
		"translations": Array(translations),
	}
	var server: TextServer = TextServerManager.get_primary_interface()
	if server.has_feature(TextServer.FEATURE_USE_SUPPORT_DATA):
		var file_name: String = server.get_support_data_filename()
		var support_data: String = action["support_data"]
		if not file_name.is_empty() and server.save_support_data(support_data):
			facts["support_data"] = file_name


func _export_file(_path: String, _type: String, _features: PackedStringArray) -> void:
	skip()
