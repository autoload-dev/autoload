#pragma once

#include "app_auth_login.h"
#include <godot_cpp/classes/object.hpp>
#include <godot_cpp/variant/packed_string_array.hpp>

// The GDScript-facing login API: static methods, identical on every operating system.
class AppAuth : public godot::Object {
  GDCLASS(AppAuth, godot::Object)

protected:
  static void _bind_methods();

public:
  // Never returns null and never blocks; the result arrives through the login's `finished`.
  static godot::Ref<AppAuthLogin> login(const godot::String &issuer, const godot::String &client_id,
                                        const godot::PackedStringArray &scopes,
                                        const godot::String &redirect_uri);
  // `<scheme>:/oauth2redirect` on operating systems with a backend; empty elsewhere.
  static godot::String default_redirect_uri();
  static bool is_supported();

  // Drops the login a backend holds pending; the extension calls it when it unloads.
  static void clear_pending_login();
};
