#include "platform_paths.h"
#include <godot_cpp/classes/project_settings.hpp>
#include <godot_cpp/core/class_db.hpp>

using namespace godot;

static bool valid_identity(const std::string &id) {
  if (id.empty() || id[0] < 'a' || id[0] > 'z') return false;
  bool start = true;
  for (char c : id) {
    if (start) {
      if (!(c >= 'a' && c <= 'z') && !(c >= '0' && c <= '9')) {
        // Every separated component must contain at least one alphanumeric character.
        return false;
      }
      start = false;
    } else if (c == '.' || c == '-') {
      start = true;
    } else if (!(c >= 'a' && c <= 'z') && !(c >= '0' && c <= '9')) {
      return false;
    }
  }
  return !id.empty() && !start;
}

void PlatformPaths::_bind_methods() {
  ClassDB::bind_method(D_METHOD("resolve", "category"), &PlatformPaths::resolve);
  BIND_ENUM_CONSTANT(TEMPORARY);
  BIND_ENUM_CONSTANT(APPLICATION_SUPPORT);
  BIND_ENUM_CONSTANT(APPLICATION_CACHE);
  BIND_ENUM_CONSTANT(DOCUMENTS);
  BIND_ENUM_CONSTANT(DOWNLOADS);
}

Ref<PlatformPathResult> PlatformPaths::resolve(int64_t category) const {
  using namespace platform_paths;
  Ref<PlatformPathResult> result;
  result.instantiate();
  result->category = category;
  if (category < 0 || category > 4) {
    result->value = failure(Status::ERROR, "Unknown directory category");
    return result;
  }
  std::string id;
  if (requires_identity(category)) {
    Variant setting = ProjectSettings::get_singleton()->get_setting("platform_paths/application_id", "");
    if (setting.get_type() == Variant::STRING) {
      id = String(setting).utf8().get_data();
    }
    if (!valid_identity(id)) {
      result->value = failure(Status::ERROR, "Set platform_paths/application_id to a lowercase application ID");
      return result;
    }
  }
  result->value = platform_paths::resolve(category, id);
  const auto &value = result->value;
  if (value.status == Status::OK &&
      (value.path.empty() || value.path[0] != '/' || value.path.find('\0') != std::string::npos ||
       !value.message.empty() || value.scope == Scope::NONE)) {
    result->value = failure(Status::ERROR, "Native backend returned an invalid path result");
  } else if (value.status != Status::OK &&
             (!value.path.empty() || value.message.empty() || value.scope != Scope::NONE)) {
    result->value = failure(Status::ERROR, "Native backend returned an invalid failure result");
  }
  return result;
}
