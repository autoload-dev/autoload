"""
The Maven minimum check of an Android application.

The check reads the Maven coordinates of the application's Java closure and Godot's Maven
graph, and gates the template activity source that the application compiles: javac reads the
check's output, never the source itself.
"""

load("@rules_java//java:java_library.bzl", "java_library")
load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/platforms/private:maven.bzl", "MavenCoordinatesInfo", "maven_coordinates_aspect")
load(":action_graph.bzl", "mentions", "reached", "reached_actions", "reads", "written_contents")
load(":android_settings.bzl", "ANDROID", "ANDROID_SDK", "MOBILE_FIXTURE")

visibility("private")

_GRAPH = "godot/private/engine/android/maven_graph_install.json"
_ACTIVITY = "godot/private/engine/android/godot_4_7/GodotApp.java"

def _test_aspect_collects_tags_along_java_edges(name):
    # Maven-tagged libraries as rules_jvm_external generates them, one per edge kind.
    java_library(
        name = name + "_exported",
        tags = ["manual", "maven_coordinates=org.example:exported:1.0"],
    )
    java_library(
        name = name + "_runtime",
        tags = ["manual", "maven_coordinates=org.example:runtime:2.0-rc01@aar"],
    )
    java_library(
        name = name + "_direct",
        exports = [":" + name + "_exported"],
        runtime_deps = [":" + name + "_runtime"],
        tags = ["manual", "maven_coordinates=org.example:direct:3.0"],
    )
    java_library(
        name = name + "_untagged",
        srcs = ["fixtures/maven_coordinates/Consumer.java"],
        deps = [":" + name + "_direct"],
        tags = ["manual"],
    )
    analysis_test(
        name = name,
        target = ":" + name + "_untagged",
        impl = _aspect_collects_tags_along_java_edges,
        extra_target_under_test_aspects = [maven_coordinates_aspect],
        attr_values = {"size": "small"},
    )

def _aspect_collects_tags_along_java_edges(env, target):
    # An AAR's packaging is dropped; an untagged target contributes nothing of its own.
    env.expect.that_collection(
        target[MavenCoordinatesInfo].coordinates.to_list(),
    ).contains_exactly([
        "org.example:direct:3.0",
        "org.example:exported:1.0",
        "org.example:runtime:2.0-rc01",
    ])

def _test_check_gates_the_template_activity(name):
    analysis_test(
        name = name,
        target = MOBILE_FIXTURE + "app",
        impl = _check_gates_the_template_activity,
        config_settings = ANDROID,
        extra_target_under_test_aspects = [reached_actions],
        attr_values = ANDROID_SDK,
    )

def _check_gates_the_template_activity(env, target):
    entries = reached(target)
    contents = written_contents(entries)
    checks = []
    others = []
    for entry in entries:
        (checks if entry.action.mnemonic == "GodotMavenMinimums" else others).append(entry.action)
    env.expect.that_bool(len(checks) > 0, expr = "the application checks its minimums").equals(True)
    for check in checks:
        for path in [_GRAPH, _ACTIVITY]:
            env.expect.where(path = path).that_bool(reads(check, path)).equals(True)

        # The coordinates of the shell library's and the template activity's Maven
        # dependencies, as resolved in the shared installation.
        for module in ["androidx.fragment:fragment:", "androidx.activity:activity:"]:
            env.expect.where(module = module).that_bool(
                mentions(check, module, contents),
            ).equals(True)

        # The diagnostic names the application as its BUILD file declares it.
        env.expect.that_collection(check.argv).contains(
            MOBILE_FIXTURE + "app",
        )
        checked = check.outputs.to_list()[0].short_path

        # javac compiles the check's output; no other action reads the source itself.
        env.expect.that_bool(
            any([action.mnemonic == "Javac" and reads(action, checked) for action in others]),
            expr = "javac compiles the checked template activity",
        ).equals(True)
    for action in others:
        env.expect.where(mnemonic = action.mnemonic).that_bool(
            reads(action, _ACTIVITY),
        ).equals(False)

def maven_minimums_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_aspect_collects_tags_along_java_edges,
            _test_check_gates_the_template_activity,
        ],
    )
