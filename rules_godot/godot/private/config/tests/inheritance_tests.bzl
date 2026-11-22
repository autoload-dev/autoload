"""A parent platform affects every platform slice; child-only properties stay on the child."""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/private/config:settings.bzl", "configured_context", "context_attrs")
load("//godot/private/config:transitions.bzl", "platform_slice_transition")

PropertiesInfo = provider(doc = "Observed inherited platform properties.", fields = ["common", "child", "operating_system", "cpu"])
PlatformSlicesInfo = provider(doc = "Properties collected across the requested platform slices.", fields = ["values"])

def _properties_impl(ctx):
    return [PropertiesInfo(
        common = ctx.target_platform_has_constraint(ctx.attr._common[platform_common.ConstraintValueInfo]),
        child = ctx.target_platform_has_constraint(ctx.attr._child[platform_common.ConstraintValueInfo]),
        operating_system = configured_context(ctx).operating_system,
        cpu = configured_context(ctx).cpu,
    )]

properties = rule(
    implementation = _properties_impl,
    attrs = context_attrs() | {
        "_common": attr.label(default = Label(":common_property")),
        "_child": attr.label(default = Label(":child_property")),
    },
)

def _platform_slices_impl(ctx):
    return [PlatformSlicesInfo(values = [target[PropertiesInfo] for target in ctx.attr.platform_slices])]

property_platform_slices = rule(
    implementation = _platform_slices_impl,
    attrs = {
        "platform_slices": attr.label(mandatory = True, cfg = platform_slice_transition),
        "_allowlist_function_transition": attr.label(default = "@bazel_tools//tools/allowlists/function_transition_allowlist"),
    },
)

def _test_parent_platform_reaches_every_platform_slice(name):
    analysis_test(
        name = name,
        target = ":property_platform_slices",
        impl = _parent_platform_reaches_every_platform_slice,
        config_settings = {"//command_line_option:platforms": str(Label(":consumer_child"))},
        attr_values = {"size": "small"},
    )

def _parent_platform_reaches_every_platform_slice(env, target):
    values = target[PlatformSlicesInfo].values
    env.expect.that_int(len(values), expr = "platform slices").equals(2)
    for value in values:
        env.expect.that_bool(value.common, expr = "Common-parent constraints must reach every platform slice").equals(True)
        env.expect.that_bool(value.child, expr = "A child platform does not rewrite its export platform's platform slices").equals(False)
        env.expect.that_str(value.operating_system).equals("android")

# A parent's operating system, CPU and export platform flags cannot redirect the
# export platform it is shared by.
def _test_parent_cannot_redirect_export_platform(name):
    analysis_test(
        name = name,
        target = ":property_platform_slices",
        impl = _parent_cannot_redirect_export_platform,
        config_settings = {"//command_line_option:platforms": str(Label(":competing_export_platform"))},
        attr_values = {"size": "small"},
    )

def _parent_cannot_redirect_export_platform(env, target):
    values = target[PlatformSlicesInfo].values
    env.expect.that_collection(
        [(value.operating_system, value.cpu) for value in values],
    ).contains_exactly([("android", "arm64")]).in_order()

def inheritance_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_parent_platform_reaches_every_platform_slice,
            _test_parent_cannot_redirect_export_platform,
        ],
    )
