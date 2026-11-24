#include <godot_cpp/classes/node.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/godot.hpp>

class NativeCounter : public godot::Node {
  GDCLASS(NativeCounter, godot::Node)

  int64_t value = 0;

protected:
  static void _bind_methods() {
    godot::ClassDB::bind_method(godot::D_METHOD("increment", "amount"),
                                &NativeCounter::increment);
    godot::ClassDB::bind_method(godot::D_METHOD("get_value"), &NativeCounter::get_value);
    godot::ClassDB::bind_method(godot::D_METHOD("reset"), &NativeCounter::reset);
  }

public:
  void increment(int64_t amount) { value += amount; }
  int64_t get_value() const { return value; }
  void reset() { value = 0; }
};

static void initialize(godot::ModuleInitializationLevel level) {
  if (level == godot::MODULE_INITIALIZATION_LEVEL_SCENE) {
    godot::ClassDB::register_class<NativeCounter>();
  }
}

static void uninitialize(godot::ModuleInitializationLevel) {}

extern "C" GDExtensionBool GDE_EXPORT native_counter_init(
    GDExtensionInterfaceGetProcAddress get_proc_address,
    GDExtensionClassLibraryPtr library,
    GDExtensionInitialization *initialization) {
  godot::GDExtensionBinding::InitObject init(get_proc_address, library, initialization);
  init.register_initializer(initialize);
  init.register_terminator(uninitialize);
  init.set_minimum_library_initialization_level(godot::MODULE_INITIALIZATION_LEVEL_SCENE);
  return init.init();
}
