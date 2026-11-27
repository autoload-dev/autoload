extends RefCounted

## Selects the cases a rules_godot test adapter runs under Bazel's test contract.
##
## The adapter decides which listed files are cases. TESTBRIDGE_TEST_ONLY (bazel test
## --test_filter) then keeps the cases whose path contains it, and TEST_TOTAL_SHARDS and
## TEST_SHARD_INDEX select among those round-robin, so every shard sees the same list.


## Returns the `res://` paths listed in the file at path that this run selects, or
## the exit code the run ends with when it selects none. is_case keeps the listed
## files that are cases; noun names a case in messages, such as "suite". A run whose
## filter or shard leaves no case passes; one without any case fails.
static func select(path: String, noun: String, is_case: Callable) -> Variant:
	var total: int = OS.get_environment("TEST_TOTAL_SHARDS").to_int()
	var status: String = OS.get_environment("TEST_SHARD_STATUS_FILE")
	if total > 0 and status:
		# Creating the file tells Bazel the test supports sharding, whatever this shard runs.
		var _status_file: FileAccess = FileAccess.open(status, FileAccess.WRITE)
	var cases: PackedStringArray = _kept(FileAccess.get_file_as_string(path).split("\n", false), is_case)
	if cases.is_empty():
		printerr("rules_godot: the test lists no %s" % noun)
		return 1
	var only: String = OS.get_environment("TESTBRIDGE_TEST_ONLY")
	if only:
		cases = _filter(cases, only)
		if cases.is_empty():
			print("rules_godot: --test_filter=%s matches no %s" % [only, noun])
			return 0
	if total > 0:
		cases = _shard(cases, OS.get_environment("TEST_SHARD_INDEX").to_int(), total)
		if cases.is_empty():
			print("rules_godot: no %ss in this shard" % noun)
			return 0
	return cases


static func _kept(files: PackedStringArray, is_case: Callable) -> PackedStringArray:
	var kept: Array[String] = []
	for file: String in files:
		var case: bool = is_case.call(file)
		if case:
			kept.append(file)
	return PackedStringArray(kept)


static func _filter(cases: PackedStringArray, only: String) -> PackedStringArray:
	var selected: Array[String] = []
	for case: String in cases:
		if case.contains(only):
			selected.append(case)
	return PackedStringArray(selected)


static func _shard(cases: PackedStringArray, index: int, total: int) -> PackedStringArray:
	var selected: Array[String] = []
	for position: int in cases.size():
		if position % total == index:
			selected.append(cases[position])
	return PackedStringArray(selected)
