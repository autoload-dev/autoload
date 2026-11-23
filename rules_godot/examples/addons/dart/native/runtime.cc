#include "runtime.h"

#include <cstring>

#include <godot_cpp/classes/class_db_singleton.hpp>
#include <godot_cpp/classes/engine.hpp>
#include <godot_cpp/core/object.hpp>
#include <godot_cpp/variant/array.hpp>
#include <godot_cpp/variant/callable_custom.hpp>
#include <godot_cpp/variant/color.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/utility_functions.hpp>
#include <godot_cpp/variant/vector2.hpp>

#include "include/dart_engine.h"
#include "instance.h"

using namespace godot;

namespace dart_godot {

namespace {

// The snapshot of a project's scripts, beside the extension library. Android applications
// deliver only lib*.so files beside it, so every platform uses that name.
constexpr const char *SNAPSHOT_NAME = "libdart_scripts.so";

Dart_Handle lookup_library(const char *p_url) {
	return Dart_LookupLibrary(Dart_NewStringFromCString(p_url));
}

Dart_Handle lookup_type(const char *p_library, const char *p_name) {
	return Dart_GetNonNullableType(lookup_library(p_library), Dart_NewStringFromCString(p_name), 0, nullptr);
}

String to_string(Dart_Handle p_string) {
	uint8_t *utf8 = nullptr;
	intptr_t length = 0;
	if (Dart_IsError(Dart_StringToUTF8(p_string, &utf8, &length))) {
		return String();
	}
	return String::utf8(reinterpret_cast<const char *>(utf8), length);
}

Dart_Handle to_dart_string(const String &p_string) {
	const CharString utf8 = p_string.utf8();
	return Dart_NewStringFromUTF8(reinterpret_cast<const uint8_t *>(utf8.get_data()), utf8.length());
}

double to_double(Dart_Handle p_handle) {
	double value = 0;
	if (Dart_IsInteger(p_handle)) {
		int64_t integer = 0;
		Dart_IntegerToInt64(p_handle, &integer);
		return static_cast<double>(integer);
	}
	Dart_DoubleValue(p_handle, &value);
	return value;
}

double field(Dart_Handle p_object, const char *p_name) {
	return to_double(Dart_GetField(p_object, Runtime::get().name(p_name)));
}

bool is_instance_of(Dart_Handle p_object, Dart_PersistentHandle p_type) {
	bool result = false;
	return !Dart_IsError(Dart_ObjectIsType(p_object, Dart_HandleFromPersistent(p_type), &result)) && result;
}

bool is_list_type(Variant::Type p_type) {
	return p_type == Variant::ARRAY || p_type >= Variant::PACKED_BYTE_ARRAY;
}

bool is_text_type(Variant::Type p_type) {
	return p_type == Variant::STRING || p_type == Variant::STRING_NAME || p_type == Variant::NODE_PATH;
}

// Null, booleans, numbers and text as Dart objects; null for other values.
Dart_Handle scalar_to_dart(const Variant &p_value) {
	if (is_text_type(p_value.get_type())) {
		return to_dart_string(p_value.stringify());
	}
	switch (p_value.get_type()) {
		case Variant::NIL:
			return Dart_Null();
		case Variant::BOOL:
			return Dart_NewBoolean(static_cast<bool>(p_value));
		case Variant::INT:
			return Dart_NewInteger(static_cast<int64_t>(p_value));
		case Variant::FLOAT:
			return Dart_NewDouble(static_cast<double>(p_value));
		default:
			return nullptr;
	}
}

// Dart's null, booleans, numbers and strings as variants; false for other objects.
bool scalar_to_variant(Dart_Handle p_value, Variant &r_value) {
	if (Dart_IsNull(p_value) || Dart_IsError(p_value)) {
		r_value = Variant();
	} else if (Dart_IsBoolean(p_value)) {
		bool value = false;
		Dart_BooleanValue(p_value, &value);
		r_value = value;
	} else if (Dart_IsInteger(p_value)) {
		int64_t value = 0;
		Dart_IntegerToInt64(p_value, &value);
		r_value = value;
	} else if (Dart_IsNumber(p_value)) {
		r_value = to_double(p_value);
	} else if (Dart_IsString(p_value)) {
		r_value = to_string(p_value);
	} else {
		return false;
	}
	return true;
}

// A Dart function that Godot calls as a Callable, such as a signal's target. Two are equal
// when their functions are equal in Dart, as two tear-offs of one object's method are, so
// Dart code can disconnect what it connected.
class DartCallable : public CallableCustom {
public:
	DartCallable(Dart_Handle p_function, uint32_t p_hash) :
			function(Dart_NewPersistentHandle(p_function)), function_hash(p_hash) {}

