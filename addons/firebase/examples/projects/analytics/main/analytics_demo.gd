extends Control
## Logs Google Analytics for Firebase events and shows what happened.

var _count := 0


func _ready() -> void:
	%Platform.text = "Firebase · %s · %s" % [OS.get_name(), DemoNative.greeting()]
	if not FirebaseAnalytics.is_supported():
		%LogEvent.disabled = true
		%Status.text = "Firebase is unavailable on %s." % OS.get_name()
		return
	Firebase.initialized.connect(_on_initialized)
	_on_initialized(Firebase.is_initialized)
	%LogEvent.pressed.connect(_on_log_event_pressed)


func _on_initialized(ok: bool) -> void:
	%Status.text = "Firebase app initialized." if ok else "Firebase app not configured."


func _on_log_event_pressed() -> void:
	_count += 1
	FirebaseAnalytics.log_event("demo_button", {"count": _count, "source": "godot"})
	%Status.text = "Logged demo_button #%d." % _count
