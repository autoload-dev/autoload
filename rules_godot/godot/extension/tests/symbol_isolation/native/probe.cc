// One godot-cpp extension of the symbol isolation test, built once per PROBE_VALUE class
// and PROBE_ENTRY entry symbol: a class whose read() takes a Ref of its own class back
// into native code.
#include <godot_cpp/classes/ref.hpp>
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/godot.hpp>

// Expands PROBE_VALUE before GDCLASS turns the class name into a string.
#define PROBE_GDCLASS(name) GDCLASS(name, godot::RefCounted)

class PROBE_VALUE : public godot::RefCounted {
  PROBE_GDCLASS(PROBE_VALUE)

  int64_t value = 0;

protected:
  static void _bind_methods() {
    godot::ClassDB::bind_method(godot::D_METHOD("set_value", "value"), &PROBE_VALUE::set_value);
    godot::ClassDB::bind_method(godot::D_METHOD("read", "other"), &PROBE_VALUE::read);
  }

public:
  void set_value(int64_t new_value) { value = new_value; }

  // -1 when the Ref does not resolve to an object of this class.
  int64_t read(const godot::Ref<PROBE_VALUE> &other) const {
    return other.is_valid() ? other->value : -1;
  }
};

static void initialize(godot::ModuleInitializationLevel level) {
  if (level == godot::MODULE_INITIALIZATION_LEVEL_SCENE) {
    godot::ClassDB::register_class<PROBE_VALUE>();
  }
}

static void uninitialize(godot::ModuleInitializationLevel) {}

extern "C" GDExtensionBool GDE_EXPORT PROBE_ENTRY(
    GDExtensionInterfaceGetProcAddress get_proc_address,
    GDExtensionClassLibraryPtr library,
    GDExtensionInitialization *initialization) {
  godot::GDExtensionBinding::InitObject init(get_proc_address, library, initialization);
  init.register_initializer(initialize);
  init.register_terminator(uninitialize);
  init.set_minimum_library_initialization_level(godot::MODULE_INITIALIZATION_LEVEL_SCENE);
  return init.init();
}
