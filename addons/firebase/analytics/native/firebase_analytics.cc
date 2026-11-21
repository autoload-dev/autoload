#include "firebase/analytics/native/firebase_analytics.h"

#include "firebase/analytics/native/backend.h"
#include <godot_cpp/core/class_db.hpp>

using namespace godot;

void FirebaseAnalytics::_bind_methods() {
  ClassDB::bind_static_method("FirebaseAnalytics",
                              D_METHOD("log_event", "name", "parameters"),
                              &FirebaseAnalytics::log_event, DEFVAL(Dictionary()));
  ClassDB::bind_static_method("FirebaseAnalytics", D_METHOD("set_user_id", "user_id"),
                              &FirebaseAnalytics::set_user_id);
  ClassDB::bind_static_method("FirebaseAnalytics",
                              D_METHOD("set_user_property", "name", "value"),
                              &FirebaseAnalytics::set_user_property);
  ClassDB::bind_static_method("FirebaseAnalytics", D_METHOD("set_collection_enabled", "enabled"),
                              &FirebaseAnalytics::set_collection_enabled);
  ClassDB::bind_static_method("FirebaseAnalytics", D_METHOD("is_supported"),
                              &FirebaseAnalytics::is_supported);
}

void FirebaseAnalytics::log_event(const String &name, const Dictionary &parameters) {
  firebase_analytics::backend_log_event(name, parameters);
}
void FirebaseAnalytics::set_user_id(const String &user_id) {
  firebase_analytics::backend_set_user_id(user_id);
}
void FirebaseAnalytics::set_user_property(const String &name, const String &value) {
  firebase_analytics::backend_set_user_property(name, value);
}
void FirebaseAnalytics::set_collection_enabled(bool enabled) {
  firebase_analytics::backend_set_collection_enabled(enabled);
}
bool FirebaseAnalytics::is_supported() { return firebase_analytics::backend_is_supported(); }
