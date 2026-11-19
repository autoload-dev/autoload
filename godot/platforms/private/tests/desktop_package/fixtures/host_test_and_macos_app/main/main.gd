extends Node

const Base = preload("res://main/base.gd")


func _ready() -> void:
	print(Base.greeting())
