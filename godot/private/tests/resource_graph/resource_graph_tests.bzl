"""How validate and require_declared reach the graph check over the resource graph of its view."""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:util.bzl", "TestingAspectInfo")
load("//godot:defs.bzl", "godot_resource_graph")
load("//godot/private:view.bzl", "GodotViewInfo")

_FIXTURE = "//godot/private/tests/fixtures/import_context"

def _graph_test(name, impl, **kwargs):
    godot_resource_graph(
        name = name + "_graph",
        project = _FIXTURE + ":configured_project",
        tags = ["manual"],
        deps = [_FIXTURE + ":configured_check", _FIXTURE + ":configured_resources"],
        **kwargs
    )
    analysis_test(
        name = name,
        targets = {"graph": name + "_graph", "view": name + "_graph.view"},
        impl = impl,
    )

def _check(targets):
    return [
        action
        for action in targets.graph[TestingAspectInfo].actions
        if action.mnemonic == "GodotResourceGraphCheck"
    ][0]

def _expect_flags(env, targets, validate, require_declared):
    argv = _check(targets).argv
    env.expect.where(flag = "--validate").that_bool("--validate" in argv).equals(validate)
    env.expect.where(flag = "--require-declared").that_bool(
        "--require-declared" in argv,
    ).equals(require_declared)

# The check reads its view's graph and nothing else.
def _test_graph_check_validates_by_default(name):
    _graph_test(name, _graph_check_validates_by_default)

def _graph_check_validates_by_default(env, targets):
    _expect_flags(env, targets, validate = True, require_declared = False)
    inputs = [
        file
        for file in _check(targets).inputs.to_list()
        # The checker itself and its runfiles.
        if not file.short_path.startswith(("tools/", "../"))
    ]
    env.expect.that_collection(inputs, expr = "check inputs").contains_exactly([
        targets.view[GodotViewInfo].graph,
    ])

def _test_require_declared_reaches_graph_check(name):
    _graph_test(name, _require_declared_reaches_graph_check, require_declared = True)

def _require_declared_reaches_graph_check(env, targets):
    _expect_flags(env, targets, validate = True, require_declared = True)

def _test_graph_check_without_validate_omits_validation(name):
    _graph_test(name, _graph_check_without_validate_omits_validation, validate = False)

def _graph_check_without_validate_omits_validation(env, targets):
    _expect_flags(env, targets, validate = False, require_declared = False)

def resource_graph_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_graph_check_validates_by_default,
            _test_graph_check_without_validate_omits_validation,
            _test_require_declared_reaches_graph_check,
        ],
    )
