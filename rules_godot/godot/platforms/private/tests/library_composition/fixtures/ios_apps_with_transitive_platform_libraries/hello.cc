// A minimal C ABI extension. Production C++ extensions should use godot-cpp.
// These ABI declarations follow Godot 4.7 GDExtension interface.
#include <cstdint>
#include <cstdio>

extern "C" int rules_godot_hello_support();

using GDExtensionBool = uint8_t;
using GDExtensionInterfaceFunctionPtr = void (*)();
using GDExtensionInterfaceGetProcAddress = GDExtensionInterfaceFunctionPtr (*)(const char *);
enum GDExtensionInitializationLevel {
  GDEXTENSION_INITIALIZATION_CORE,
  GDEXTENSION_INITIALIZATION_SERVERS,
  GDEXTENSION_INITIALIZATION_SCENE,
  GDEXTENSION_INITIALIZATION_EDITOR,
};
struct GDExtensionInitialization {
  GDExtensionInitializationLevel minimum_initialization_level;
  void *userdata;
  void (*initialize)(void *, GDExtensionInitializationLevel);
  void (*deinitialize)(void *, GDExtensionInitializationLevel);
};

static void initialize(void *, GDExtensionInitializationLevel level) {
  if (level == GDEXTENSION_INITIALIZATION_SCENE) {
    std::puts("rules_godot extension initialized");
    std::fflush(stdout);
  }
}
static void deinitialize(void *, GDExtensionInitializationLevel) {}

extern "C" __attribute__((visibility("default"))) GDExtensionBool
rules_godot_library_init(GDExtensionInterfaceGetProcAddress, void *,
                         GDExtensionInitialization *initialization) {
  if (rules_godot_hello_support() != 42) {
    return 0;
  }
  initialization->minimum_initialization_level = GDEXTENSION_INITIALIZATION_SCENE;
  initialization->userdata = nullptr;
  initialization->initialize = initialize;
  initialization->deinitialize = deinitialize;
  return 1;
}
