// A trivial extension: one class whose method GDScript calls in the browser.
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/godot.hpp>

using namespace godot;

class WebHello : public RefCounted {
  GDCLASS(WebHello, RefCounted)

protected:
  static void _bind_methods() {
    ClassDB::bind_method(D_METHOD("add", "a", "b"), &WebHello::add);
    ClassDB::bind_method(D_METHOD("greet", "name"), &WebHello::greet);
    ClassDB::bind_method(D_METHOD("bump"), &WebHello::bump);
  }

public:
  int64_t add(int64_t a, int64_t b) const { return a + b; }
  // Thread-local state: exercises TLS relocations of a side module in worker threads.
  int64_t bump() const {
    static thread_local int64_t counter = 0;
    return ++counter;
  }
  String greet(const String &name) const {
    return String("Hello from wasm, ") + name + " (sizeof(void*)=" +
           String::num_int64(sizeof(void *)) + ")";
  }
};

static void initialize(ModuleInitializationLevel level) {
  if (level != MODULE_INITIALIZATION_LEVEL_SCENE) {
    return;
  }
  GDREGISTER_CLASS(WebHello);
}

static void uninitialize(ModuleInitializationLevel) {}

extern "C" GDExtensionBool GDE_EXPORT web_hello_init(
    GDExtensionInterfaceGetProcAddress get_proc_address,
    GDExtensionClassLibraryPtr library,
    GDExtensionInitialization *initialization) {
  GDExtensionBinding::InitObject init(get_proc_address, library, initialization);
  init.register_initializer(initialize);
  init.register_terminator(uninitialize);
  init.set_minimum_library_initialization_level(MODULE_INITIALIZATION_LEVEL_SCENE);
  return init.init();
}
