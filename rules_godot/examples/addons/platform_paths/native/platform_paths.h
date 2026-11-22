#pragma once

#include "platform_path_result.h"

class PlatformPaths : public godot::RefCounted {
  GDCLASS(PlatformPaths, godot::RefCounted)

protected:
  static void _bind_methods();

public:
  enum Category { TEMPORARY = 0, APPLICATION_SUPPORT, APPLICATION_CACHE, DOCUMENTS, DOWNLOADS };
  godot::Ref<PlatformPathResult> resolve(int64_t category) const;
};

VARIANT_ENUM_CAST(PlatformPaths::Category)
