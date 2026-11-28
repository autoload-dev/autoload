#include <cstring>

#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/godot.hpp>
#include <godot_cpp/variant/array.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/packed_byte_array.hpp>
#include <sqlite3.h>

using namespace godot;

class SQLiteDatabase : public RefCounted {
  GDCLASS(SQLiteDatabase, RefCounted)

  sqlite3 *database = nullptr;
  String last_error;

  sqlite3_stmt *prepare(const String &sql, const Array &parameters) {
    last_error = "";
    if (!database) {
      last_error = "Database is closed";
      return nullptr;
    }
    sqlite3_stmt *statement = nullptr;
    const CharString text = sql.utf8();
    const char *tail = nullptr;
    int result = sqlite3_prepare_v2(database, text.get_data(), -1, &statement, &tail);
    if (result != SQLITE_OK) {
      last_error = String::utf8(sqlite3_errmsg(database));
      return nullptr;
    }
    while (tail && (*tail == ' ' || *tail == '\n' || *tail == '\r' || *tail == '\t')) {
      ++tail;
    }
    if (!statement || (tail && *tail)) {
      last_error = "Provide exactly one SQL statement";
      sqlite3_finalize(statement);
      return nullptr;
    }
    if (sqlite3_bind_parameter_count(statement) != parameters.size()) {
      last_error = "Parameter count does not match SQL placeholders";
      sqlite3_finalize(statement);
      return nullptr;
    }
    for (int i = 0; i < parameters.size(); ++i) {
      const Variant value = parameters[i];
      switch (value.get_type()) {
      case Variant::NIL:
        result = sqlite3_bind_null(statement, i + 1);
        break;
      case Variant::BOOL:
      case Variant::INT:
        result = sqlite3_bind_int64(statement, i + 1, int64_t(value));
        break;
      case Variant::FLOAT:
        result = sqlite3_bind_double(statement, i + 1, double(value));
        break;
      case Variant::STRING: {
        const CharString string = String(value).utf8();
        result = sqlite3_bind_text(statement, i + 1, string.get_data(),
                                   string.length(), SQLITE_TRANSIENT);
        break;
      }
      case Variant::PACKED_BYTE_ARRAY: {
        const PackedByteArray bytes = value;
        result = bytes.is_empty()
                     ? sqlite3_bind_zeroblob(statement, i + 1, 0)
                     : sqlite3_bind_blob(statement, i + 1, bytes.ptr(),
                                         bytes.size(), SQLITE_TRANSIENT);
        break;
      }
      default:
        result = SQLITE_MISMATCH;
      }
      if (result != SQLITE_OK) {
        last_error = String::utf8(sqlite3_errstr(result));
        sqlite3_finalize(statement);
        return nullptr;
      }
    }
    return statement;
  }

protected:
  static void _bind_methods() {
    ClassDB::bind_method(D_METHOD("open"), &SQLiteDatabase::open);
    ClassDB::bind_method(D_METHOD("close"), &SQLiteDatabase::close);
    ClassDB::bind_method(D_METHOD("execute", "sql", "parameters"),
                         &SQLiteDatabase::execute, DEFVAL(Array()));
    ClassDB::bind_method(D_METHOD("query", "sql", "parameters"),
                         &SQLiteDatabase::query, DEFVAL(Array()));
    ClassDB::bind_method(D_METHOD("get_last_error"), &SQLiteDatabase::get_last_error);
  }

public:
  ~SQLiteDatabase() { close(); }

  bool open() {
    last_error = "";
    if (database) {
      last_error = "Database is already open";
      return false;
    }
    const int result = sqlite3_open(":memory:", &database);
    if (result == SQLITE_OK) {
      return true;
    }
    last_error = String::utf8(sqlite3_errmsg(database));
    sqlite3_close(database);
    database = nullptr;
    return false;
  }

  void close() {
    sqlite3_close(database);
    database = nullptr;
    last_error = "";
  }

  bool execute(const String &sql, const Array &parameters) {
    sqlite3_stmt *statement = prepare(sql, parameters);
    if (!statement) {
      return false;
    }
    const int result = sqlite3_step(statement);
    if (result != SQLITE_DONE) {
      last_error = result == SQLITE_ROW ? "Use query for statements returning rows"
                                        : String::utf8(sqlite3_errmsg(database));
    }
    sqlite3_finalize(statement);
    return result == SQLITE_DONE;
  }

  Array query(const String &sql, const Array &parameters) {
    Array rows;
    sqlite3_stmt *statement = prepare(sql, parameters);
    if (!statement) {
      return rows;
    }
    if (sqlite3_column_count(statement) == 0) {
      last_error = "Use execute for statements without result columns";
      sqlite3_finalize(statement);
      return rows;
    }
    int result;
    while ((result = sqlite3_step(statement)) == SQLITE_ROW) {
      Dictionary row;
      for (int column = 0; column < sqlite3_column_count(statement); ++column) {
        Variant value;
        switch (sqlite3_column_type(statement, column)) {
        case SQLITE_INTEGER:
          value = int64_t(sqlite3_column_int64(statement, column));
          break;
        case SQLITE_FLOAT:
          value = sqlite3_column_double(statement, column);
          break;
        case SQLITE_TEXT:
          value = String::utf8(
              reinterpret_cast<const char *>(sqlite3_column_text(statement, column)),
              sqlite3_column_bytes(statement, column));
          break;
        case SQLITE_BLOB: {
          PackedByteArray bytes;
          const int size = sqlite3_column_bytes(statement, column);
          bytes.resize(size);
          if (size) {
            std::memcpy(bytes.ptrw(), sqlite3_column_blob(statement, column), size);
          }
          value = bytes;
          break;
        }
        }
        row[String::utf8(sqlite3_column_name(statement, column))] = value;
      }
      rows.append(row);
    }
    if (result != SQLITE_DONE) {
      last_error = String::utf8(sqlite3_errmsg(database));
      rows.clear();
    }
    sqlite3_finalize(statement);
    return rows;
  }

  String get_last_error() const { return last_error; }
};

static void initialize(ModuleInitializationLevel level) {
  if (level == MODULE_INITIALIZATION_LEVEL_SCENE) {
    ClassDB::register_class<SQLiteDatabase>();
  }
}

static void uninitialize(ModuleInitializationLevel) {}

extern "C" GDExtensionBool GDE_EXPORT sqlite_addon_init(
    GDExtensionInterfaceGetProcAddress get_proc_address,
    GDExtensionClassLibraryPtr library, GDExtensionInitialization *initialization) {
  GDExtensionBinding::InitObject init(get_proc_address, library, initialization);
  init.register_initializer(initialize);
  init.register_terminator(uninitialize);
  init.set_minimum_library_initialization_level(MODULE_INITIALIZATION_LEVEL_SCENE);
  return init.init();
}
