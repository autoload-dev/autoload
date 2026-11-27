#pragma once

#include "backend.h"
#include <godot_cpp/classes/ref.hpp>
#include <godot_cpp/classes/ref_counted.hpp>

class PlatformPaths;

class PlatformPathResult : public godot::RefCounted {
  GDCLASS(PlatformPathResult, godot::RefCounted)
  friend class PlatformPaths;
  int64_t category = -1;
  platform_paths::BackendResult value;

protected:
  static void _bind_methods();

public:
  enum Status { OK = 0,
                UNAVAILABLE = 1,
                INTEGRATION_UNAVAILABLE = 2,
                ERROR = 3 };
  enum Scope { NONE = 0,
               APPLICATION = 1,
               USER_DOMAIN = 2,
               TEMPORARY = 3 };
  int64_t get_category() const { return category; }
  Status get_status() const { return static_cast<Status>(value.status); }
  godot::String get_path() const { return godot::String::utf8(value.path.c_str()); }
  godot::String get_message() const { return godot::String::utf8(value.message.c_str()); }
  Scope get_scope() const { return static_cast<Scope>(value.scope); }
};

VARIANT_ENUM_CAST(PlatformPathResult::Status)
VARIANT_ENUM_CAST(PlatformPathResult::Scope)
