#include <godot_cpp/classes/node.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/godot.hpp>

class BazelNode : public godot::Node {
  GDCLASS(BazelNode, godot::Node)
protected:
  static void _bind_methods() {}
};

static void initialize(godot::ModuleInitializationLevel level) {
  if (level == godot::MODULE_INITIALIZATION_LEVEL_SCENE) {
    godot::ClassDB::register_class<BazelNode>();
  }
}
static void uninitialize(godot::ModuleInitializationLevel) {}

extern "C" GDExtensionBool GDE_EXPORT example_library_init(
    GDExtensionInterfaceGetProcAddress get_proc_address,
    GDExtensionClassLibraryPtr library,
    GDExtensionInitialization *initialization) {
  godot::GDExtensionBinding::InitObject init(get_proc_address, library, initialization);
  init.register_initializer(initialize);
  init.register_terminator(uninitialize);
  init.set_minimum_library_initialization_level(godot::MODULE_INITIALIZATION_LEVEL_SCENE);
  return init.init();
}
