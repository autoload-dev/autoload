extends GdUnitTestSuite

func test_parameterized_round_trip() -> void:
	var database = SQLiteDatabase.new()
	assert_bool(database.open()).is_true()
	assert_bool(database.execute("CREATE TABLE messages (id INTEGER, text TEXT)")).is_true()
	var message := "It's a parameter; DROP TABLE messages; --"
	assert_bool(database.execute("INSERT INTO messages VALUES (?, ?)", [7, message])).is_true()
	assert_array(database.query("SELECT id, text FROM messages WHERE id = ?", [7])).contains_exactly([
		{"id": 7, "text": message},
	])
	assert_str(database.get_last_error()).is_empty()
	assert_array(database.query("INSERT INTO messages VALUES (8, 'not inserted')")).is_empty()
	assert_str(database.get_last_error()).contains("Use execute")
	assert_array(database.query("SELECT id FROM messages")).contains_exactly([{"id": 7}])
	database.close()

func test_values_and_errors() -> void:
	var database = SQLiteDatabase.new()
	assert_bool(database.open()).is_true()
	var bytes := PackedByteArray([0, 255, 19])
	var rows: Array = database.query("SELECT ? AS missing, ? AS real, ? AS bytes", [null, 1.25, bytes])
	assert_array(rows).has_size(1)
	assert_dict(rows[0]).contains_key_value("missing", null)
	assert_dict(rows[0]).contains_key_value("real", 1.25)
	assert_dict(rows[0]).contains_key_value("bytes", bytes)
	assert_bool(database.execute("SELECT ?", [])).is_false()
	assert_str(database.get_last_error()).contains("Parameter count")
	assert_bool(database.execute("THIS IS NOT SQL")).is_false()
	assert_str(database.get_last_error()).is_not_empty()
	database.close()
	assert_array(database.query("SELECT 1")).is_empty()
	assert_str(database.get_last_error()).contains("closed")
	assert_bool(database.open()).is_true()
	assert_str(database.get_last_error()).is_empty()
	database.close()
