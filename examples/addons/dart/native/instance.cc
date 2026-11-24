#include "instance.h"

#include <godot_cpp/godot.hpp>
#include <godot_cpp/variant/string_name.hpp>
#include <godot_cpp/variant/variant.hpp>

#include "language.h"
#include "runtime.h"
#include "script.h"

using namespace godot;

namespace dart_godot {

namespace {

Instance *self(GDExtensionScriptInstanceDataPtr p_self) {
	return static_cast<Instance *>(p_self);
}

GDExtensionBool has_method(GDExtensionScriptInstanceDataPtr p_self, GDExtensionConstStringNamePtr p_name) {
	return self(p_self)->script->_has_method(*static_cast<const StringName *>(p_name));
}

void call(GDExtensionScriptInstanceDataPtr p_self, GDExtensionConstStringNamePtr p_method,
		const GDExtensionConstVariantPtr *p_args, GDExtensionInt p_argument_count,
		GDExtensionVariantPtr r_return, GDExtensionCallError *r_error) {
	Instance *instance = self(p_self);
	const StringName &method = *static_cast<const StringName *>(p_method);
	if (!instance->script->_has_method(method)) {
		r_error->error = GDEXTENSION_CALL_ERROR_INVALID_METHOD;
		return;
	}
	r_error->error = GDEXTENSION_CALL_OK;
	Runtime &runtime = Runtime::get();
	if (!runtime.is_running()) {
		return;
	}
	Scope scope;
	Dart_Handle arguments = Dart_NewList(p_argument_count);
	for (GDExtensionInt i = 0; i < p_argument_count; i++) {
		Dart_ListSetAt(arguments, i, runtime.to_dart(*static_cast<const Variant *>(p_args[i])));
	}
	Dart_Handle result = instance->script->call(Dart_HandleFromPersistent(instance->object), method, arguments);
	if (Runtime::report(result, "calling a script method")) {
		return;
	}
	*static_cast<Variant *>(r_return) = runtime.to_variant(result);
}

GDExtensionObjectPtr get_owner(GDExtensionScriptInstanceDataPtr p_self) {
	return self(p_self)->owner->_owner;
}

GDExtensionObjectPtr get_script(GDExtensionScriptInstanceDataPtr p_self) {
	return self(p_self)->script->_owner;
}

GDExtensionBool is_placeholder(GDExtensionScriptInstanceDataPtr) {
	return false;
}

GDExtensionScriptLanguagePtr get_language(GDExtensionScriptInstanceDataPtr) {
	return DartLanguage::get_singleton()->_owner;
}

GDExtensionBool refcount_decremented(GDExtensionScriptInstanceDataPtr) {
	return true;
}

// Godot ended the script instance, because it freed the object or replaced its script:
// the Dart object stops working, so no Dart code keeps a second script object of it.
void free_instance(GDExtensionScriptInstanceDataPtr p_self) {
	Instance *instance = self(p_self);
	Runtime &runtime = Runtime::get();
	if (runtime.is_running()) {
		Scope scope;
		Dart_Handle argv[] = { Dart_HandleFromPersistent(instance->object) };
		Runtime::report(runtime.invoke_objects("_releaseScript", 1, argv), "releasing a script object");
		Dart_DeletePersistentHandle(instance->object);
	}
	delete instance;
}

const GDExtensionScriptInstanceInfo3 &instance_info() {
	static const GDExtensionScriptInstanceInfo3 info = [] {
		GDExtensionScriptInstanceInfo3 value = {};
		value.get_owner_func = &get_owner;
		value.has_method_func = &has_method;
		value.call_func = &call;
		value.refcount_decremented_func = &refcount_decremented;
		value.get_script_func = &get_script;
		value.is_placeholder_func = &is_placeholder;
		value.get_language_func = &get_language;
		value.free_func = &free_instance;
		return value;
	}();
	return info;
}

} // namespace

void *create_script_instance(Instance *p_instance) {
	return gdextension_interface::script_instance_create3(&instance_info(), p_instance);
}

Instance *find_instance(Object *p_object) {
	return static_cast<Instance *>(gdextension_interface::object_get_script_instance(p_object->_owner, DartLanguage::get_singleton()->_owner));
}

} // namespace dart_godot
