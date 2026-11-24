#pragma once

#include <cstdint>
#include <string>

namespace platform_paths {
enum Category { TEMPORARY = 0, APPLICATION_SUPPORT, APPLICATION_CACHE, DOCUMENTS, DOWNLOADS };
enum class Status { OK = 0, UNAVAILABLE = 1, INTEGRATION_UNAVAILABLE = 2, ERROR = 3 };
enum class Scope { NONE = 0, APPLICATION = 1, USER_DOMAIN = 2, TEMPORARY = 3 };

// Each value owns its strings; no platform handles or Godot objects cross this boundary.
struct BackendResult {
  Status status = Status::ERROR;
  std::string path;
  std::string message = "No lookup has been performed";
  Scope scope = Scope::NONE;
};

inline BackendResult failure(Status status, const std::string &message) {
  return {status, {}, message, Scope::NONE};
}
inline BackendResult success(const std::string &path, Scope scope) {
  return {Status::OK, path, {}, scope};
}
BackendResult resolve(int64_t category, const std::string &application_id);
bool requires_identity(int64_t category);
} // namespace platform_paths
