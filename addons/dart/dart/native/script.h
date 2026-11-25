// A Dart script resource: a .dart file of the project, whose class the scripts' snapshot
// holds. The source text is for the editor; the compiled class runs.

#pragma once

#include <godot_cpp/classes/script_extension.hpp>
#include <godot_cpp/classes/script_language.hpp>
#include <godot_cpp/templates/hash_map.hpp>
#include <godot_cpp/variant/packed_string_array.hpp>

#include "include/dart_api.h"

namespace dart_godot {

class DartScript : public godot::ScriptExtension {
	GDCLASS(DartScript, godot::ScriptExtension)

public:
	~DartScript() override;

	// The resource path the snapshot registered the script's class under.
	void set_script_path(const godot::String &p_path) { script_path = p_path; }
	const godot::String &get_script_path() const { return script_path; }

	bool _editor_can_reload_from_file() override { return true; }
	void _placeholder_erased(void *p_placeholder) override;
	bool _can_instantiate() const override;
	godot::Ref<godot::Script> _get_base_script() const override { return {}; }
	godot::StringName _get_global_name() const override { return {}; }
	bool _inherits_script(const godot::Ref<godot::Script> &p_script) const override { return false; }
	godot::StringName _get_instance_base_type() const override;
	void *_instance_create(godot::Object *p_for_object) const override;
	void *_placeholder_instance_create(godot::Object *p_for_object) const override;
	bool _instance_has(godot::Object *p_object) const override;
	bool _has_source_code() const override { return true; }
	godot::String _get_source_code() const override { return source_code; }
	void _set_source_code(const godot::String &p_code) override { source_code = p_code; }
	godot::Error _reload(bool p_keep_state) override;
	godot::StringName _get_doc_class_name() const override { return {}; }
	godot::TypedArray<godot::Dictionary> _get_documentation() const override { return {}; }
	bool _has_method(const godot::StringName &p_method) const override;
	bool _has_static_method(const godot::StringName &p_method) const override { return false; }
	godot::Dictionary _get_method_info(const godot::StringName &p_method) const override;
	bool _is_tool() const override { return false; }
	bool _is_valid() const override;
	godot::ScriptLanguage *_get_language() const override;
	bool _has_script_signal(const godot::StringName &p_signal) const override { return false; }
	godot::TypedArray<godot::Dictionary> _get_script_signal_list() const override { return {}; }
	bool _has_property_default_value(const godot::StringName &p_property) const override { return false; }
	godot::Variant _get_property_default_value(const godot::StringName &p_property) const override { return {}; }
	void _update_exports() override {}
	godot::TypedArray<godot::Dictionary> _get_script_method_list() const override;
	godot::TypedArray<godot::Dictionary> _get_script_property_list() const override { return {}; }
	int32_t _get_member_line(const godot::StringName &p_member) const override { return -1; }
	godot::Dictionary _get_constants() const override { return {}; }
	godot::TypedArray<godot::StringName> _get_members() const override { return {}; }
	bool _is_placeholder_fallback_enabled() const override { return false; }
	godot::Variant _get_rpc_config() const override { return godot::Dictionary(); }

	// Calls the callback or method p_method of p_object, the Dart object of an instance of
	// this script. Requires a Scope.
	Dart_Handle call(Dart_Handle p_object, const godot::StringName &p_method, Dart_Handle p_arguments) const;

protected:
	static void _bind_methods() {}

private:
	// What the snapshot says about the script's class, read on first use: its package:godot
	// Script object, its Godot base class, and its callbacks and methods with their Dart
	// names.
	struct Description {
		bool valid = false;
		Dart_PersistentHandle script = nullptr;
		godot::StringName base_type;
		godot::PackedStringArray callbacks;
		godot::PackedStringArray methods;
		godot::HashMap<godot::StringName, Dart_PersistentHandle> names;
	};
	const Description &describe() const;
	void add_names(const godot::PackedStringArray &p_names) const;

	godot::String source_code;
	godot::String script_path;
	mutable bool described = false;
	mutable Description description;
};

} // namespace dart_godot
