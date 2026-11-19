extends Node


func _ready() -> void:
	print(VendoredSentryLogger.new().capture("ready"))
