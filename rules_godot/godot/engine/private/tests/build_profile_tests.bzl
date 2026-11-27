"""
An application's build profile reaches the class generator of a source-built runtime only.

godot_app's build_profile sets //godot/private:build_profile at the runtime's edge. The class
generator of a source recipe reads it as an action input; the engine's objects that read no
profile reset it, so applications with different profiles share them; a prebuilt runtime,
which has no class generator, refuses it.
"""

load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:truth.bzl", "matching")
load("//godot/engine/private:optimization.bzl", "tuned_engine_settings")
load("//godot/private:providers.bzl", "GodotComponentInfo")
load("//godot/private/tests:toolchains.bzl", "own_toolchains")

visibility("private")

_BUILD_PROFILE = str(Label("//godot/private:build_profile"))
_NO_BUILD_PROFILE = Label("//godot/private:no_build_profile")
_PROFILE = Label("//godot/engine/private/tests:profile.gdbuild")
_BUILD_PROFILE_LABEL = str(Label("//godot/private:build_profile_label"))

# The label string of the fixtures' build profile, as a runtime profile registers it.
PROFILE = str(_PROFILE)
_TESTS = "//godot/engine/private/tests:"
_FIXTURES = "//godot/engine/private/tests/fixtures"

def _profile_files_impl(ctx):
    return [CcInfo(), DefaultInfo(files = depset(ctx.files._build_profile))]

# An object stand-in that names the build profile of its configuration.
profile_reader = rule(
    doc = "Report the build profile of the configuration as DefaultInfo files.",
    implementation = _profile_files_impl,
    attrs = {"_build_profile": attr.label(default = Label("//godot/private:build_profile"), allow_files = True)},
)

def _settings(build_profile = _NO_BUILD_PROFILE):
    return {
        str(Label("//godot:engine")): "",
        str(Label("//godot:engine_optimize")): "auto",
        str(Label("//godot:engine_lto")): "none",
        str(Label("//godot:engine_vfe")): False,
        _BUILD_PROFILE: build_profile,
    }

def _attr(build_profile = None):
    return struct(engine = "", engine_optimize = "", engine_lto = "", engine_vfe = "", build_profile = build_profile)

# The runtime's edge selects the application's profile; without one it keeps the build's.
def _test_the_runtime_edge_sets_the_build_profile(env):
    values = tuned_engine_settings(_settings(), _attr(_PROFILE))
    env.expect.that_str(str(values[_BUILD_PROFILE])).equals(str(_PROFILE))
    env.expect.that_str(values[_BUILD_PROFILE_LABEL]).equals(str(_PROFILE))
    kept = tuned_engine_settings(_settings(_PROFILE), _attr())
    env.expect.that_str(str(kept[_BUILD_PROFILE])).equals(str(_PROFILE))
    none = tuned_engine_settings(_settings(), _attr())
    env.expect.that_str(none[_BUILD_PROFILE_LABEL]).equals("")

def _class_generator_arguments(target):
    action = [action for action in target.actions if action.mnemonic == "GodotGenerate"][0]
    return action.argv

def _test_the_class_generator_reads_the_profile(name):
    analysis_test(
        name = name,
        target = _TESTS + "class_generator",
        impl = _test_the_class_generator_reads_the_profile_impl,
        config_settings = {_BUILD_PROFILE: str(_PROFILE)},
    )

def _test_the_class_generator_reads_the_profile_impl(env, target):
    arguments = _class_generator_arguments(target)
    env.expect.that_collection(arguments).contains("--class-profile")
    env.expect.that_str(arguments[arguments.index("--class-profile") + 1]).contains("profile.gdbuild")

def _test_without_a_profile_the_class_generator_reads_none(name):
    analysis_test(
        name = name,
        target = _TESTS + "class_generator",
        impl = _test_without_a_profile_the_class_generator_reads_none_impl,
    )

def _test_without_a_profile_the_class_generator_reads_none_impl(env, target):
    env.expect.that_collection(_class_generator_arguments(target)).not_contains("--class-profile")

# Objects that read no profile resolve without the application's, so every profile shares them.
def _test_profile_independent_objects_reset_the_profile(name):
    analysis_test(
        name = name,
        target = _TESTS + "profile_independent",
        impl = _test_profile_independent_objects_reset_the_profile_impl,
        config_settings = {_BUILD_PROFILE: str(_PROFILE)},
    )

