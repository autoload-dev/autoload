#pragma once

#include <cstdint>
#include <string>
#include <utility>
#include <vector>

// The boundary between the shared native API and the backend of one operating system.
// Each value owns its strings; no platform handles or Godot objects cross it.
namespace app_auth {
enum class Status {
  OK = 0,
  CANCELLED = 1,
  INVALID_CONFIGURATION = 2,
  BUSY = 3,
  NETWORK_ERROR = 4,
  PROVIDER_ERROR = 5,
  UNSUPPORTED = 6,
  ERROR = 7,
};

struct BackendRequest {
  int64_t request_id = 0;
  std::string issuer;
  std::string client_id;
  std::vector<std::string> scopes;
  std::string redirect_uri;
};

struct BackendResult {
  Status status = Status::ERROR;
  std::string message;
  std::string provider_error;
  std::string access_token;
  std::string id_token;
  std::vector<std::string> scopes;
  int64_t expires_at = 0; // Unix seconds; 0 when the provider sends no expiry.
  bool has_refresh_token = false;
};

inline BackendResult failure(Status status, std::string message) {
  BackendResult result;
  result.status = status;
  result.message = std::move(message);
  return result;
}

// Implemented by the backend of the selected operating system.
bool app_auth_backend_is_supported();
// The scheme of the default redirect URI; empty when the operating system has none.
std::string app_auth_backend_default_scheme();
// Where the default scheme comes from, named in messages: "the bundle identifier" and such.
std::string app_auth_backend_default_scheme_source();
// Starts the login; false when it cannot start, in which case no report follows. Otherwise
// exactly one app_auth_report follows for the request ID.
bool app_auth_backend_start(const BackendRequest &request);

// Implemented by the shared native layer; backends call it on Godot's main thread.
void app_auth_report(int64_t request_id, BackendResult result);
} // namespace app_auth
