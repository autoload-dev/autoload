extends Node
## Checks what the runtime reads from the pack: a translation, a texture imported with
## feature-tagged variants and a global class. Quits with 1 on a failed check.


func _ready() -> void:
	var failures: Array[String] = []
	TranslationServer.set_locale("ja")
	if tr("HELLO") != "こんにちは":
		failures.append("translation: %s" % tr("HELLO"))
	var texture: Texture2D = load("res://main/tile.png") as Texture2D
	if texture == null or texture.get_width() != 4:
		failures.append("texture: %s" % texture)
	if RuntimeGreeter.new().greet() != "hello":
		failures.append("global class")
	for failure in failures:
		push_error("check failed: " + failure)
	print("runtime inputs: ", "failed" if failures else "ok")
	get_tree().quit(1 if failures else 0)
