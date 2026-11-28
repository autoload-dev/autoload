extends Node

# Creates a table in an in-memory database, reads it back and quits with 0 when the row
# arrived, 1 otherwise.


func _ready() -> void:
	var database := SQLiteDatabase.new()
	var success: bool = database.open()
	success = success and database.execute("CREATE TABLE messages (text TEXT)")
	success = success and database.execute("INSERT INTO messages VALUES (?)", ["Hello from the browser"])
	var rows: Array = database.query("SELECT text FROM messages") if success else []
	success = success and rows == [{"text": "Hello from the browser"}]
	database.close()
	print("sqlite on the web: %s" % ("ok" if success else database.get_last_error()))
	get_tree().quit(0 if success else 1)