	~DartCallable() override {
		if (Runtime::get().get_isolate() == nullptr) {
			return;
		}
		Scope scope;
		Dart_DeletePersistentHandle(function);
	}

	uint32_t hash() const override { return function_hash; }
	String get_as_text() const override { return "<Dart function>"; }
	CompareEqualFunc get_compare_equal_func() const override { return &equal; }
	CompareLessFunc get_compare_less_func() const override { return &less; }
	// A Dart function belongs to no Godot object; it stays callable while it exists.
	ObjectID get_object() const override { return ObjectID(); }
	bool is_valid() const override { return true; }

	void call(const Variant **p_arguments, int p_argcount, Variant &r_return_value, GDExtensionCallError &r_call_error) const override {
		Runtime &runtime = Runtime::get();
		r_call_error.error = GDEXTENSION_CALL_OK;
		if (!runtime.is_running()) {
			return;
		}
		Scope scope;
		Dart_Handle arguments = Dart_NewList(p_argcount);
		for (int i = 0; i < p_argcount; i++) {
			Dart_ListSetAt(arguments, i, runtime.to_dart(*p_arguments[i]));
		}
		Dart_Handle argv[] = { Dart_HandleFromPersistent(function), arguments };
		Dart_Handle result = runtime.invoke("callFunction", 2, argv);
		if (!Runtime::report(result, "calling a Dart function")) {
			r_return_value = runtime.to_variant(result);
		}
	}

private:
	static bool equal(const CallableCustom *p_a, const CallableCustom *p_b) {
		const DartCallable *a = static_cast<const DartCallable *>(p_a);
		const DartCallable *b = static_cast<const DartCallable *>(p_b);
		if (a == b) {
			return true;
		}
		if (a->function_hash != b->function_hash || !Runtime::get().is_running()) {
			return false;
		}
		Scope scope;
		bool result = false;
		Dart_ObjectEquals(Dart_HandleFromPersistent(a->function), Dart_HandleFromPersistent(b->function), &result);
		return result;
	}

	// Orders by hash, then by Dart equality, so equal functions are never less than each other.
	static bool less(const CallableCustom *p_a, const CallableCustom *p_b) {
		const DartCallable *a = static_cast<const DartCallable *>(p_a);
		const DartCallable *b = static_cast<const DartCallable *>(p_b);
		if (a->function_hash != b->function_hash) {
			return a->function_hash < b->function_hash;
		}
		return !equal(p_a, p_b) && p_a < p_b;
	}

