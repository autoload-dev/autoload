extends Node

var _hello: Object

func _ready() -> void:
	print("WEBHELLO features: web=%s web_extensions=%s threads=%s nothreads=%s" % [
		OS.has_feature("web"), OS.has_feature("web_extensions"),
		OS.has_feature("threads"), OS.has_feature("nothreads")])
	if OS.has_feature("web"):
		print("WEBHELLO crossOriginIsolated=%s" % JavaScriptBridge.eval("String(self.crossOriginIsolated)"))
	if not ClassDB.class_exists("WebHello"):
		print("WEBHELLO RESULT=FAIL class WebHello is not registered")
		get_tree().quit()
		return
	_hello = ClassDB.instantiate("WebHello")
	print("WEBHELLO add(40, 2)=%d" % _hello.add(40, 2))
	print("WEBHELLO %s" % _hello.greet("Godot"))
	var main_bumps = [_hello.bump(), _hello.bump()]
	print("WEBHELLO main thread bump()=%s" % [main_bumps])
	if OS.has_feature("threads"):
		var thread := Thread.new()
		thread.start(_on_thread)
		var worker_bumps = thread.wait_to_finish()
		print("WEBHELLO worker thread bump()=%s add=%d" % [worker_bumps[0], worker_bumps[1]])
		if worker_bumps[0] != [1, 2]:
			print("WEBHELLO RESULT=FAIL thread_local not per thread")
			get_tree().quit()
			return
	print("WEBHELLO RESULT=PASS")
	get_tree().quit()

func _on_thread() -> Array:
	return [[_hello.bump(), _hello.bump()], _hello.add(1, 2)]
