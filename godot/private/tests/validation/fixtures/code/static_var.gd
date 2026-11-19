extends RefCounted

# A static variable whose initializer runs when Godot loads the script for running.

const Guard = preload("res://guard/guard.gd")

static var marker: int = Guard.value("static_var.gd static var")
