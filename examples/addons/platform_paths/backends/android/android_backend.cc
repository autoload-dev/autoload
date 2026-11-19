#include "addons/platform_paths/native/backend.h"
#include <godot_cpp/classes/engine.hpp>
#include <godot_cpp/variant/array.hpp>
#include <godot_cpp/variant/packed_string_array.hpp>

using namespace godot;
namespace platform_paths {
bool requires_identity(int64_t) { return false; }
BackendResult resolve(int64_t category, const std::string &) {
  Engine *engine = Engine::get_singleton();
  if (!engine || !engine->has_singleton("PlatformPathsAndroid")) {
    return failure(Status::INTEGRATION_UNAVAILABLE, "PlatformPathsAndroid plugin is unavailable");
  }
  Object *plugin = engine->get_singleton("PlatformPathsAndroid");
  if (!plugin) {
    return failure(Status::INTEGRATION_UNAVAILABLE, "PlatformPathsAndroid resolver is unavailable");
  }
  Variant receiver(plugin), argument(category), response;
  const Variant *arguments[] = {&argument};
  GDExtensionCallError error;
  receiver.callp("resolve", arguments, 1, response, error);
  // Java singleton methods are dispatched dynamically and are not listed by has_method.
  if (error.error == GDEXTENSION_CALL_ERROR_INVALID_METHOD) {
    return failure(Status::INTEGRATION_UNAVAILABLE, "PlatformPathsAndroid resolver is unavailable");
  }
  if (error.error != GDEXTENSION_CALL_OK) return failure(Status::ERROR, "Android plugin call failed");
  Array fields;
  if (response.get_type() == Variant::PACKED_STRING_ARRAY) {
    PackedStringArray strings = response;
    for (int i = 0; i < strings.size(); ++i) fields.append(strings[i]);
  } else if (response.get_type() == Variant::ARRAY) {
    fields = response;
  }
  if (fields.size() != 3) return failure(Status::ERROR, "Malformed Android result length");
  for (int i = 0; i < 3; ++i) {
    if (fields[i].get_type() != Variant::STRING) return failure(Status::ERROR, "Malformed Android result field");
  }
  const String status = fields[0], path = fields[1], message = fields[2];
  if (status == "ok") {
    if (!message.is_empty() || path.is_empty() || !path.is_absolute_path()) return failure(Status::ERROR, "Invalid Android success");
    return success(path.utf8().get_data(), category == TEMPORARY ? Scope::TEMPORARY : Scope::APPLICATION);
  }
  if (!path.is_empty() || message.is_empty()) return failure(Status::ERROR, "Invalid Android failure");
  if (status == "unavailable") return failure(Status::UNAVAILABLE, message.utf8().get_data());
  if (status == "integration_unavailable") return failure(Status::INTEGRATION_UNAVAILABLE, message.utf8().get_data());
  if (status == "error") return failure(Status::ERROR, message.utf8().get_data());
  return failure(Status::ERROR, "Unknown Android result status");
}
} // namespace platform_paths
