@tool
extends EditorPlugin

# Derives the project's build profile, as the Engine Compilation Configuration editor's
# "Detect from Project" and "Save As" do, and records that it did.
#
# Godot exposes no API for this: the editor's profile manager is a dialog of the editor
# with no bound methods. The plugin finds it by its class, presses the detect action by its
# enum value, answers the confirmation and gives the save dialog the path, so no caption of
# the editor and no node name takes part. The enum order of the manager's actions is the one
# of editor/settings/editor_build_profile.h; a change shows as a failed lookup.

@warning_ignore("inferred_declaration")
const Record = preload("res://addons/rules_godot_action/record.gd")

const MANAGER: String = "EditorBuildProfileManager"
const CONFIRMATION: String = "ConfirmationDialog"
# ACTION_DETECT of the profile manager's Action enum.
const ACTION_DETECT: int = 5

var _action: Dictionary


func _enter_tree() -> void:
	_action = Record.action()
	_derive.call_deferred()


func _derive() -> void:
	var filesystem: EditorFileSystem = EditorInterface.get_resource_filesystem()
	while filesystem.is_scanning():
		await get_tree().create_timer(0.1).timeout
	await get_tree().process_frame
	var managers: Array[Node] = _find(get_tree().root, func(node: Node) -> bool: return node.get_class() == MANAGER)
	if managers.size() != 1:
		return _fail("expected one %s, found %d" % [MANAGER, managers.size()])
	var manager: Node = managers[0]
	var detect: Button = _action_button(manager, ACTION_DETECT)
	if detect == null:
		return _fail("the profile manager has no button for its detect action")
	var dialogs: Array[Node] = _find(manager, func(node: Node) -> bool: return node.get_class() == CONFIRMATION)
	if dialogs.size() != 1:
		return _fail("expected one %s in the profile manager, found %d" % [CONFIRMATION, dialogs.size()])
	var confirmation: ConfirmationDialog = dialogs[0] as ConfirmationDialog
	# The detection runs synchronously when the dialog confirms.
	detect.pressed.emit()
	await get_tree().process_frame
	confirmation.confirmed.emit()
	await get_tree().process_frame
	var savers: Array[Node] = _find(manager, func(node: Node) -> bool: return node is EditorFileDialog and (node as EditorFileDialog).file_mode == EditorFileDialog.FILE_MODE_SAVE_FILE)
	if savers.size() != 1:
		return _fail("expected one save dialog in the profile manager, found %d" % savers.size())
	var path: String = _action["profile"]
	(savers[0] as EditorFileDialog).file_selected.emit(path)
	await get_tree().process_frame
	if not FileAccess.file_exists(path):
		return _fail("the profile manager wrote no profile to " + path)
	Record.write(_action, false, [], {})
	get_tree().quit(0)


func _fail(message: String) -> void:
	Record.write(_action, true, ["profile derivation: " + message], {})
	get_tree().quit(1)


# The nodes below the node, itself included, the predicate accepts.
func _find(node: Node, accepts: Callable) -> Array[Node]:
	var found: Array[Node] = []
	if accepts.call(node):
		found.append(node)
	for child: Node in node.get_children():
		found.append_array(_find(child, accepts))
	return found


# The button of the manager whose pressed signal calls its action handler with the action.
func _action_button(manager: Node, action: int) -> Button:
	var buttons: Array[Node] = _find(manager, func(node: Node) -> bool: return node is Button)
	for node: Node in buttons:
		var button: Button = node as Button
		for connection: Dictionary in button.get_signal_connection_list("pressed"):
			var handler: Callable = connection["callable"]
			var bound: Array = handler.get_bound_arguments()
			if bound.size() == 1 and bound[0] is int and bound[0] == action:
				return button
	return null
