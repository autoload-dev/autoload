extends GdUnitTestSuite
## The login API on the host, without network access or an identity provider.
## BUSY needs a pending login and is a manual check; the README's "Run the demo" lists it.

const ISSUER := "https://demo.duendesoftware.com"
const CLIENT_ID := "interactive.public"
const SCOPES: Array[String] = ["openid", "profile"]


func test_login_never_returns_null_and_finishes_once_on_a_later_frame() -> void:
	var results: Array[AppAuthResult] = []
	var login: AppAuthLogin = AppAuth.login("", CLIENT_ID, PackedStringArray(SCOPES))
	assert_object(login).is_not_null()
	assert_bool(login.is_pending()).is_true()
	login.finished.connect(func(result: AppAuthResult) -> void: results.append(result))
	# Nothing is emitted before login returns, so a caller can connect afterwards.
	assert_array(results).is_empty()
	await get_tree().process_frame
	await get_tree().process_frame
	assert_array(results).has_size(1)
	assert_bool(login.is_pending()).is_false()
	await get_tree().process_frame
	assert_array(results).has_size(1)


func test_invalid_configuration_names_the_field_on_every_operating_system() -> void:
	var cases := {
		"issuer": ["http://demo.duendesoftware.com", CLIENT_ID, PackedStringArray(SCOPES), ""],
		"client_id": [ISSUER, "", PackedStringArray(SCOPES), ""],
		"scopes": [ISSUER, CLIENT_ID, PackedStringArray(["profile"]), ""],
		"redirect_uri": [ISSUER, CLIENT_ID, PackedStringArray(SCOPES), "/oauth2redirect"],
	}
	for field: String in cases:
		var arguments: Array = cases[field]
		var login: AppAuthLogin = AppAuth.login(arguments[0], arguments[1], arguments[2], arguments[3])
		var result: AppAuthResult = await login.finished
		assert_int(result.status).override_failure_message(field).is_equal(AppAuthResult.INVALID_CONFIGURATION)
		assert_str(result.message).contains(field)
		_assert_no_tokens(result)


func test_host_without_backend_reports_unsupported() -> void:
	if AppAuth.is_supported():
		# A macOS host has a backend; a valid login there is a real provider flow.
		assert_str(AppAuth.default_redirect_uri()).ends_with(":/oauth2redirect")
		return
	assert_str(AppAuth.default_redirect_uri()).is_empty()
	var login: AppAuthLogin = AppAuth.login(ISSUER, CLIENT_ID, PackedStringArray(SCOPES))
	var result: AppAuthResult = await login.finished
	assert_int(result.status).is_equal(AppAuthResult.UNSUPPORTED)
	assert_str(result.message).is_not_empty()
	_assert_no_tokens(result)


func test_registered_types_and_readonly_properties() -> void:
	var methods := ClassDB.class_get_method_list("AppAuth", true)
	for name in ["login", "default_redirect_uri", "is_supported"]:
		var matching := methods.filter(func(m: Dictionary) -> bool: return m.name == name)
		assert_array(matching).override_failure_message(name).has_size(1)
		assert_bool((matching[0]["flags"] & METHOD_FLAG_STATIC) != 0).is_true()
	var expected_types := {
		"status": TYPE_INT,
		"message": TYPE_STRING,
		"provider_error": TYPE_STRING,
		"access_token": TYPE_STRING,
		"id_token": TYPE_STRING,
		"claims": TYPE_DICTIONARY,
		"scopes": TYPE_PACKED_STRING_ARRAY,
		"expires_at": TYPE_INT,
		"has_refresh_token": TYPE_BOOL,
	}
	var properties := ClassDB.class_get_property_list("AppAuthResult", true)
	for name: String in expected_types:
		var matching := properties.filter(func(p: Dictionary) -> bool: return p.name == name)
		assert_array(matching).override_failure_message(name).has_size(1)
		assert_int(matching[0].type).is_equal(expected_types[name])
		assert_str(str(ClassDB.class_get_property_setter("AppAuthResult", name))).is_empty()
	assert_int(AppAuthResult.OK).is_equal(0)
	assert_int(AppAuthResult.CANCELLED).is_equal(1)
	assert_int(AppAuthResult.INVALID_CONFIGURATION).is_equal(2)
	assert_int(AppAuthResult.BUSY).is_equal(3)
	assert_int(AppAuthResult.NETWORK_ERROR).is_equal(4)
	assert_int(AppAuthResult.PROVIDER_ERROR).is_equal(5)
	assert_int(AppAuthResult.UNSUPPORTED).is_equal(6)
	assert_int(AppAuthResult.ERROR).is_equal(7)


func _assert_no_tokens(result: AppAuthResult) -> void:
	assert_str(result.access_token).is_empty()
	assert_str(result.id_token).is_empty()
	assert_dict(result.claims).is_empty()
	assert_array(result.scopes).is_empty()
	assert_int(result.expires_at).is_equal(0)
	assert_bool(result.has_refresh_token).is_false()
