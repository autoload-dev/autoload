"""
Declare an operating system and consumer-selected CPU set as one export platform.

Example: `godot_export_platform(name = "android", operating_system = "android",
cpus = ["@platforms//cpu:armv7", "@platforms//cpu:aarch64"])`.

Select the resulting label with --platforms. C++ compiler, debug symbol, signing and
variant settings stay independent of it. See the platform guide for engine and SDK setup.
"""

load("//godot/private/config:settings.bzl", "export_platform_declarations")

def godot_export_platform(
        name,
        operating_system,
        cpus,
        environment = None,
        parents = [],
        constraint_values = [],
        exec_properties = {},
        visibility = None):
    """
    Create an export platform and, for mobile, its private platform slices.

    A child platform, `platform(parents = [":android_arm64"])` for an export platform
    named `android_arm64`, keeps the export platform's operating system, CPUs
    and platform slices. The child's own constraints, flags and execution properties
    apply only to application packaging and a desktop runtime: content export, the
    project's extension libraries and mobile platform slices build for this export
    platform or its platform slices, and a desktop export platform is its own platform
    slice. Put properties those actions need on `parents`, `constraint_values` or
    `exec_properties` here. A child that sets another operating system, CPU or iOS
    environment fails analysis.

    ### Default outputs
    - metadata (none): select operating system and CPUs; no run behavior

    Args:
        name: Public export platform target name, selected through --platforms.
        operating_system: Operating system: linux, macos, android or ios.
        cpus: Nonempty unique list of `@platforms//cpu` constraint values Godot can
            express: `armv7`, `aarch64` (or its alias `arm64`), `x86_32`, `x86_64` and
            `riscv64`. Desktops take one CPU, an iOS device `aarch64` and the iOS
            Simulator `aarch64` or `x86_64`. Whether a CPU builds is decided by the
            registered runtime components: an application for a CPU without one
            fails analysis.
        environment: iOS device (default) or simulator; omit for other operating systems.
        parents: At most one parent platform for custom properties every platform slice
            shares.
            The export platform's operating system, CPU, environment and mobile
            CPU flags replace its own.
        constraint_values: Additional constraints shared by the export platform and its platform slices.
            Operating system, CPU and iOS environment constraints are owned by
            this macro.
        exec_properties: Execution properties shared by the export platform and every
            platform slice.
        visibility: Visibility of the public export platform; generated platform slices
            remain private.
    """
    for declaration in export_platform_declarations(
        name,
        operating_system,
        cpus,
        package_relative_label = native.package_relative_label,
        environment = environment,
        parents = parents,
        constraint_values = constraint_values,
        exec_properties = exec_properties,
        visibility = visibility,
    ):
        native.platform(**declaration)
