extends SceneTree
# Writes the analyzed syntax tree of every script of the mounted project, with types and
# member indices, as JSON below the output directory, the first user argument, at the
# script's path with the extension .json.

func _initialize() -> void:
	var out_dir: String = OS.get_cmdline_user_args()[0]
	var failed := 0
	var written := 0
	for path in _scripts("res://"):
		var text: String = GDScriptBytecodeWriter.ast(path)
		if text.is_empty():
			printerr("FAILED ", path)
			failed += 1
			continue
		var target := out_dir.path_join(path.trim_prefix("res://").get_basename() + ".json")
		DirAccess.make_dir_recursive_absolute(target.get_base_dir())
		var file := FileAccess.open(target, FileAccess.WRITE)
		file.store_string(text)
		written += 1
	print("syntax trees: %d written, %d failed" % [written, failed])
	quit(1 if failed else 0)


func _scripts(dir: String) -> PackedStringArray:
	var found := PackedStringArray()
	for sub in DirAccess.get_directories_at(dir):
		if not sub.begins_with("."):
			found.append_array(_scripts(dir.path_join(sub)))
	for file in DirAccess.get_files_at(dir):
		if file.get_extension() == "gd":
			found.append(dir.path_join(file))
	return found
