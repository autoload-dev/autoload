// Registers Dart as a script language, and the loader and saver of .dart files.

#include <godot_cpp/classes/engine.hpp>
#include <godot_cpp/classes/file_access.hpp>
#include <godot_cpp/classes/resource_format_loader.hpp>
#include <godot_cpp/classes/resource_format_saver.hpp>
#include <godot_cpp/classes/resource_loader.hpp>
#include <godot_cpp/classes/resource_saver.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/godot.hpp>

#include "language.h"
#include "runtime.h"
#include "script.h"

using namespace godot;

namespace dart_godot {

class DartScriptLoader : public ResourceFormatLoader {
	GDCLASS(DartScriptLoader, ResourceFormatLoader)

public:
	PackedStringArray _get_recognized_extensions() const override { return PackedStringArray({ "dart" }); }
	bool _handles_type(const StringName &p_type) const override { return p_type == StringName("Script") || p_type == StringName("DartScript"); }
	String _get_resource_type(const String &p_path) const override { return p_path.get_extension() == "dart" ? "DartScript" : ""; }

	Variant _load(const String &p_path, const String &p_original_path, bool p_use_sub_threads, int32_t p_cache_mode) const override {
		Ref<DartScript> script;
		script.instantiate();
		script->_set_source_code(FileAccess::get_file_as_string(p_path));
		script->set_script_path(p_original_path.is_empty() ? p_path : p_original_path);
		return script;
	}

protected:
	static void _bind_methods() {}
};

class DartScriptSaver : public ResourceFormatSaver {
	GDCLASS(DartScriptSaver, ResourceFormatSaver)

public:
	bool _recognize(const Ref<Resource> &p_resource) const override { return Object::cast_to<DartScript>(p_resource.ptr()) != nullptr; }

	PackedStringArray _get_recognized_extensions(const Ref<Resource> &p_resource) const override {
		return _recognize(p_resource) ? PackedStringArray({ "dart" }) : PackedStringArray();
	}

	Error _save(const Ref<Resource> &p_resource, const String &p_path, uint32_t p_flags) override {
		Ref<DartScript> script = p_resource;
		Ref<FileAccess> file = FileAccess::open(p_path, FileAccess::WRITE);
		if (file.is_null()) {
			return FileAccess::get_open_error();
		}
		file->store_string(script->_get_source_code());
		script->set_script_path(p_path);
		return OK;
	}

protected:
	static void _bind_methods() {}
};

namespace {

DartLanguage *language = nullptr;
Ref<DartScriptLoader> loader;
Ref<DartScriptSaver> saver;

void initialize(ModuleInitializationLevel p_level) {
	if (p_level != MODULE_INITIALIZATION_LEVEL_SCENE) {
		return;
	}
	String library_path;
	gdextension_interface::get_library_path(gdextension_interface::library, &library_path);
	Runtime::get().set_library_path(library_path);

	GDREGISTER_CLASS(DartLanguage);
	GDREGISTER_CLASS(DartScript);
	GDREGISTER_CLASS(DartScriptLoader);
	GDREGISTER_CLASS(DartScriptSaver);

	language = memnew(DartLanguage);
	Engine::get_singleton()->register_script_language(language);
	loader.instantiate();
	ResourceLoader::get_singleton()->add_resource_format_loader(loader);
	saver.instantiate();
	ResourceSaver::get_singleton()->add_resource_format_saver(saver);
}

void uninitialize(ModuleInitializationLevel p_level) {
	if (p_level != MODULE_INITIALIZATION_LEVEL_SCENE) {
		return;
	}
	ResourceSaver::get_singleton()->remove_resource_format_saver(saver);
	saver.unref();
	ResourceLoader::get_singleton()->remove_resource_format_loader(loader);
	loader.unref();
	Engine::get_singleton()->unregister_script_language(language);
	memdelete(language);
	language = nullptr;
}

} // namespace

} // namespace dart_godot

extern "C" GDExtensionBool GDE_EXPORT dart_language_init(
		GDExtensionInterfaceGetProcAddress p_get_proc_address,
		GDExtensionClassLibraryPtr p_library, GDExtensionInitialization *r_initialization) {
	GDExtensionBinding::InitObject init(p_get_proc_address, p_library, r_initialization);
	init.register_initializer(dart_godot::initialize);
	init.register_terminator(dart_godot::uninitialize);
	init.set_minimum_library_initialization_level(MODULE_INITIALIZATION_LEVEL_SCENE);
	return init.init();
}
