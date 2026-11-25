extends GdUnitTestSuite

func test_real_locations() -> void:
	var saved: Dictionary = {}
	var root := OS.get_environment("TEST_TMPDIR").path_join("platform paths ü")
	if OS.get_name() == "Linux":
		DirAccess.make_dir_recursive_absolute(root.path_join("config"))
		var template := FileAccess.get_file_as_string("res://locations/fixtures/user-dirs.dirs.tpl")
		var config := FileAccess.open(root.path_join("config/user-dirs.dirs"), FileAccess.WRITE)
		config.store_string(template.replace("{ROOT}", root))
		config.close()
		for name in ["HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "TMPDIR"]:
			saved[name] = [OS.has_environment(name), OS.get_environment(name)]
			OS.set_environment(name, root.path_join("config" if name == "XDG_CONFIG_HOME" else name))
	var resolver := PlatformPaths.new()
	for category in range(5):
		var result: PlatformPathResult = resolver.resolve(category)
		assert_int(result.status).is_equal(PlatformPathResult.OK)
		assert_int(result.category).is_equal(category)
		assert_bool(result.path.is_absolute_path()).is_true()
		assert_str(result.message).is_empty()
		var expected_scope := PlatformPathResult.TEMPORARY if category == 0 else (PlatformPathResult.APPLICATION if category < 3 else PlatformPathResult.USER_DOMAIN)
		assert_int(result.scope).is_equal(expected_scope)
		if category in [1, 2]:
			assert_str(result.path).ends_with("/org.example.platformpaths")
		if OS.get_name() == "Linux":
			var suffixes := ["TMPDIR", "XDG_DATA_HOME/org.example.platformpaths", "XDG_CACHE_HOME/org.example.platformpaths", "Documents ü", "Downloads space"]
			assert_str(result.path).is_equal(root.path_join(suffixes[category]))
			if category == 3:
				assert_bool(DirAccess.dir_exists_absolute(result.path)).is_false()
		elif category >= 3:
			var directory := OS.SYSTEM_DIR_DOCUMENTS if category == 3 else OS.SYSTEM_DIR_DOWNLOADS
			assert_str(result.path).is_equal(OS.get_system_dir(directory))
	if OS.get_name() == "Linux":
		OS.set_environment("TMPDIR", resolver.resolve(2).path)
		assert_str(resolver.resolve(0).path).is_equal(resolver.resolve(2).path)
		assert_int(resolver.resolve(0).scope).is_equal(PlatformPathResult.TEMPORARY)
	for name in saved:
		if saved[name][0]:
			OS.set_environment(name, saved[name][1])
		else:
			OS.unset_environment(name)

func test_identity_error_preserves_other_categories() -> void:
	var original: Variant = ProjectSettings.get_setting("platform_paths/application_id")
	var resolver := PlatformPaths.new()
	var before: Array[PlatformPathResult] = [resolver.resolve(0), resolver.resolve(3), resolver.resolve(4)]
	ProjectSettings.set_setting("platform_paths/application_id", "../invalid")
	assert_int(resolver.resolve(1).status).is_equal(PlatformPathResult.ERROR)
	assert_int(resolver.resolve(2).status).is_equal(PlatformPathResult.ERROR)
	for index in range(3):
		var after: PlatformPathResult = resolver.resolve([0, 3, 4][index])
		assert_int(after.status).is_equal(before[index].status)
		assert_str(after.path).is_equal(before[index].path)
	ProjectSettings.set_setting("platform_paths/application_id", original)

func test_linux_configuration_failures_are_independent_and_reread() -> void:
	if OS.get_name() != "Linux":
		return
	var had_config := OS.has_environment("XDG_CONFIG_HOME")
	var original := OS.get_environment("XDG_CONFIG_HOME")
	var root := OS.get_environment("TEST_TMPDIR").path_join("failure-config")
	DirAccess.make_dir_recursive_absolute(root)
	OS.set_environment("XDG_CONFIG_HOME", root)
	var filename := root.path_join("user-dirs.dirs")
	var resolver := PlatformPaths.new()
	assert_int(resolver.resolve(3).status).is_equal(PlatformPathResult.UNAVAILABLE)
	var file := FileAccess.open(filename, FileAccess.WRITE)
	file.store_string(FileAccess.get_file_as_string("res://locations/fixtures/malformed-user-dirs.dirs.tpl"))
	file.close()
	var previous: PlatformPathResult = resolver.resolve(4)
	assert_int(resolver.resolve(3).status).is_equal(PlatformPathResult.ERROR)
	assert_int(previous.status).is_equal(PlatformPathResult.OK)
	assert_str(previous.path).is_equal("/valid/not-created/ü")
	file = FileAccess.open(filename, FileAccess.WRITE)
	file.store_string(FileAccess.get_file_as_string("res://locations/fixtures/documents-only-user-dirs.dirs.tpl"))
	file.close()
	assert_int(resolver.resolve(4).status).is_equal(PlatformPathResult.UNAVAILABLE)
	assert_str(resolver.resolve(3).path).is_equal("/new/configured/documents")
	assert_str(previous.path).is_equal("/valid/not-created/ü")
	file = FileAccess.open(filename, FileAccess.WRITE)
	file.close()
	assert_int(resolver.resolve(3).status).is_equal(PlatformPathResult.UNAVAILABLE)
	DirAccess.remove_absolute(filename)
	DirAccess.make_dir_absolute(filename)
	assert_int(resolver.resolve(3).status).is_equal(PlatformPathResult.ERROR)
	DirAccess.remove_absolute(filename)
	if had_config:
		OS.set_environment("XDG_CONFIG_HOME", original)
	else:
		OS.unset_environment("XDG_CONFIG_HOME")
