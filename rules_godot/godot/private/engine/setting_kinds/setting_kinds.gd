extends SceneTree

# Lists the project settings Godot hints as naming a file or directory. With the
# path of the setting-kind tables after Godot's -- separator, checks the table and
# the sections of this Godot's minor against what it registers instead and quits
# with 1 on a difference.

const HINTS = {
	PROPERTY_HINT_FILE: "file",
	PROPERTY_HINT_FILE_PATH: "file",
	PROPERTY_HINT_RESOURCE_TYPE: "file",
	PROPERTY_HINT_DIR: "dir",
}


func _init():
	var listed = {}
	var registered = {}
	for property in ProjectSettings.get_property_list():
		if "/" in property.name:
			registered[property.name.get_slice("/", 0)] = true
		if "/" in property.name and HINTS.has(property.hint):
			listed[property.name] = HINTS[property.hint]
	var arguments = OS.get_cmdline_user_args()
	if arguments.is_empty():
		print(JSON.stringify(listed, "  ", true))
		quit()
		return
	var root = OS.get_environment("TEST_SRCDIR")
	if root.is_empty():
		root = OS.get_environment("RUNFILES_DIR")
	var data = JSON.parse_string(FileAccess.get_file_as_string(root.path_join(arguments[0])))
	var tables = data["kinds"]
	var version = Engine.get_version_info()
	var minor = "%d.%d" % [version["major"], version["minor"]]
	if not tables.has(minor):
		printerr("No setting-kind table for Godot %s" % minor)
		quit(1)
		return
	var table = tables[minor]
	var problems = []
	for key in listed:
		if not table.has(key):
			problems.append("Godot %s hints %s as a %s; classify it in godot/private/engine/setting_kinds.bzl" % [minor, key, listed[key]])
		elif table[key]["hint"] != listed[key]:
			problems.append("Godot %s hints %s as a %s, the table as a %s" % [minor, key, listed[key], table[key]["hint"]])
	for key in table:
		if table[key]["hint"] != null and not listed.has(key):
			problems.append("Godot %s no longer hints %s; remove or reclassify its row" % [minor, key])
	var sections = data["sections"][minor]
	for section in registered:
		# A test adds the runner's own settings and its logger autoload through override.cfg.
		var known = section in sections["registered"] or section in sections["read"]
		if not known and section != "rules_godot":
			problems.append("Godot %s registers settings in %s; add the section to godot/private/engine/setting_kinds.bzl" % [minor, section])
	for section in sections["registered"]:
		if not registered.has(section):
			problems.append("Godot %s no longer registers settings in %s; move or remove the section" % [minor, section])
	for problem in problems:
		printerr(problem)
	print("Checked %d hinted settings of Godot %s" % [listed.size(), minor])
	quit(1 if problems else 0)
