// The Android backend: a bridge to the AppAuthAndroid plugin singleton, whose one `finished`
// signal carries every login result.
#include "app_auth/native/backend.h"
#include <godot_cpp/classes/engine.hpp>
#include <godot_cpp/variant/callable_method_pointer.hpp>
#include <godot_cpp/variant/packed_string_array.hpp>
#include <optional>

using namespace godot;

namespace app_auth {
namespace {
const char *const kPlugin = "AppAuthAndroid";
bool connected = false;

Object *plugin() {
  Engine *engine = Engine::get_singleton();
  if (!engine || !engine->has_singleton(kPlugin)) return nullptr;
  return engine->get_singleton(kPlugin);
}

std::string utf8(const String &text) { return text.utf8().get_data(); }
String to_godot(const std::string &text) { return String::utf8(text.c_str(), text.size()); }

// The status names the plugin's `finished` signal carries.
std::optional<Status> status_from_name(const std::string &name) {
  if (name == "ok") return Status::OK;
  if (name == "cancelled") return Status::CANCELLED;
  if (name == "network_error") return Status::NETWORK_ERROR;
  if (name == "provider_error") return Status::PROVIDER_ERROR;
  if (name == "error") return Status::ERROR;
  return std::nullopt;
}

void on_finished(int64_t request_id, const String &status, const String &message,
                 const String &provider_error, const String &access_token, const String &id_token,
                 const String &scopes, int64_t expires_at, bool has_refresh_token) {
  const std::optional<Status> parsed = status_from_name(utf8(status));
  if (!parsed) {
    app_auth_report(request_id, failure(Status::ERROR,
                                        "Unknown Android login status: " + utf8(status)));
    return;
  }
  BackendResult result;
  result.status = *parsed;
  result.message = utf8(message);
  result.provider_error = utf8(provider_error);
  result.access_token = utf8(access_token);
  result.id_token = utf8(id_token);
  const PackedStringArray parts = scopes.split(" ", false);
  for (int i = 0; i < parts.size(); ++i) result.scopes.push_back(utf8(parts[i]));
  result.expires_at = expires_at;
  result.has_refresh_token = has_refresh_token;
  app_auth_report(request_id, std::move(result));
}

bool connect_once(Object *singleton) {
  if (!connected) connected = singleton->connect("finished", callable_mp_static(&on_finished)) == OK;
  return connected;
}
} // namespace

bool app_auth_backend_is_supported() { return plugin() != nullptr; }

std::string app_auth_backend_default_scheme() {
  Object *singleton = plugin();
  if (!singleton) return "";
  // Java singleton methods are dispatched dynamically and are not listed by has_method; a
  // failed call yields a nil Variant.
  const Variant response = singleton->call("redirect_scheme");
  return response.get_type() == Variant::STRING ? utf8(response) : "";
}

std::string app_auth_backend_default_scheme_source() {
  return "the appAuthRedirectScheme manifest value";
}

bool app_auth_backend_start(const BackendRequest &request) {
  Object *singleton = plugin();
  if (!singleton || !connect_once(singleton)) return false;
  String joined;
  for (const std::string &scope : request.scopes) {
    if (!joined.is_empty()) joined += " ";
    joined += to_godot(scope);
  }
  const Variant response =
      singleton->call("start", request.request_id, to_godot(request.issuer),
                      to_godot(request.client_id), joined, to_godot(request.redirect_uri));
  // Godot's JNI bridge returns a Java boolean as its jboolean value, an INT Variant; a failed
  // call yields nil, which booleanizes to false.
  return response.booleanize();
}
} // namespace app_auth
