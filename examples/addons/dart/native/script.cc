#include "script.h"

#include <godot_cpp/classes/engine.hpp>
#include <godot_cpp/godot.hpp>
#include <godot_cpp/variant/utility_functions.hpp>

#include "instance.h"
#include "language.h"
#include "runtime.h"

using namespace godot;

namespace dart_godot {

DartScript::~DartScript() {
	if (!described || Runtime::get().get_isolate() == nullptr) {
		return;
	}
	Scope scope;
	if (description.script != nullptr) {
		Dart_DeletePersistentHandle(description.script);
	}
	for (const KeyValue<StringName, Dart_PersistentHandle> &name : description.names) {
		Dart_DeletePersistentHandle(name.value);
	}
}

void DartScript::add_names(const PackedStringArray &p_names) const {
	Runtime &runtime = Runtime::get();
	for (const String &name : p_names) {
		description.names.insert(name, Dart_NewPersistentHandle(runtime.to_dart(name)));
	}
}

const DartScript::Description &DartScript::describe() const {
	// A script the editor just created has no path, nor a compiled class until a build.
	if (described || script_path.is_empty()) {
		return description;
	}
	described = true;
	Runtime &runtime = Runtime::get();
	if (!runtime.ensure_started()) {
		return description;
	}
	Scope scope;
	Dart_Handle argv[] = { runtime.to_dart(script_path) };
	Dart_Handle result = runtime.invoke("describeScript", 1, argv);
	if (Runtime::report(result, "describing a script")) {
		return description;
	}
	if (Dart_IsNull(result)) {
		UtilityFunctions::push_error("Dart: no compiled script for ", script_path, "; the scripts' snapshot lists only the scripts the build compiled.");
		return description;
	}
	description.valid = true;
	description.script = Dart_NewPersistentHandle(Dart_ListGetAt(result, 0));
	description.base_type = runtime.to_variant(Dart_ListGetAt(result, 1));
	description.callbacks = runtime.to_variant(Dart_ListGetAt(result, 2));
	description.methods = runtime.to_variant(Dart_ListGetAt(result, 3));
	add_names(description.callbacks);
	add_names(description.methods);
	return description;
}

Dart_Handle DartScript::call(Dart_Handle p_object, const StringName &p_method, Dart_Handle p_arguments) const {
	Dart_Handle argv[] = {
		Dart_HandleFromPersistent(description.script),
		p_object,
		Dart_HandleFromPersistent(description.names[p_method]),
		p_arguments,
	};
	return Runtime::get().invoke("callScript", 4, argv);
}

Error DartScript::_reload(bool p_keep_state) {
	// The compiled class comes from the snapshot, which changes only with a new build.
	return OK;
}

bool DartScript::_can_instantiate() const {
	return describe().valid && !Engine::get_singleton()->is_editor_hint();
}

StringName DartScript::_get_instance_base_type() const {
	return describe().base_type;
}

bool DartScript::_has_method(const StringName &p_method) const {
	return describe().names.has(p_method);
}

Dictionary DartScript::_get_method_info(const StringName &p_method) const {
	Dictionary info;
	if (_has_method(p_method)) {
		info["name"] = p_method;
	}
	return info;
}

TypedArray<Dictionary> DartScript::_get_script_method_list() const {
	TypedArray<Dictionary> list;
	const Description &info = describe();
	for (const PackedStringArray &names : { info.callbacks, info.methods }) {
		for (const String &name : names) {
			Dictionary method;
			method["name"] = name;
			list.push_back(method);
		}
	}
	return list;
}

bool DartScript::_is_valid() const {
	return describe().valid;
}

ScriptLanguage *DartScript::_get_language() const {
	return DartLanguage::get_singleton();
}

void *DartScript::_instance_create(Object *p_for_object) const {
	if (!describe().valid) {
		return nullptr;
	}
	Runtime &runtime = Runtime::get();
	Scope scope;
	Dart_Handle argv[] = {
		Dart_HandleFromPersistent(description.script),
		Dart_NewInteger(static_cast<int64_t>(p_for_object->get_instance_id())),
	};
	Dart_Handle object = runtime.invoke_objects("_createScript", 2, argv);
	if (Runtime::report(object, "creating a script instance")) {
		return nullptr;
	}
	Instance *instance = new Instance();
	instance->owner = p_for_object;
	instance->script = Ref<DartScript>(const_cast<DartScript *>(this));
	instance->object = Dart_NewPersistentHandle(object);
	return create_script_instance(instance);
}

void *DartScript::_placeholder_instance_create(Object *p_for_object) const {
	return gdextension_interface::placeholder_script_instance_create(
			DartLanguage::get_singleton()->_owner, _owner, p_for_object->_owner);
}

void DartScript::_placeholder_erased(void *p_placeholder) {}

bool DartScript::_instance_has(Object *p_object) const {
	const Instance *instance = find_instance(p_object);
	return instance != nullptr && instance->script.ptr() == this;
}

} // namespace dart_godot
