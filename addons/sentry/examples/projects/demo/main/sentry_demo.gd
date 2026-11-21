extends Control
## Reports a breadcrumb and a message to Sentry and shows what happened. Lines with the
## SENTRY_DEMO: prefix let a device log be filtered for the demo's output.


func _ready() -> void:
	var enabled := SentrySDK.is_enabled()
	_report("platform=%s enabled=%s" % [OS.get_name(), enabled])
	%Capture.pressed.connect(_capture)
	if enabled:
		_capture()


func _capture() -> void:
	SentrySDK.add_breadcrumb(SentryBreadcrumb.create("Demo started"))
	var event_id := SentrySDK.capture_message("Hello from the Sentry demo")
	_report("event_id=%s" % event_id)


func _report(line: String) -> void:
	print("SENTRY_DEMO: ", line)
	%Status.text += line + "\n"
