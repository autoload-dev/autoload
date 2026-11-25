extends Control
## Logs in against Duende's public demo identity provider and shows the result.

const ISSUER := "https://demo.duendesoftware.com"
const CLIENT_ID := "interactive.public"
const SCOPES: Array[String] = ["openid", "profile", "email", "offline_access"]
const STATUS_NAMES := {
	AppAuthResult.OK: "OK",
	AppAuthResult.CANCELLED: "Cancelled",
	AppAuthResult.INVALID_CONFIGURATION: "Invalid configuration",
	AppAuthResult.BUSY: "Busy",
	AppAuthResult.NETWORK_ERROR: "Network error",
	AppAuthResult.PROVIDER_ERROR: "Provider error",
	AppAuthResult.UNSUPPORTED: "Unsupported",
	AppAuthResult.ERROR: "Error",
}
# Enough of a token to show that one arrived; the demo never shows or prints a whole token.
const TOKEN_PREFIX_LENGTH := 8


func _ready() -> void:
	_fit_safe_area()
	get_viewport().size_changed.connect(_fit_safe_area)
	%Platform.text = "AppAuth · %s" % OS.get_name()
	if AppAuth.is_supported():
		%Status.text = "Redirect URI: %s" % AppAuth.default_redirect_uri()
	else:
		%LogIn.disabled = true
		%Status.text = "Login is unavailable on %s: this operating system has no login backend." % OS.get_name()
	%LogIn.pressed.connect(_on_log_in_pressed)
	print(%Status.text)
	if DisplayServer.get_name() == "headless":
		print("APP_AUTH_DEMO_OK")
		get_tree().quit(0)


func _on_log_in_pressed() -> void:
	%Status.text = "Logging in…"
	%Details.text = ""
	var login: AppAuthLogin = AppAuth.login(ISSUER, CLIENT_ID, PackedStringArray(SCOPES))
	var result: AppAuthResult = await login.finished
	_show(result)


func _show(result: AppAuthResult) -> void:
	if result.status != AppAuthResult.OK:
		%Status.text = "%s: %s" % [STATUS_NAMES[result.status], result.message]
		%Details.text = "Provider error: %s" % result.provider_error if result.provider_error else ""
		print(%Status.text)
		return
	# Not every provider puts profile claims into the ID token; `sub` is always there.
	var user: String = result.claims.get("name", "subject %s" % result.claims.get("sub", "?"))
	%Status.text = "Signed in as %s" % user
	var expiry := "unknown"
	if result.expires_at > 0:
		expiry = Time.get_datetime_string_from_unix_time(result.expires_at, true) + " UTC"
	%Details.text = "Scopes: %s\nAccess token expires: %s\nAccess token: %s…\nRefresh token issued: %s" % [
		" ".join(result.scopes),
		expiry,
		result.access_token.substr(0, TOKEN_PREFIX_LENGTH),
		"yes" if result.has_refresh_token else "no",
	]
	print(%Status.text)


## Keeps the content out of notches and rounded corners: the display's safe area is in screen
## pixels, the layout in canvas units.
func _fit_safe_area() -> void:
	var safe := Rect2(DisplayServer.get_display_safe_area())
	if not safe.has_area():
		return
	var window_origin := Vector2(DisplayServer.window_get_position())
	var to_canvas := get_viewport().get_final_transform().affine_inverse()
	var top_left := to_canvas * (safe.position - window_origin)
	var bottom_right := to_canvas * (safe.end - window_origin)
	var visible := get_viewport_rect().size
	offset_left = maxf(top_left.x, 0.0)
	offset_top = maxf(top_left.y, 0.0)
	offset_right = minf(bottom_right.x - visible.x, 0.0)
	offset_bottom = minf(bottom_right.y - visible.y, 0.0)
