extends GdUnitTestSuite

func test_results_are_typed_snapshots() -> void:
	var resolver := PlatformPaths.new()
	var first: PlatformPathResult = resolver.resolve(-23)
	assert_object(first).is_not_null()
	assert_int(first.category).is_equal(-23)
	assert_int(first.status).is_equal(PlatformPathResult.ERROR)
	assert_str(first.path).is_empty()
	assert_str(first.message).is_not_empty()
	assert_int(first.scope).is_equal(PlatformPathResult.NONE)
	var second: PlatformPathResult = resolver.resolve(999)
	resolver = null
	assert_int(second.category).is_equal(999)
	assert_int(first.category).is_equal(-23)
	assert_bool(first.has_method("set_path")).is_false()
	assert_bool(first.has_method("reset")).is_false()
	var properties := first.get_property_list()
	for name in ["category", "status", "path", "message", "scope"]:
		var matching := properties.filter(func(p: Dictionary) -> bool: return p.name == name)
		assert_array(matching).has_size(1)
	assert_int(PlatformPaths.TEMPORARY).is_equal(0)
	assert_int(PlatformPaths.DOWNLOADS).is_equal(4)
	assert_int(PlatformPathResult.OK).is_equal(0)
	assert_int(PlatformPathResult.UNAVAILABLE).is_equal(1)
	assert_int(PlatformPathResult.INTEGRATION_UNAVAILABLE).is_equal(2)
	assert_int(PlatformPathResult.TEMPORARY).is_equal(3)

func test_registered_types_and_readonly_properties() -> void:
	var methods := ClassDB.class_get_method_list("PlatformPaths", true)
	var resolve_methods := methods.filter(func(m: Dictionary) -> bool: return m.name == "resolve")
	assert_array(resolve_methods).has_size(1)
	assert_str(str(resolve_methods[0]["return"].class_name)).is_equal("PlatformPathResult")
	var expected_types := {"category": TYPE_INT, "status": TYPE_INT, "path": TYPE_STRING, "message": TYPE_STRING, "scope": TYPE_INT}
	for property in ClassDB.class_get_property_list("PlatformPathResult", true):
		if property.name in expected_types:
			assert_int(property.type).is_equal(expected_types[property.name])
			assert_str(str(ClassDB.class_get_property_setter("PlatformPathResult", property.name))).is_empty()
			if property.name in ["status", "scope"]:
				assert_bool((property.usage & PROPERTY_USAGE_CLASS_IS_ENUM) != 0).is_true()
				assert_str(str(property.class_name)).is_equal("PlatformPathResult.Status" if property.name == "status" else "PlatformPathResult.Scope")
	assert_int(PlatformPaths.APPLICATION_SUPPORT).is_equal(1)
	assert_int(PlatformPaths.APPLICATION_CACHE).is_equal(2)
	assert_int(PlatformPaths.DOCUMENTS).is_equal(3)
	assert_int(PlatformPathResult.ERROR).is_equal(3)
	assert_int(PlatformPathResult.APPLICATION).is_equal(1)
	assert_int(PlatformPathResult.USER_DOMAIN).is_equal(2)

func test_invalid_identity_is_local_to_support_and_cache() -> void:
	var original: Variant = ProjectSettings.get_setting("platform_paths/application_id")
	var resolver := PlatformPaths.new()
	for invalid in ["", "../escape", ".hidden", "has space", "UPPER", "trailing.", "a..b", "a/b", "a\\b", "0first"]:
		ProjectSettings.set_setting("platform_paths/application_id", invalid)
		for category in [PlatformPaths.APPLICATION_SUPPORT, PlatformPaths.APPLICATION_CACHE]:
			var result: PlatformPathResult = resolver.resolve(category)
			assert_int(result.status).is_equal(PlatformPathResult.ERROR)
			assert_str(result.path).is_empty()
			assert_str(result.message).is_not_empty()
			assert_int(result.scope).is_equal(PlatformPathResult.NONE)
	ProjectSettings.set_setting("platform_paths/application_id", original)
