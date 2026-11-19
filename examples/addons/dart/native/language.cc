#include "language.h"

#include <godot_cpp/classes/class_db_singleton.hpp>

#include "runtime.h"
#include "script.h"

using namespace godot;

namespace dart_godot {

namespace {

const char *const TEMPLATE = R"(import 'package:godot/godot.dart';

class _CLASS_ extends _BASE_ with Ready {
  _CLASS_(super.handle);

  @override
  void ready() {}
}

final script = Script(_CLASS_.new);
)";

// The class a new script for p_base extends: the nearest of p_base and its ancestors that
// package:godot has a view of, else Node.
String view_class(const String &p_base) {
	Runtime &runtime = Runtime::get();
	if (!runtime.ensure_started()) {
		return "Node";
	}
	Scope scope;
	const PackedStringArray views = runtime.to_variant(runtime.invoke("viewClasses", 0, nullptr));
	ClassDBSingleton *class_db = ClassDBSingleton::get_singleton();
	for (StringName name = p_base; !String(name).is_empty(); name = class_db->get_parent_class(name)) {
		if (views.has(name)) {
			return name;
		}
	}
	return "Node";
}

} // namespace

DartLanguage *DartLanguage::singleton = nullptr;

DartLanguage::DartLanguage() {
	singleton = this;
}

DartLanguage::~DartLanguage() {
	if (singleton == this) {
		singleton = nullptr;
	}
}

void DartLanguage::_finish() {
	Runtime::get().shutdown();
}

PackedStringArray DartLanguage::_get_reserved_words() const {
	return PackedStringArray({
			"abstract", "as", "assert", "async", "await", "base", "break", "case", "catch", "class",
			"const", "continue", "covariant", "default", "deferred", "do", "dynamic", "else", "enum",
			"export", "extends", "extension", "external", "factory", "false", "final", "finally", "for",
			"Function", "get", "hide", "if", "implements", "import", "in", "interface", "is", "late",
			"library", "mixin", "new", "null", "of", "on", "operator", "part", "required", "rethrow",
			"return", "sealed", "set", "show", "static", "super", "switch", "sync", "this", "throw",
			"true", "try", "type", "typedef", "var", "void", "when", "while", "with", "yield",
	});
}

bool DartLanguage::_is_control_flow_keyword(const String &p_keyword) const {
	const PackedStringArray keywords({
			"break", "case", "catch", "continue", "default", "do", "else", "finally", "for", "if",
			"rethrow", "return", "switch", "throw", "try", "while", "yield", "await",
	});
	return keywords.has(p_keyword);
}

PackedStringArray DartLanguage::_get_comment_delimiters() const {
	return PackedStringArray({ "//", "/* */" });
}

PackedStringArray DartLanguage::_get_doc_comment_delimiters() const {
	return PackedStringArray({ "///" });
}

PackedStringArray DartLanguage::_get_string_delimiters() const {
	return PackedStringArray({ "\" \"", "' '", "\"\"\" \"\"\"", "''' '''" });
}

Ref<Script> DartLanguage::_make_template(const String &p_template, const String &p_class_name, const String &p_base_class_name) const {
	const String base = view_class(p_base_class_name);
	const String class_name = p_class_name.is_empty() ? String("Script") : p_class_name.to_pascal_case();
	Ref<DartScript> script;
	script.instantiate();
	script->_set_source_code(String(TEMPLATE).replace("_CLASS_", class_name).replace("_BASE_", base));
	return script;
}

Dictionary DartLanguage::_validate(const String &p_script, const String &p_path, bool p_validate_functions, bool p_validate_errors, bool p_validate_warnings, bool p_validate_safe_lines) const {
	// The build compiles the scripts and reports their errors.
	Dictionary result;
	result["valid"] = true;
	result["errors"] = Array();
	result["warnings"] = Array();
	result["functions"] = PackedStringArray();
	result["safe_lines"] = PackedInt32Array();
	return result;
}

Dictionary DartLanguage::_complete_code(const String &p_code, const String &p_path, Object *p_owner) const {
	Dictionary result;
	result["result"] = ERR_UNAVAILABLE;
	result["force"] = false;
	result["call_hint"] = String();
	return result;
}

Dictionary DartLanguage::_lookup_code(const String &p_code, const String &p_symbol, const String &p_path, Object *p_owner) const {
	Dictionary result;
	result["result"] = ERR_UNAVAILABLE;
	return result;
}

PackedStringArray DartLanguage::_get_recognized_extensions() const {
	return PackedStringArray({ "dart" });
}

} // namespace dart_godot
