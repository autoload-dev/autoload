class_name DlcLevel
extends Node

# The base pack provides this shared script.
const Example = preload("res://main/shared/math.gd")


func answer() -> int:
	return Example.answer()