	Dart_PersistentHandle function;
	uint32_t function_hash;
};

// The functions package:godot/src/natives.dart declares.

Object *object_of(int64_t p_id) {
	Object *object = ObjectDB::get_instance(static_cast<uint64_t>(p_id));
	if (object == nullptr) {
		UtilityFunctions::push_error("Dart script used a freed Godot object (ID ", p_id, ").");
	}
	return object;
}

Dart_Handle object_call(int64_t p_id, Dart_Handle p_method, Dart_Handle p_arguments) {
	Object *object = object_of(p_id);
	if (object == nullptr) {
		return Dart_Null();
	}
	Runtime &runtime = Runtime::get();
	const Array arguments = runtime.to_variant(p_arguments);
	return runtime.to_dart(object->callv(to_string(p_method), arguments));
}

Dart_Handle object_get(int64_t p_id, Dart_Handle p_property) {
	Object *object = object_of(p_id);
	return object == nullptr ? Dart_Null() : Runtime::get().to_dart(object->get(to_string(p_property)));
}

void object_set(int64_t p_id, Dart_Handle p_property, Dart_Handle p_value) {
	Object *object = object_of(p_id);
	if (object != nullptr) {
		object->set(to_string(p_property), Runtime::get().to_variant(p_value));
	}
}

Dart_Handle singleton(Dart_Handle p_name) {
	return Runtime::get().to_dart(Engine::get_singleton()->get_singleton(to_string(p_name)));
}

void print(Dart_Handle p_message) {
	UtilityFunctions::print(to_string(p_message));
}

void error(Dart_Handle p_message) {
	UtilityFunctions::push_error(to_string(p_message));
}

void *resolve_native(const char *p_name, uintptr_t p_argument_count) {
	struct Native {
		const char *name;
		void *function;
	};
	static const Native natives[] = {
		{ "godot_dart_object_call", reinterpret_cast<void *>(&object_call) },
		{ "godot_dart_object_get", reinterpret_cast<void *>(&object_get) },
		{ "godot_dart_object_set", reinterpret_cast<void *>(&object_set) },
		{ "godot_dart_singleton", reinterpret_cast<void *>(&singleton) },
		{ "godot_dart_print", reinterpret_cast<void *>(&print) },
		{ "godot_dart_error", reinterpret_cast<void *>(&error) },
	};
	for (const Native &native : natives) {
		if (std::strcmp(native.name, p_name) == 0) {
			return native.function;
		}
	}
	return nullptr;
}

// Runs the isolate's messages, such as timers and completed futures, on the main thread.
void handle_messages() {
	Dart_Isolate isolate = Runtime::get().get_isolate();
	if (isolate != nullptr) {
		DartEngine_HandleMessage(isolate);
	}
}

void schedule_messages(Dart_Isolate, void *) {
	callable_mp_static(&handle_messages).call_deferred();
}

void report_message_error(Dart_Handle p_error, Dart_Isolate) {
	Runtime::report(p_error, "handling a Dart message");
}

} // namespace

Runtime &Runtime::get() {
	static Runtime runtime;
	return runtime;
}

bool Runtime::ensure_started() {
	if (state == State::IDLE) {
		state = start_isolate() && bind_scripts() ? State::RUNNING : State::FAILED;
	}
	return state == State::RUNNING;
}

bool Runtime::start_isolate() {
	const String snapshot = library_path.get_base_dir().path_join(SNAPSHOT_NAME);
	char *error = nullptr;
	if (!DartEngine_Init(&error)) {
		UtilityFunctions::push_error("Dart: cannot initialize the VM: ", error);
		return false;
	}
	DartEngine_SnapshotData data = DartEngine_AotSnapshotFromFile(snapshot.utf8().get_data(), &error);
	if (error != nullptr) {
		UtilityFunctions::push_error("Dart: cannot load the scripts' snapshot ", snapshot, ": ", error);
		return false;
	}
	isolate = DartEngine_CreateIsolate(data, &error);
	if (isolate == nullptr) {
		UtilityFunctions::push_error("Dart: cannot start the scripts' isolate: ", error);
		return false;
	}
	DartEngine_SetHandleMessageErrorCallback(&report_message_error);
	DartEngine_SetDefaultMessageScheduler({ &schedule_messages, nullptr });
	return true;
}

bool Runtime::bind_scripts() {
	Scope scope;
	Dart_Handle natives = lookup_library("package:godot/src/natives.dart");
	if (report(natives, "finding the Godot natives") ||
			report(Dart_SetFfiNativeResolver(natives, &resolve_native), "resolving the Godot natives")) {
		return false;
	}
	embedder = Dart_NewPersistentHandle(lookup_library("package:godot/src/embedder.dart"));
	objects = Dart_NewPersistentHandle(lookup_library("package:godot/src/object.dart"));
	object_type = Dart_NewPersistentHandle(lookup_type("package:godot/src/object.dart", "GodotObject"));
	vector2_type = Dart_NewPersistentHandle(lookup_type("package:godot/src/values.dart", "Vector2"));
	color_type = Dart_NewPersistentHandle(lookup_type("package:godot/src/values.dart", "Color"));
	// The generated entry point registers the project's scripts.
	return !report(Dart_Invoke(Dart_RootLibrary(), Dart_NewStringFromCString("main"), 0, nullptr), "registering the Dart scripts");
}

void Runtime::shutdown() {
	if (isolate == nullptr) {
		return;
	}
	{
		Scope scope;
		for (Dart_PersistentHandle *handle : { &embedder, &objects, &object_type, &vector2_type, &color_type }) {
			if (*handle != nullptr) {
				Dart_DeletePersistentHandle(*handle);
				*handle = nullptr;
			}
		}
		for (const auto &[_, handle] : names) {
			Dart_DeletePersistentHandle(handle);
		}
		names.clear();
	}
	isolate = nullptr;
	state = State::STOPPED;
	DartEngine_Shutdown();
}

Dart_Handle Runtime::invoke(const char *p_function, int p_argc, Dart_Handle *p_argv) {
	return Dart_Invoke(Dart_HandleFromPersistent(embedder), name(p_function), p_argc, p_argv);
}

Dart_Handle Runtime::invoke_objects(const char *p_function, int p_argc, Dart_Handle *p_argv) {
	return Dart_Invoke(Dart_HandleFromPersistent(objects), name(p_function), p_argc, p_argv);
}

uint32_t Runtime::function_hash(Dart_Handle p_function) {
	Dart_Handle argv[] = { p_function };
	int64_t hash = 0;
	Dart_IntegerToInt64(invoke("hashOf", 1, argv), &hash);
	return static_cast<uint32_t>(hash);
}

Dart_Handle Runtime::name(const char *p_name) {
	auto found = names.find(p_name);
	if (found == names.end()) {
		found = names.emplace(p_name, Dart_NewPersistentHandle(Dart_NewStringFromCString(p_name))).first;
	}
	return Dart_HandleFromPersistent(found->second);
}

bool Runtime::report(Dart_Handle p_handle, const char *p_context) {
	if (!Dart_IsError(p_handle)) {
		return false;
	}
	UtilityFunctions::push_error("Dart: error ", p_context, ": ", Dart_GetError(p_handle));
	return true;
}

Dart_Handle Runtime::object_to_dart(Object *p_object) {
	if (p_object == nullptr) {
		return Dart_Null();
	}
	if (Instance *instance = find_instance(p_object)) {
		return Dart_HandleFromPersistent(instance->object);
	}
	// The object's class and its ancestors, for the most derived view Dart has.
	PackedStringArray names;
	ClassDBSingleton *class_db = ClassDBSingleton::get_singleton();
	for (StringName name = p_object->get_class(); !String(name).is_empty(); name = class_db->get_parent_class(name)) {
		names.push_back(name);
	}
	Dart_Handle classes = Dart_NewList(names.size());
	for (int64_t i = 0; i < names.size(); i++) {
		Dart_ListSetAt(classes, i, to_dart_string(names[i]));
	}
	Dart_Handle argv[] = { Dart_NewInteger(static_cast<int64_t>(p_object->get_instance_id())), classes };
	return invoke_objects("_wrapObject", 2, argv);
}

Dart_Handle Runtime::list_to_dart(const Array &p_array) {
	Dart_Handle list = Dart_NewList(p_array.size());
	for (int64_t i = 0; i < p_array.size(); i++) {
		Dart_ListSetAt(list, i, to_dart(p_array[i]));
	}
	return list;
}

Dart_Handle Runtime::to_dart(const Variant &p_value) {
	Dart_Handle result = scalar_to_dart(p_value);
	if (result == nullptr) {
		result = composite_to_dart(p_value);
	}
	if (result == nullptr) {
		UtilityFunctions::push_warning("Dart: ", Variant::get_type_name(p_value.get_type()), " values have no Dart type; Dart receives null.");
		return Dart_Null();
	}
	return result;
}

Dart_Handle Runtime::composite_to_dart(const Variant &p_value) {
	switch (p_value.get_type()) {
		case Variant::VECTOR2:
		case Variant::VECTOR2I: {
			const Vector2 vector = p_value;
			Dart_Handle argv[] = { Dart_NewDouble(vector.x), Dart_NewDouble(vector.y) };
			return Dart_New(Dart_HandleFromPersistent(vector2_type), Dart_Null(), 2, argv);
		}
		case Variant::COLOR: {
			const Color color = p_value;
			Dart_Handle argv[] = { Dart_NewDouble(color.r), Dart_NewDouble(color.g), Dart_NewDouble(color.b), Dart_NewDouble(color.a) };
			return Dart_New(Dart_HandleFromPersistent(color_type), Dart_Null(), 4, argv);
		}
		case Variant::OBJECT:
			return object_to_dart(p_value.get_validated_object());
		case Variant::DICTIONARY: {
			const Dictionary dictionary = p_value;
			Dart_Handle argv[] = { list_to_dart(dictionary.keys()), list_to_dart(dictionary.values()) };
			return invoke("mapOf", 2, argv);
		}
		default:
			return is_list_type(p_value.get_type()) ? list_to_dart(p_value) : nullptr;
	}
}

Variant Runtime::to_variant(Dart_Handle p_value) {
	Variant result;
	if (scalar_to_variant(p_value, result)) {
		return result;
	}
	if (typed_to_variant(p_value, result)) {
		return result;
	}
	if (collection_to_variant(p_value, result)) {
		return result;
	}
	UtilityFunctions::push_warning("Dart: ", to_string(Dart_ToString(p_value)), " has no Godot type; Godot receives null.");
	return Variant();
}

bool Runtime::typed_to_variant(Dart_Handle p_value, Variant &r_value) {
	if (is_instance_of(p_value, object_type)) {
		int64_t id = 0;
		Dart_IntegerToInt64(Dart_GetField(p_value, name("id")), &id);
		r_value = ObjectDB::get_instance(static_cast<uint64_t>(id));
	} else if (is_instance_of(p_value, vector2_type)) {
		r_value = Vector2(field(p_value, "x"), field(p_value, "y"));
	} else if (is_instance_of(p_value, color_type)) {
		r_value = Color(field(p_value, "r"), field(p_value, "g"), field(p_value, "b"), field(p_value, "a"));
	} else if (Dart_IsClosure(p_value)) {
		r_value = Callable(memnew(DartCallable(p_value, function_hash(p_value))));
	} else {
		return false;
	}
	return true;
}

bool Runtime::collection_to_variant(Dart_Handle p_value, Variant &r_value) {
	if (Dart_IsList(p_value)) {
		r_value = list_to_variant(p_value);
	} else if (Dart_IsMap(p_value)) {
		r_value = map_to_variant(p_value);
	} else {
		return false;
	}
	return true;
}

Array Runtime::list_to_variant(Dart_Handle p_list) {
	intptr_t length = 0;
	Dart_ListLength(p_list, &length);
	Array array;
	for (intptr_t i = 0; i < length; i++) {
		array.push_back(to_variant(Dart_ListGetAt(p_list, i)));
	}
	return array;
}

Dictionary Runtime::map_to_variant(Dart_Handle p_map) {
	Dart_Handle keys = Dart_MapKeys(p_map);
	intptr_t length = 0;
	Dart_ListLength(keys, &length);
	Dictionary dictionary;
	for (intptr_t i = 0; i < length; i++) {
		Dart_Handle key = Dart_ListGetAt(keys, i);
		dictionary[to_variant(key)] = to_variant(Dart_MapGetAt(p_map, key));
	}
	return dictionary;
}

Scope::Scope() {
	Dart_Isolate isolate = Runtime::get().get_isolate();
	if (Dart_CurrentIsolate() != isolate) {
		DartEngine_AcquireIsolate(isolate);
		acquired = true;
	}
	Dart_EnterScope();
}

Scope::~Scope() {
	if (acquired) {
		Runtime::report(DartEngine_DrainMicrotasksQueue(), "running Dart microtasks");
	}
	Dart_ExitScope();
	if (acquired) {
		DartEngine_ReleaseIsolate();
	}
}

} // namespace dart_godot
