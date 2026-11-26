# Generated Godot engine hub. rules_godot registers its components through the extension's
# toolchains repository; @{NAME}//toolchains:all registers them alone.

# The registrations of the hub's components, which the slots that serve tuned runtimes
# grant visibility to: they are no entrypoints.
package_group(
    name = "registration",
    packages = [
        "//toolchains",
{TOOLCHAINS_REPOSITORY}    ],
)
{PIN}