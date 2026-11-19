#pragma once

#include "app_auth_result.h"
#include "backend.h"
#include <godot_cpp/classes/ref_counted.hpp>
#include <string>
#include <vector>

// One login attempt. `finished` is emitted exactly once, deferred to a later frame, so a
// caller can connect or await after `AppAuth.login` returns.
class AppAuthLogin : public godot::RefCounted {
  GDCLASS(AppAuthLogin, godot::RefCounted)

  int64_t request_id = 0;
  std::vector<std::string> requested_scopes;
  bool pending = true;
  godot::Ref<AppAuthResult> result; // Set once by finish(); emitted on a later frame.

  void emit_finished(const godot::Ref<AppAuthLogin> &self);

protected:
  static void _bind_methods();

public:
  bool is_pending() const { return pending; }

  // The native side, which AppAuth drives; not bound to scripts.
  void set_request(const app_auth::BackendRequest &request);
  int64_t get_request_id() const { return request_id; }
  const std::vector<std::string> &get_requested_scopes() const { return requested_scopes; }
  // Ends the login once: the result reaches `finished` on a later frame; later results
  // are dropped.
  void finish(const godot::Ref<AppAuthResult> &login_result);
};
