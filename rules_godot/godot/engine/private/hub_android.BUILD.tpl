load({ANDROID_BZL}, "godot_android_runtime")

# The runtimes wrap Godot's shells, among them prebuilt downloads without metadata of their own.
package(
    default_package_metadata = [{PACKAGE_METADATA}],
    default_visibility = ["//visibility:public"],
)
{RUNTIMES}
