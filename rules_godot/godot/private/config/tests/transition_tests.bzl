"""Observe actual per-platform-slice contexts and common export artifact convergence."""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/private/config:settings.bzl", "configured_context", "context_attrs")
load("//godot/private/config:transitions.bzl", "content_transition", "platform_slice_transition")
load("//godot/private/tests:toolchains.bzl", "own_toolchains")

visibility("private")

_ExportInfo = provider(doc = "Configured regression observations.", fields = ["file"])
_PlatformSliceInfo = provider(doc = "Configured regression observations.", fields = ["cpu", "file", "runtime"])
_PlatformSlicesInfo = provider(doc = "Configured regression observations.", fields = ["cpus", "files", "runtimes"])
_RUNTIME = Label("//godot:runtime_toolchain_type")

def _export_impl(ctx):
    file = ctx.actions.declare_file(ctx.label.name + ".pck")
    ctx.actions.write(file, "Only a configuration convergence fixture")
    return [_ExportInfo(file = file)]

export_fixture = rule(implementation = _export_impl)

def _platform_slice_impl(ctx):
    # A runtime platform slice resolves its own runtime component, as the runtime bridges do.
    toolchain = ctx.toolchains[_RUNTIME] if _RUNTIME in ctx.toolchains else None
    return [_PlatformSliceInfo(
        cpu = configured_context(ctx).cpu,
        file = ctx.attr.export[0][_ExportInfo].file,
        runtime = Label(toolchain.godot.provenance.component).name if toolchain else None,
    )]

_PLATFORM_SLICE_ATTRS = dict(context_attrs(), export = attr.label(cfg = content_transition))

platform_slice_fixture = rule(implementation = _platform_slice_impl, attrs = _PLATFORM_SLICE_ATTRS)

# Resolving iOS runtime components analyzes their Apple aspects, so only macOS tests use it.
runtime_platform_slice_fixture = rule(
    implementation = _platform_slice_impl,
    attrs = _PLATFORM_SLICE_ATTRS,
    toolchains = [config_common.toolchain_type(_RUNTIME, mandatory = False)],
)

def _platform_slices_impl(ctx):
    platform_slices = [platform_slice[_PlatformSliceInfo] for platform_slice in ctx.attr.platform_slice]
    return [_PlatformSlicesInfo(
        cpus = sorted([platform_slice.cpu for platform_slice in platform_slices]),
        files = [platform_slice.file for platform_slice in platform_slices],
        runtimes = sorted([
            platform_slice.runtime
            for platform_slice in platform_slices
            if platform_slice.runtime
        ]),
    )]

platform_slices_fixture = rule(
    implementation = _platform_slices_impl,
    attrs = {
        "platform_slice": attr.label(cfg = platform_slice_transition),
    },
)

def _platform_slices_share_content_test(name, platform):
    analysis_test(
        name = name,
        target = ":platform_slices",
        impl = _platform_slices_share_content,
        config_settings = {"//command_line_option:platforms": str(Label(platform))},
        attr_values = {"size": "small"},
    )

def _platform_slices_share_content(env, target):
    platform_slices = target[_PlatformSlicesInfo]
    env.expect.that_collection(platform_slices.cpus).contains_exactly(["arm64", "x86_64"]).in_order()
    env.expect.that_int(len({f: True for f in platform_slices.files}), expr = "distinct export files").equals(1)

def _test_android_platform_slices_share_content(name):
    _platform_slices_share_content_test(name, "//godot/private/config/tests:android_distribution")

def _test_simulator_platform_slices_share_content(name):
    _platform_slices_share_content_test(name, "//godot/private/config/tests:simulator_distribution")

# Each platform slice resolves its own runtime component; arm64 device and simulator differ.
def _runtime_platform_slices_test(name, platform, expected):
    analysis_test(
        name = name,
        target = ":runtime_platform_slices",
        impl = _platform_slices_resolve_own_runtime_components,
        attrs = {"expected": attr.string_list()},
        config_settings = {
            "//command_line_option:platforms": str(Label(platform)),
            str(Label("//godot:variant")): "release",
        } | own_toolchains(["//godot/private/config/tests/platform_slice_engines:all"]),
        attr_values = {
            "expected": expected,
            "size": "small",
            "target_compatible_with": ["@platforms//os:macos"],
        },
    )

def _platform_slices_resolve_own_runtime_components(env, target):
    env.expect.that_collection(target[_PlatformSlicesInfo].runtimes).contains_exactly(env.ctx.attr.expected).in_order()

def _test_simulator_platform_slices_resolve_simulator_runtimes(name):
    _runtime_platform_slices_test(name, "//godot/private/config/tests:simulator_distribution", [
        "runtime_ios_arm64_simulator_release",
        "runtime_ios_x86_64_simulator_release",
    ])

def _test_device_platform_slice_resolves_device_runtime(name):
    _runtime_platform_slices_test(name, "//godot/platforms:ios_arm64", ["runtime_ios_arm64_device_release"])

def transition_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_android_platform_slices_share_content,
            _test_simulator_platform_slices_share_content,
            _test_simulator_platform_slices_resolve_simulator_runtimes,
            _test_device_platform_slice_resolves_device_runtime,
        ],
    )
