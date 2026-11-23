@tool
extends Node

# A tool script, which the editor runs: its static constructor when it loads, its
# constructor when it is instantiated, and a tool button's callable when it is pressed.

const Guard = preload("res://guard/guard.gd")

static var marker: int = Guard.value("tool_node.gd static var")

@export_tool_button("Press", "Callable") var press: Callable = func() -> void: Guard.ran(
	"tool_node.gd tool button"
)


static func _static_init() -> void:
	Guard.ran("tool_node.gd _static_init")


func _init() -> void:
	Guard.ran("tool_node.gd _init")
