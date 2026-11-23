#include "app_auth.h"
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/godot.hpp>

using namespace godot;

static void initialize(ModuleInitializationLevel level) {
  if (level == MODULE_INITIALIZATION_LEVEL_SCENE) {
    ClassDB::register_class<AppAuthResult>();
    ClassDB::register_class<AppAuthLogin>();
    ClassDB::register_class<AppAuth>();
  }
}
static void uninitialize(ModuleInitializationLevel level) {
  if (level == MODULE_INITIALIZATION_LEVEL_SCENE) AppAuth::clear_pending_login();
}

extern "C" GDExtensionBool GDE_EXPORT app_auth_addon_init(
    GDExtensionInterfaceGetProcAddress get_proc_address,
    GDExtensionClassLibraryPtr library, GDExtensionInitialization *initialization) {
  GDExtensionBinding::InitObject init(get_proc_address, library, initialization);
  init.register_initializer(initialize);
  init.register_terminator(uninitialize);
  init.set_minimum_library_initialization_level(MODULE_INITIALIZATION_LEVEL_SCENE);
  return init.init();
}