def _test_profile_independent_objects_reset_the_profile_impl(env, target):
    env.expect.that_target(target).default_outputs().contains_exactly([])

def _test_a_prebuilt_runtime_refuses_a_build_profile(name):
    analysis_test(
        name = name,
        target = _TESTS + "profiled_runtime",
        impl = _test_a_prebuilt_runtime_refuses_a_build_profile_impl,
        expect_failure = True,
        config_settings = {
            "//command_line_option:platforms": str(Label(_TESTS + "linux_x86_64")),
        } | own_toolchains([_FIXTURES + ":all"]),
    )

def _test_a_prebuilt_runtime_refuses_a_build_profile_impl(env, target):
    env.expect.that_target(target).failures().contains_predicate(matching.contains("build_profile"))
    env.expect.that_target(target).failures().contains_predicate(matching.contains("prebuilt"))

def _test_a_source_built_runtime_takes_a_build_profile(name):
    analysis_test(
        name = name,
        target = _TESTS + "profiled_runtime",
        impl = _test_a_source_built_runtime_takes_a_build_profile_impl,
        config_settings = {
            "//command_line_option:platforms": str(Label("//godot/platforms:macos_arm64")),
        } | own_toolchains([_FIXTURES + "/source_built_runtime:all"]),
        # The source-built fixture's native graph analyzes with an Apple toolchain.
        attr_values = {"target_compatible_with": ["@platforms//os:macos"]},
    )

def _test_a_source_built_runtime_takes_a_build_profile_impl(env, target):
    env.expect.that_str(target[GodotComponentInfo].kind).equals("source")

# A registered runtime profile stays: it selects the variant the objects compile in.
def _test_profile_independent_objects_keep_a_runtime_profile(name):
    analysis_test(
        name = name,
        target = _TESTS + "variant_independent",
        impl = _test_profile_independent_objects_keep_a_runtime_profile_impl,
        config_settings = {_BUILD_PROFILE: str(_PROFILE)},
    )

def _test_profile_independent_objects_keep_a_runtime_profile_impl(env, target):
    env.expect.that_target(target).default_outputs().contains_exactly([
        "godot/engine/private/tests/profile.gdbuild",
    ])

def _test_a_config_setting_selects_the_variant_of_a_profile(name):
    analysis_test(
        name = name,
        target = _TESTS + "variant_probe",
        impl = _test_a_config_setting_selects_the_variant_of_a_profile_impl,
        config_settings = {_BUILD_PROFILE_LABEL: str(_PROFILE)},
    )

def _test_a_config_setting_selects_the_variant_of_a_profile_impl(env, target):
    env.expect.that_target(target).default_outputs().contains_exactly([
        "godot/engine/private/tests/profile.gdbuild",
    ])

def _test_an_unregistered_profile_names_its_registration(name):
    analysis_test(
        name = name,
        target = _TESTS + "class_generator",
        impl = _test_an_unregistered_profile_names_its_registration_impl,
        config_settings = {_BUILD_PROFILE: str(_PROFILE)},
    )

def _test_an_unregistered_profile_names_its_registration_impl(env, target):
    arguments = _class_generator_arguments(target)
    env.expect.that_str(arguments[arguments.index("--registration") + 1]).equals(
        'godot_engines.runtime_profile(profile = "//godot/engine/private/tests:profile.gdbuild")',
    )

def _test_a_registered_profile_may_set_build_options(name):
    analysis_test(
        name = name,
        target = _TESTS + "registered_class_generator",
        impl = _test_a_registered_profile_may_set_build_options_impl,
        config_settings = {_BUILD_PROFILE: str(_PROFILE)},
    )

def _test_a_registered_profile_may_set_build_options_impl(env, target):
    env.expect.that_collection(_class_generator_arguments(target)).not_contains("--registration")

def _test_the_registration_names_the_selected_engine(name):
    analysis_test(
        name = name,
        target = _TESTS + "class_generator",
        impl = _test_the_registration_names_the_selected_engine_impl,
        config_settings = {_BUILD_PROFILE: str(_PROFILE), str(Label("//godot:engine")): "petri"},
    )

