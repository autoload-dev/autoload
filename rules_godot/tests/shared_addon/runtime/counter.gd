extends RefCounted

var _native: NativeCounter = NativeCounter.new()

func _notification(what: int) -> void:
	if what == NOTIFICATION_PREDELETE:
		_native.free()

func increment(amount: int = 1) -> int:
	_native.increment(amount)
	return _native.get_value()

func value() -> int:
	return _native.get_value()

func reset() -> void:
	_native.reset()
