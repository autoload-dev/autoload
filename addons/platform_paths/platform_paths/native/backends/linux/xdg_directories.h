#pragma once
#include "platform_paths/native/backend.h"
namespace platform_paths {
BackendResult xdg_base(const std::string &override_path, const std::string &home, const std::string &suffix);
BackendResult user_directory(const std::string &contents, const std::string &key, const std::string &home);
} // namespace platform_paths
