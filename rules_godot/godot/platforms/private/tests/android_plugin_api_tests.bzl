"""
Which Android shell an Android plugin compiles against through //godot/platforms:android_plugin_api.

The plugin API resolves the runtime component of the engine its configuration selects, so a
plugin of a project whose engine is not the default one compiles against that engine's
shell library, and the classes stay out of the plugin's runtime classpath. A runtime whose
AAR carries a source-built engine library lends the plugin the unmodified shell's classes,
so compiling a plugin never waits for an engine build.
"""

load("@rules_android//rules:rules.bzl", "android_library")
load("@rules_java//java/common:java_info.bzl", "JavaInfo")
load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:truth.bzl", "matching")
load("//godot/private/config:settings.bzl", "VARIANT")
load("//godot/private/tests:toolchains.bzl", "DEVELOPMENT_ENGINES", "development_engine")
load(":android_settings.bzl", "ANDROID", "ANDROID_SDK")

def _hub_files(engine):
    """A pattern of the files of a development engine's hub, which imports its Android shell."""
    return "*/%s/*" % DEVELOPMENT_ENGINES[engine].hub.repo_name

def _plugin_test(name, impl, config_settings):
    android_library(
        name = name + "_plugin",
        srcs = ["android_plugin_api/Plugin.java"],
        custom_package = "org.example.plugin",
        target_compatible_with = ["@platforms//os:android"],
        tags = ["manual"],
        deps = ["//godot/platforms:android_plugin_api"],
    )
    analysis_test(
        name = name,
        target = name + "_plugin",
        impl = impl,
        config_settings = config_settings,
        attr_values = ANDROID_SDK,
    )

def _compile_classpath(target):
    return [
        file.path
        for action in target.actions
        if action.mnemonic == "Javac"
        for file in action.inputs.to_list()
        if file.extension == "jar"
    ]

def _test_named_engine_shell_reaches_plugin_compile(name):
    _plugin_test(
        name,
        _named_engine_shell_reaches_plugin_compile,
        ANDROID | development_engine("beta"),
    )

def _named_engine_shell_reaches_plugin_compile(env, target):
    classpath = env.expect.that_collection(_compile_classpath(target), expr = "Javac classpath")
    classpath.contains_predicate(matching.str_matches(_hub_files("beta")))
    classpath.not_contains_predicate(matching.str_matches(_hub_files("stable")))

def _test_source_built_runtime_lends_unmodified_shell(name):
    # The official 4.7.2 release has no debug shell, so the hub builds its debug runtime from
    # source.
    _plugin_test(
        name,
        _source_built_runtime_lends_unmodified_shell,
        ANDROID | {VARIANT: "debug"},
    )

def _source_built_runtime_lends_unmodified_shell(env, target):
    env.expect.that_collection(
        _compile_classpath(target),
        expr = "Javac classpath",
    ).contains_predicate(matching.str_matches(_hub_files("stable") + "/_aar/debug.shell/*"))

def _test_shell_classes_stay_out_of_plugin_runtime(name):
    _plugin_test(name, _shell_classes_stay_out_of_plugin_runtime, ANDROID)

def _shell_classes_stay_out_of_plugin_runtime(env, target):
    env.expect.that_collection(
        [file.path for file in target[JavaInfo].transitive_runtime_jars.to_list()],
        expr = "runtime classpath",
    ).not_contains_predicate(matching.str_matches(_hub_files("stable")))

def android_plugin_api_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_named_engine_shell_reaches_plugin_compile,
            _test_shell_classes_stay_out_of_plugin_runtime,
            _test_source_built_runtime_lends_unmodified_shell,
        ],
    )
