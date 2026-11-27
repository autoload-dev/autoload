#include "platform_path_result.h"
#include <godot_cpp/core/class_db.hpp>
using namespace godot;
void PlatformPathResult::_bind_methods() {
  ClassDB::bind_method(D_METHOD("get_category"), &PlatformPathResult::get_category);
  ClassDB::bind_method(D_METHOD("get_status"), &PlatformPathResult::get_status);
  ClassDB::bind_method(D_METHOD("get_path"), &PlatformPathResult::get_path);
  ClassDB::bind_method(D_METHOD("get_message"), &PlatformPathResult::get_message);
  ClassDB::bind_method(D_METHOD("get_scope"), &PlatformPathResult::get_scope);
  ADD_PROPERTY(PropertyInfo(Variant::INT, "category"), "", "get_category");
  ADD_PROPERTY(PropertyInfo(Variant::INT, "status", PROPERTY_HINT_NONE, "", PROPERTY_USAGE_DEFAULT | PROPERTY_USAGE_CLASS_IS_ENUM, "PlatformPathResult.Status"), "", "get_status");
  ADD_PROPERTY(PropertyInfo(Variant::STRING, "path"), "", "get_path");
  ADD_PROPERTY(PropertyInfo(Variant::STRING, "message"), "", "get_message");
  ADD_PROPERTY(PropertyInfo(Variant::INT, "scope", PROPERTY_HINT_NONE, "", PROPERTY_USAGE_DEFAULT | PROPERTY_USAGE_CLASS_IS_ENUM, "PlatformPathResult.Scope"), "", "get_scope");
  BIND_ENUM_CONSTANT(OK);
  BIND_ENUM_CONSTANT(UNAVAILABLE);
  BIND_ENUM_CONSTANT(INTEGRATION_UNAVAILABLE);
  BIND_ENUM_CONSTANT(ERROR);
  BIND_ENUM_CONSTANT(NONE);
  BIND_ENUM_CONSTANT(APPLICATION);
  BIND_ENUM_CONSTANT(USER_DOMAIN);
  BIND_ENUM_CONSTANT(TEMPORARY);
}
