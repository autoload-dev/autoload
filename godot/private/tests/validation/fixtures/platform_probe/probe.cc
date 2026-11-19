// An extension class for scripts to use, whether or not the platform has its library.
#include <godot_cpp/classes/node.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/godot.hpp>

class PlatformProbe : public godot::Node {
  GDCLASS(PlatformProbe, godot::Node)

protected:
  static void _bind_methods() {}
};

static void initialize(godot::ModuleInitializationLevel level) {
  if (level == godot::MODULE_INITIALIZATION_LEVEL_SCENE) {
    godot::ClassDB::register_class<PlatformProbe>();
  }
}

static void uninitialize(godot::ModuleInitializationLevel) {}

extern "C" GDExtensionBool GDE_EXPORT platform_probe_init(
    GDExtensionInterfaceGetProcAddress get_proc_address,
    GDExtensionClassLibraryPtr library,
    GDExtensionInitialization *initialization) {
  godot::GDExtensionBinding::InitObject init(get_proc_address, library, initialization);
  init.register_initializer(initialize);
  init.register_terminator(uninitialize);
  init.set_minimum_library_initialization_level(godot::MODULE_INITIALIZATION_LEVEL_SCENE);
  return init.init();
}
