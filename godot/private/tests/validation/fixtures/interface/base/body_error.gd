class_name InterfaceBodyError
extends RefCounted
## A base whose body fails: its own validation fails, its interface does not.


func value() -> int:
	return "not an int"
