extends Node

func _ready() -> void:
	print("WEBHELLO crossOriginIsolated=%s" % JavaScriptBridge.eval("String(self.crossOriginIsolated)"))
	if not ClassDB.class_exists("SQLiteDatabase"):
		print("WEBHELLO RESULT=FAIL class SQLiteDatabase is not registered")
		get_tree().quit()
		return
	var db = ClassDB.instantiate("SQLiteDatabase")
	var ok: bool = db.open()
	ok = ok and db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT, score REAL)", [])
	ok = ok and db.execute("INSERT INTO t (name, score) VALUES (?, ?)", ["wasm", 4.5])
	ok = ok and db.execute("INSERT INTO t (name, score) VALUES (?, ?)", ["godot", 3.25])
	var rows: Array = db.query("SELECT name, score, sqlite_version() AS v FROM t ORDER BY score DESC", [])
	print("WEBHELLO rows=%s error='%s'" % [rows, db.get_last_error()])
	print("WEBHELLO RESULT=%s" % ("PASS" if ok and rows.size() == 2 and rows[0]["name"] == "wasm" else "FAIL"))
	get_tree().quit()
