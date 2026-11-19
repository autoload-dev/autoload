"""
What an export platform declares for itself and each of its platform slices.

Its constraint values and execution properties reach the export platform and every platform
slice, and it rejects constraints of the operating system, CPU and iOS environment it owns.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:unit_test.bzl", "unit_test")
load("//godot/platforms:defs.bzl", "godot_export_platform")
load("//godot/private/config:settings.bzl", "export_platform_declarations")
load(":inheritance_tests.bzl", "PlatformSlicesInfo", "PropertiesInfo")

def _test_constraint_values_reach_every_platform_slice(name):
    godot_export_platform(
        name = name + "_platform",
        constraint_values = [":common_property"],
        cpus = [
            "@platforms//cpu:aarch64",
            "@platforms//cpu:x86_64",
        ],
        operating_system = "android",
    )
    analysis_test(
        name = name,
        targets = {
            "export_platform": ":properties",
            "platform_slices": ":property_platform_slices",
        },
        impl = _constraint_values_reach_every_platform_slice,
        config_settings = {"//command_line_option:platforms": str(native.package_relative_label(name + "_platform"))},
        attr_values = {"size": "small"},
    )

def _constraint_values_reach_every_platform_slice(env, targets):
    env.expect.that_bool(
        targets.export_platform[PropertiesInfo].common,
        expr = "the export platform carries its constraint values",
    ).equals(True)
    values = targets.platform_slices[PlatformSlicesInfo].values
    env.expect.that_collection([value.cpu for value in values]).contains_exactly(["arm64", "x86_64"])
    for value in values:
        env.expect.where(cpu = value.cpu).that_bool(
            value.common,
            expr = "every platform slice carries the export platform's constraint values",
        ).equals(True)

def _package_relative_label(value):
    """Resolve a label as native.package_relative_label does in this package."""
    if value.startswith(":"):
        return Label("//godot/private/config/tests:BUILD.bazel").same_package_label(value[1:])
    return Label(value)

def _declarations(**kwargs):
    errors = []
    declarations = export_platform_declarations(
        package_relative_label = _package_relative_label,
        _fail = errors.append,
        **kwargs
    )
    return declarations, errors

def _test_exec_properties_reach_every_platform_slice(name):
    unit_test(name = name, impl = _exec_properties_reach_every_platform_slice)

def _exec_properties_reach_every_platform_slice(env):
    for operating_system, cpus, environment, names in [
        ("android", ["@platforms//cpu:x86_64", "@platforms//cpu:aarch64"], None, ["mobile.platform_slice_arm64", "mobile.platform_slice_x86_64", "mobile"]),
        ("ios", ["@platforms//cpu:x86_64", "@platforms//cpu:arm64"], "simulator", ["mobile.platform_slice_arm64", "mobile.platform_slice_x86_64", "mobile"]),
        ("linux", ["@platforms//cpu:x86_64"], None, ["mobile"]),
    ]:
        declarations, errors = _declarations(
            name = "mobile",
            operating_system = operating_system,
            cpus = cpus,
            environment = environment,
            exec_properties = {"container-image": "docker://example"},
        )
        env.expect.where(operating_system = operating_system).that_collection(errors).contains_exactly([])
        env.expect.where(operating_system = operating_system).that_collection(
            [declaration["name"] for declaration in declarations],
        ).contains_exactly(names).in_order()
        for declaration in declarations:
            env.expect.where(operating_system = operating_system, platform = declaration["name"]).that_dict(
                declaration["exec_properties"],
            ).contains_exactly({"container-image": "docker://example"})

def _test_owned_constraint_fails(name):
    unit_test(name = name, impl = _owned_constraint_fails)

def _owned_constraint_fails(env):
    for constraint in ["@platforms//os:linux", "@platforms//cpu:aarch64", "@apple_support//constraints:simulator"]:
        declarations, errors = _declarations(
            name = "owned",
            operating_system = "android",
            cpus = ["@platforms//cpu:aarch64"],
            constraint_values = [constraint],
        )
        env.expect.where(constraint = constraint).that_collection(errors).contains_exactly([
            "Operating system, CPU and iOS environment constraints are owned by godot_export_platform",
        ])
        env.expect.where(constraint = constraint).that_collection(declarations).contains_exactly([])

def _test_android_cpus_declare_their_abis(name):
    unit_test(name = name, impl = _android_cpus_declare_their_abis)

def _android_cpus_declare_their_abis(env):
    declarations, errors = _declarations(
        name = "android",
        operating_system = "android",
        cpus = ["@platforms//cpu:aarch64", "@platforms//cpu:armv7"],
    )
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection([declaration["name"] for declaration in declarations]).contains_exactly([
        "android.platform_slice_arm32",
        "android.platform_slice_arm64",
        "android",
    ]).in_order()
    slices = {declaration["name"]: declaration for declaration in declarations}
    for name, constraint in [
        ("android.platform_slice_arm32", "@platforms//cpu:armv7"),
        ("android.platform_slice_arm64", "@platforms//cpu:aarch64"),
    ]:
        env.expect.where(platform_slice = name).that_collection(
            [str(value) for value in slices[name]["constraint_values"]],
        ).contains(str(Label(constraint)))
    env.expect.that_collection(slices["android"]["flags"]).contains(
        "--%s=arm32,arm64" % Label("//godot/private/config:cpus"),
    )

def _test_cpu_outside_the_table_fails(name):
    unit_test(name = name, impl = _cpu_outside_the_table_fails)

def _cpu_outside_the_table_fails(env):
    declarations, errors = _declarations(
        name = "mainframe",
        operating_system = "linux",
        cpus = ["@platforms//cpu:s390x"],
    )
    env.expect.that_collection(declarations).contains_exactly([])
    env.expect.that_collection(errors).has_size(1)
    env.expect.that_str(errors[0]).contains("Unsupported CPU @@platforms//cpu:s390x; godot_export_platform takes @@platforms//cpu:armv7, @@platforms//cpu:aarch64")
    declarations, errors = _declarations(
        name = "duplicate",
        operating_system = "android",
        cpus = ["@platforms//cpu:aarch64", "@platforms//cpu:arm64"],
    )
    env.expect.that_collection(errors).contains_exactly(["CPUs must be nonempty and duplicate-free"])

def export_platform_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_constraint_values_reach_every_platform_slice,
            _test_exec_properties_reach_every_platform_slice,
            _test_owned_constraint_fails,
            _test_android_cpus_declare_their_abis,
            _test_cpu_outside_the_table_fails,
        ],
    )
