extends SceneTree
# Compiles every script of the mounted project and writes its bytecode below the output
# directory, the first user argument, at the script's path with the extension .gdc.

func _initialize() -> void:
	var out_dir: String = OS.get_cmdline_user_args()[0]
	var failed := 0
	var written := 0
	for path in _scripts("res://"):
		var bytes: PackedByteArray = GDScriptBytecodeWriter.compile(path)
		if bytes.is_empty():
			printerr("FAILED ", path)
			failed += 1
			continue
		var target := out_dir.path_join(path.trim_prefix("res://").get_basename() + ".gdc")
		DirAccess.make_dir_recursive_absolute(target.get_base_dir())
		var file := FileAccess.open(target, FileAccess.WRITE)
		file.store_buffer(bytes)
		written += 1
	print("bytecode: %d written, %d failed" % [written, failed])
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
