#include "app_auth.h"
#include "backend.h"
#include "validation.h"
#include <godot_cpp/classes/engine.hpp>
#include <godot_cpp/classes/os.hpp>
#include <godot_cpp/core/class_db.hpp>

using namespace godot;

namespace {
const char *const kRedirectPath = ":/oauth2redirect";

std::string utf8(const String &text) { return text.utf8().get_data(); }

// The login a backend holds pending, or none: at most one per process. Heap-allocated so
// no static destructor touches Godot objects after the engine shut down.
Ref<AppAuthLogin> &pending_login() {
  static Ref<AppAuthLogin> *login = new Ref<AppAuthLogin>();
  return *login;
}
} // namespace

void AppAuth::_bind_methods() {
  ClassDB::bind_static_method("AppAuth",
                              D_METHOD("login", "issuer", "client_id", "scopes", "redirect_uri"),
                              &AppAuth::login, DEFVAL(String()));
  ClassDB::bind_static_method("AppAuth", D_METHOD("default_redirect_uri"),
                              &AppAuth::default_redirect_uri);
  ClassDB::bind_static_method("AppAuth", D_METHOD("is_supported"), &AppAuth::is_supported);
}

Ref<AppAuthLogin> AppAuth::login(const String &issuer, const String &client_id,
                                 const PackedStringArray &scopes, const String &redirect_uri) {
  using app_auth::Status;
  Ref<AppAuthLogin> login;
  login.instantiate();
  app_auth::BackendRequest request;
  request.issuer = utf8(issuer);
  request.client_id = utf8(client_id);
  for (int i = 0; i < scopes.size(); ++i) request.scopes.push_back(utf8(scopes[i]));
  request.redirect_uri = utf8(redirect_uri);
  if (auto error = app_auth::validate_configuration(request.issuer, request.client_id,
                                                    request.scopes, request.redirect_uri)) {
    login->finish(AppAuthResult::failure(Status::INVALID_CONFIGURATION, *error));
    return login;
  }
  if (pending_login().is_valid()) {
    login->finish(AppAuthResult::failure(Status::BUSY, "Another login is pending"));
    return login;
  }
  if (!app_auth::app_auth_backend_is_supported()) {
    // The editor loads the unsupported backend on every operating system.
    const std::string where = Engine::get_singleton()->is_editor_hint()
                                  ? std::string("in the editor")
                                  : "on " + utf8(OS::get_singleton()->get_name());
    login->finish(AppAuthResult::failure(Status::UNSUPPORTED, "Login is not supported " + where));
    return login;
  }
  if (request.redirect_uri.empty()) {
    const std::string scheme = app_auth::app_auth_backend_default_scheme();
    if (auto error = app_auth::validate_redirect_scheme(
            scheme, app_auth::app_auth_backend_default_scheme_source())) {
      login->finish(AppAuthResult::failure(Status::INVALID_CONFIGURATION, *error));
      return login;
    }
    request.redirect_uri = scheme + kRedirectPath;
  }
  static int64_t next_request_id = 0;
  request.request_id = ++next_request_id;
  login->set_request(request);
  pending_login() = login;
  if (!app_auth::app_auth_backend_start(request)) {
    pending_login().unref();
    login->finish(AppAuthResult::failure(Status::ERROR, "The login could not be started"));
  }
  return login;
}

String AppAuth::default_redirect_uri() {
  const std::string scheme = app_auth::app_auth_backend_default_scheme();
  return scheme.empty() ? String() : app_auth::to_godot(scheme + kRedirectPath);
}

bool AppAuth::is_supported() { return app_auth::app_auth_backend_is_supported(); }

void AppAuth::clear_pending_login() { pending_login().unref(); }

namespace app_auth {
void app_auth_report(int64_t request_id, BackendResult result) {
  Ref<AppAuthLogin> login = pending_login();
  if (login.is_null() || login->get_request_id() != request_id) return; // Unknown or repeated.
  pending_login().unref();
  login->finish(AppAuthResult::from_backend(std::move(result), login->get_requested_scopes()));
}
} // namespace app_auth
