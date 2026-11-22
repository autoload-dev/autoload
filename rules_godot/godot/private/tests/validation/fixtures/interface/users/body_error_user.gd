extends RefCounted
## Uses a base whose body fails, which fails only the base's own validation.


func use() -> int:
	return InterfaceBodyError.new().value()