def _test_the_registration_names_the_selected_engine_impl(env, target):
    arguments = _class_generator_arguments(target)
    env.expect.that_str(arguments[arguments.index("--registration") + 1]).contains('engine = "petri"')

# A slot with a prebuilt and a source-built runtime leaves applications with a build profile
# to the source-built one.
def _test_a_tuned_runtime_skips_prebuilt_components(name):
    analysis_test(
        name = name,
        target = _TESTS + "profiled_runtime",
        impl = _test_a_tuned_runtime_skips_prebuilt_components_impl,
        expect_failure = True,
        config_settings = {
            "//command_line_option:platforms": str(Label(_TESTS + "linux_x86_64")),
        } | own_toolchains([_FIXTURES + "/tuned_slot:all"]),
    )

def _test_a_tuned_runtime_skips_prebuilt_components_impl(env, target):
    # The fixture's tuned component is a file too, so it fails, naming itself.
    env.expect.that_target(target).failures().contains_predicate(
        matching.contains("runtime_linux_x86_64_release_tuned"),
    )

def _test_an_unprofiled_runtime_takes_the_prebuilt_component(name):
    analysis_test(
        name = name,
        target = _TESTS + "resolved_runtime",
        impl = _test_an_unprofiled_runtime_takes_the_prebuilt_component_impl,
        config_settings = {
            "//command_line_option:platforms": str(Label(_TESTS + "linux_x86_64")),
        } | own_toolchains([_FIXTURES + "/tuned_slot:all"]),
    )

def _test_an_unprofiled_runtime_takes_the_prebuilt_component_impl(env, target):
    env.expect.that_str(target[GodotComponentInfo].component).equals(
        str(Label(_FIXTURES + "/tuned_slot:runtime_linux_x86_64_release")),
    )

# Engine optimization tunes the runtime under -c opt only: there the slot's source-built
# runtime serves, elsewhere the prebuilt one, whose optimization is fixed.
def _tuning_test(name, compilation_mode, optimize, expected):
    analysis_test(
        name = name,
        target = _TESTS + "resolved_runtime",
        impl = lambda env, target: env.expect.that_str(target[GodotComponentInfo].component).equals(
            str(Label(_FIXTURES + "/tuned_slot:" + expected)),
        ),
        config_settings = {
            "//command_line_option:platforms": str(Label(_TESTS + "linux_x86_64")),
            "//command_line_option:compilation_mode": compilation_mode,
            str(Label("//godot:engine_optimize")): optimize,
        } | own_toolchains([_FIXTURES + "/tuned_slot:all"]),
    )

def _test_an_optimized_release_takes_the_tuned_runtime(name):
    _tuning_test(name, "opt", "size", "runtime_linux_x86_64_release_tuned")

def _test_a_release_with_default_optimization_takes_the_prebuilt_runtime(name):
    _tuning_test(name, "opt", "auto", "runtime_linux_x86_64_release")

def _test_optimization_outside_opt_keeps_the_prebuilt_runtime(name):
    _tuning_test(name, "fastbuild", "size", "runtime_linux_x86_64_release")

def build_profile_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [_test_the_runtime_edge_sets_the_build_profile],
        tests = [
            _test_the_class_generator_reads_the_profile,
            _test_without_a_profile_the_class_generator_reads_none,
            _test_profile_independent_objects_reset_the_profile,
            _test_a_prebuilt_runtime_refuses_a_build_profile,
            _test_a_source_built_runtime_takes_a_build_profile,
            _test_profile_independent_objects_keep_a_runtime_profile,
            _test_a_config_setting_selects_the_variant_of_a_profile,
            _test_an_unregistered_profile_names_its_registration,
            _test_a_registered_profile_may_set_build_options,
            _test_the_registration_names_the_selected_engine,
            _test_a_tuned_runtime_skips_prebuilt_components,
            _test_an_unprofiled_runtime_takes_the_prebuilt_component,
            _test_an_optimized_release_takes_the_tuned_runtime,
            _test_a_release_with_default_optimization_takes_the_prebuilt_runtime,
            _test_optimization_outside_opt_keeps_the_prebuilt_runtime,
        ],
    )
