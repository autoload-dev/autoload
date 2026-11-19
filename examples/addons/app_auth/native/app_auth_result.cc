#include "app_auth_result.h"
#include "id_token.h"
#include <godot_cpp/classes/json.hpp>
#include <godot_cpp/core/class_db.hpp>

using namespace godot;
using app_auth::to_godot;

void AppAuthResult::_bind_methods() {
  ClassDB::bind_method(D_METHOD("get_status"), &AppAuthResult::get_status);
  ClassDB::bind_method(D_METHOD("get_message"), &AppAuthResult::get_message);
  ClassDB::bind_method(D_METHOD("get_provider_error"), &AppAuthResult::get_provider_error);
  ClassDB::bind_method(D_METHOD("get_access_token"), &AppAuthResult::get_access_token);
  ClassDB::bind_method(D_METHOD("get_id_token"), &AppAuthResult::get_id_token);
  ClassDB::bind_method(D_METHOD("get_claims"), &AppAuthResult::get_claims);
  ClassDB::bind_method(D_METHOD("get_scopes"), &AppAuthResult::get_scopes);
  ClassDB::bind_method(D_METHOD("get_expires_at"), &AppAuthResult::get_expires_at);
  ClassDB::bind_method(D_METHOD("get_has_refresh_token"), &AppAuthResult::get_has_refresh_token);
  ADD_PROPERTY(PropertyInfo(Variant::INT, "status", PROPERTY_HINT_NONE, "",
                            PROPERTY_USAGE_DEFAULT | PROPERTY_USAGE_CLASS_IS_ENUM,
                            "AppAuthResult.Status"),
               "", "get_status");
  ADD_PROPERTY(PropertyInfo(Variant::STRING, "message"), "", "get_message");
  ADD_PROPERTY(PropertyInfo(Variant::STRING, "provider_error"), "", "get_provider_error");
  ADD_PROPERTY(PropertyInfo(Variant::STRING, "access_token"), "", "get_access_token");
  ADD_PROPERTY(PropertyInfo(Variant::STRING, "id_token"), "", "get_id_token");
  ADD_PROPERTY(PropertyInfo(Variant::DICTIONARY, "claims"), "", "get_claims");
  ADD_PROPERTY(PropertyInfo(Variant::PACKED_STRING_ARRAY, "scopes"), "", "get_scopes");
  ADD_PROPERTY(PropertyInfo(Variant::INT, "expires_at"), "", "get_expires_at");
  ADD_PROPERTY(PropertyInfo(Variant::BOOL, "has_refresh_token"), "", "get_has_refresh_token");
  BIND_ENUM_CONSTANT(OK);
  BIND_ENUM_CONSTANT(CANCELLED);
  BIND_ENUM_CONSTANT(INVALID_CONFIGURATION);
  BIND_ENUM_CONSTANT(BUSY);
  BIND_ENUM_CONSTANT(NETWORK_ERROR);
  BIND_ENUM_CONSTANT(PROVIDER_ERROR);
  BIND_ENUM_CONSTANT(UNSUPPORTED);
  BIND_ENUM_CONSTANT(ERROR);
}

Ref<AppAuthResult> AppAuthResult::failure(app_auth::Status status, std::string message) {
  Ref<AppAuthResult> result;
  result.instantiate();
  result->value = app_auth::failure(status, std::move(message));
  return result;
}

Ref<AppAuthResult> AppAuthResult::from_backend(app_auth::BackendResult value,
                                               const std::vector<std::string> &requested_scopes) {
  using app_auth::Status;
  if (value.status != Status::OK) {
    if (value.message.empty()) value.message = "The login failed without a reason";
    Ref<AppAuthResult> result = failure(value.status, std::move(value.message));
    if (value.status == Status::PROVIDER_ERROR) {
      result->value.provider_error = std::move(value.provider_error);
    }
    return result;
  }
  if (value.access_token.empty() || value.id_token.empty()) {
    return failure(Status::ERROR, "The backend reported a login without tokens");
  }
  const std::optional<std::string> payload = app_auth::id_token_payload(value.id_token);
  if (!payload) return failure(Status::ERROR, "The ID token is not a JWT");
  const Variant parsed = JSON::parse_string(to_godot(*payload));
  if (parsed.get_type() != Variant::DICTIONARY) {
    return failure(Status::ERROR, "The ID token payload is not a JSON object");
  }
  Ref<AppAuthResult> result;
  result.instantiate();
  if (value.scopes.empty()) value.scopes = requested_scopes;
  value.message.clear();
  value.provider_error.clear();
  result->value = std::move(value);
  result->claims = parsed;
  return result;
}

PackedStringArray AppAuthResult::get_scopes() const {
  PackedStringArray scopes;
  for (const std::string &scope : value.scopes) scopes.push_back(to_godot(scope));
  return scopes;
}
