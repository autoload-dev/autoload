extends Control

const Counter = preload("res://addons/native_counter/counter.gd")
var counter = Counter.new()

func _ready() -> void:
	$Count.text = str(counter.increment())
