extends Control

const Counter = preload("res://main/native_counter/counter.gd")

func _ready() -> void:
	var counter = Counter.new()
	$Count.text = "Add-on count: %d" % counter.increment(2)
