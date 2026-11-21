load({ANDROID_BZL}, "godot_android_runtime")
load({RULES_ANDROID_BZL}, "android_library")

package(default_visibility = ["//visibility:public"])
{RUNTIMES}
# The shell library's classes for Android plugins to compile against; never packaged, so an
# application carries only the runtime its variant selects.
android_library(
    name = "plugin_api",
    exports = [":{PLUGIN_API_RUNTIME}"],
    neverlink = True,
)
