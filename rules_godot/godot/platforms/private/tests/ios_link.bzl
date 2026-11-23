"""Unsigned device-link inputs for the prebuilt beta engine regression only."""

load("@rules_apple//apple:apple_binary.bzl", "apple_binary")
load("//godot/platforms/private:ios.bzl", "ios_application_inputs")

visibility(["//godot/platforms/private/tests/engine_probe/..."])

def ios_unsigned_link(name, pack, runtime):
    """Link the same production inputs without creating a provisioned device archive."""
    inputs = ios_application_inputs(
        name = name + ".inputs",
        pack = pack,
        runtime = runtime,
        minimum_os_version = "15.0",
        shell = dict(
            bundle_id = "org.example.rulesgodot.beta",
            families = ["iphone", "ipad"],
            app_name = "beta_app",
            executable_name = "beta_app",
        ),
        common = {"tags": ["manual"]},
    )
    apple_binary(
        name = name,
        # The shell's Info.plist, which the beta artifact test inspects.
        data = [pack, ":" + inputs.data],
        minimum_os_version = "15.0",
        platform_type = "ios",
        tags = ["manual"],
        deps = inputs.deps,
    )
