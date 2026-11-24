#pragma once

#include "backend.h"
#include <godot_cpp/classes/ref.hpp>
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/packed_string_array.hpp>

namespace app_auth {
// A Godot string from UTF-8 text of a known length.
inline godot::String to_godot(const std::string &text) {
  return godot::String::utf8(text.c_str(), text.size());
}
} // namespace app_auth

class AppAuthResult : public godot::RefCounted {
  GDCLASS(AppAuthResult, godot::RefCounted)

  app_auth::BackendResult value;
  godot::Dictionary claims;

protected:
  static void _bind_methods();

public:
  // The backend's statuses, bound for scripts.
  enum Status {
    OK = static_cast<int>(app_auth::Status::OK),
    CANCELLED = static_cast<int>(app_auth::Status::CANCELLED),
    INVALID_CONFIGURATION = static_cast<int>(app_auth::Status::INVALID_CONFIGURATION),
    BUSY = static_cast<int>(app_auth::Status::BUSY),
    NETWORK_ERROR = static_cast<int>(app_auth::Status::NETWORK_ERROR),
    PROVIDER_ERROR = static_cast<int>(app_auth::Status::PROVIDER_ERROR),
    UNSUPPORTED = static_cast<int>(app_auth::Status::UNSUPPORTED),
    ERROR = static_cast<int>(app_auth::Status::ERROR),
  };

  // A result for a failed login: every token field stays empty.
  static godot::Ref<AppAuthResult> failure(app_auth::Status status, std::string message);
  // A backend's result, with the claims decoded from the ID token; a malformed OK result
  // becomes ERROR, and missing scopes fall back to the requested ones.
  static godot::Ref<AppAuthResult> from_backend(app_auth::BackendResult result,
                                                const std::vector<std::string> &requested_scopes);

  Status get_status() const { return static_cast<Status>(value.status); }
  godot::String get_message() const { return app_auth::to_godot(value.message); }
  godot::String get_provider_error() const { return app_auth::to_godot(value.provider_error); }
  godot::String get_access_token() const { return app_auth::to_godot(value.access_token); }
  godot::String get_id_token() const { return app_auth::to_godot(value.id_token); }
  godot::Dictionary get_claims() const { return claims; }
  godot::PackedStringArray get_scopes() const;
  int64_t get_expires_at() const { return value.expires_at; }
  bool get_has_refresh_token() const { return value.has_refresh_token; }
};

VARIANT_ENUM_CAST(AppAuthResult::Status)
