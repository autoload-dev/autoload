#include "app_auth_login.h"
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/variant/callable_method_pointer.hpp>

using namespace godot;

void AppAuthLogin::_bind_methods() {
  ClassDB::bind_method(D_METHOD("is_pending"), &AppAuthLogin::is_pending);
  ADD_SIGNAL(MethodInfo("finished", PropertyInfo(Variant::OBJECT, "result", PROPERTY_HINT_NONE, "",
                                                 PROPERTY_USAGE_DEFAULT, "AppAuthResult")));
}

void AppAuthLogin::set_request(const app_auth::BackendRequest &request) {
  request_id = request.request_id;
  requested_scopes = request.scopes;
}

void AppAuthLogin::finish(const Ref<AppAuthResult> &login_result) {
  if (result.is_valid() || login_result.is_null()) return;
  result = login_result;
  // The bound reference keeps the login alive until the deferred emission ran, whether or
  // not the caller holds one.
  callable_mp(this, &AppAuthLogin::emit_finished).bind(Ref<AppAuthLogin>(this)).call_deferred();
}

void AppAuthLogin::emit_finished(const Ref<AppAuthLogin> &) {
  pending = false;
  emit_signal("finished", result);
}
