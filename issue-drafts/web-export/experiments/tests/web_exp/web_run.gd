class_name GdUnitWebRunner
extends SceneTree

## EXPERIMENT(web tests): runs GdUnit's CI runner inside an exported web pack.
##
## Godot 4.6+ export templates ignore --script (disable_path_overrides, godotengine/godot#111909),
## so the pack names this class as its main loop: application/run/main_loop_type.
##
##     -- [<GdUnit options, such as -a res://suites>]
##
## Reports go to user://gdunit (Emscripten's IDBFS-backed /userfs). After GdUnit wrote
## them, the JUnit XML leaves the browser through one of two channels, both tried:
##  1. JavaScriptBridge: window.godotTestReport(name, text) on the harness page.
##  2. The log: the XML between marker lines, for a harness that only sees prints.

const REPORTS: String = "user://gdunit"


class WebRunner extends GdUnitTestCIRunner:
	var finish: Callable
	## Whether to find suites through ResourceLoader, which resolves the .remap files of
	## scripts exported as binary tokens, instead of GdUnit's FileAccess/DirAccess scan.
	var resolve_remaps: bool = false

	func quit(code: int) -> void:
		var exit_code: int = finish.call(code)
		await super(exit_code)

	func discover_tests() -> Array[GdUnitTestCase]:
		if not resolve_remaps:
			return super()
		var added: Signal = GdUnitSignals.instance().gdunit_test_discover_added
		_test_cases = _runner_config.test_cases()
		for path: String in _included_tests:
			for suite: String in _suites(path):
				GdUnitTestDiscoverer.discover_tests(load(suite), func(test: GdUnitTestCase) -> void:
					if not is_skipped(test):
						_test_cases.append(test)
						added.emit(test)
				)
		print("web_run: discovered %d tests through ResourceLoader" % _test_cases.size())
		return _test_cases

	## The suites at a res:// path: the script itself, or the suites below a directory.
	static func _suites(path: String) -> PackedStringArray:
		if ResourceLoader.exists(path):
			return PackedStringArray([path]) if _is_suite(path) else PackedStringArray()
		var found: PackedStringArray = PackedStringArray()
		for entry: String in ResourceLoader.list_directory(path):
			found.append_array(_suites(path.path_join(entry.trim_suffix("/"))))
		return found

	static func _is_suite(path: String) -> bool:
		if not path.ends_with(".gd"):
			return false
		var script: Script = load(path) as Script
		while script != null:
			if script.resource_path == "res://addons/gdUnit4/src/GdUnitTestSuite.gd":
				return true
			script = script.get_base_script()
		return false


func _initialize() -> void:
	var command: PackedStringArray = PackedStringArray(
		["GdUnitCmdTool.gd", "--ignoreHeadlessMode", "-c", "-rd", REPORTS, "-rc", "1"]
	)
	var user_args: PackedStringArray = OS.get_cmdline_user_args()
	var resolve_remaps: bool = user_args.has("--resolve-remaps")
	if resolve_remaps:
		user_args.remove_at(user_args.find("--resolve-remaps"))
	command.append_array(user_args)
	print("web_run: features web=%s debug=%s; display=%s; GdUnit args %s" % [
		OS.has_feature("web"), OS.is_debug_build(), DisplayServer.get_name(), command
	])
	var runner: WebRunner = WebRunner.new()
	runner.finish = _finish
	runner.resolve_remaps = resolve_remaps
	runner._debug_cmd_args = command
	root.add_child(runner)


func _finish(code: int) -> int:
	var reports: String = ProjectSettings.globalize_path(REPORTS)
	var results: String = _find(reports, "results.xml")
	print("web_run: GdUnit exit %d; reports in %s; JUnit at %s" % [code, reports, results])
	if results.is_empty():
		printerr("web_run: GdUnit wrote no JUnit report")
		return code if code != 0 else 1
	var xml: String = FileAccess.get_file_as_string(results)
	var window: JavaScriptObject = JavaScriptBridge.get_interface("window")
	if window != null and window.godotTestReport != null:
		window.godotTestReport("results.xml", xml)
		print("web_run: handed %d bytes of JUnit XML to window.godotTestReport" % xml.length())
	print("@@JUNIT-BEGIN@@")
	print(xml)
	print("@@JUNIT-END@@")
	return code


func _find(directory: String, file_name: String) -> String:
	var entries: DirAccess = DirAccess.open(directory)
	if entries == null:
		return ""
	for child: String in entries.get_directories():
		var found: String = _find(directory.path_join(child), file_name)
		if found:
			return found
	return directory.path_join(file_name) if entries.file_exists(file_name) else ""
