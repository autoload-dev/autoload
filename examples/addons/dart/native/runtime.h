// The Dart isolate that runs a project's scripts, and the conversion of values between
// Godot variants and Dart objects.

#pragma once

#include <unordered_map>

#include <godot_cpp/variant/array.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/string.hpp>
#include <godot_cpp/variant/variant.hpp>

#include "include/dart_api.h"

namespace dart_godot {

class Runtime {
public:
	static Runtime &get();

	// Where the extension library lies; the scripts' snapshot is beside it.
	void set_library_path(const godot::String &p_path) { library_path = p_path; }

	// Starts the isolate on first use. False, with the reason reported, when it cannot or
	// after shutdown: the Dart VM does not start again once it shut down.
	bool ensure_started();
	void shutdown();

	// Calls a function of package:godot/src/embedder.dart. Requires a Scope; the result
	// may be an error handle.
	Dart_Handle invoke(const char *p_function, int p_argc, Dart_Handle *p_argv);

	// Calls a private function of package:godot/src/object.dart, the only library that
	// creates and releases the Dart objects of Godot objects. Requires a Scope.
	Dart_Handle invoke_objects(const char *p_function, int p_argc, Dart_Handle *p_argv);

	// The Dart string of a constant name, such as a function or field name, created once.
	// Requires a Scope.
	Dart_Handle name(const char *p_name);

	Dart_Handle to_dart(const godot::Variant &p_value);
	godot::Variant to_variant(Dart_Handle p_value);

	// Reports an error handle as a Godot error; true when the handle was an error.
	static bool report(Dart_Handle p_handle, const char *p_context);

	Dart_Isolate get_isolate() const { return isolate; }
	bool is_running() const { return state == State::RUNNING; }

private:
	bool start_isolate();
	bool bind_scripts();

	Dart_Handle composite_to_dart(const godot::Variant &p_value);
	Dart_Handle object_to_dart(godot::Object *p_object);
	Dart_Handle list_to_dart(const godot::Array &p_array);

	uint32_t function_hash(Dart_Handle p_function);
	bool typed_to_variant(Dart_Handle p_value, godot::Variant &r_value);
	bool collection_to_variant(Dart_Handle p_value, godot::Variant &r_value);
	godot::Array list_to_variant(Dart_Handle p_list);
	godot::Dictionary map_to_variant(Dart_Handle p_map);

	enum class State {
		IDLE,
		RUNNING,
		FAILED,
		STOPPED,
	};

	godot::String library_path;
	State state = State::IDLE;
	Dart_Isolate isolate = nullptr;
	std::unordered_map<const char *, Dart_PersistentHandle> names;
	Dart_PersistentHandle embedder = nullptr;
	Dart_PersistentHandle objects = nullptr;
	Dart_PersistentHandle object_type = nullptr;
	Dart_PersistentHandle vector2_type = nullptr;
	Dart_PersistentHandle color_type = nullptr;
};

// Enters the isolate and a Dart API scope on this thread, unless the thread is already in
// one: Dart code calls Godot, which may call Dart again. The outermost scope runs the
// microtasks that Dart code scheduled before it leaves.
class Scope {
public:
	Scope();
	~Scope();
	Scope(const Scope &) = delete;
	Scope &operator=(const Scope &) = delete;

private:
	bool acquired = false;
};

} // namespace dart_godot
