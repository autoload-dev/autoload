"""An analysis test that each of its targets fails analysis with one message."""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:truth.bzl", "matching")

visibility("private")

def _fails_with_message_impl(env, targets):
    for target in targets:
        env.expect.that_target(target).failures().contains_predicate(matching.contains(env.ctx.attr.message))

def failure_test(name, message, targets, config_settings = {}):
    """
    Declare an analysis test that each of targets fails analysis with message.

    Args:
        name: Name of the test.
        message: Required substring of an analysis failure of each target.
        targets: Labels of the failing targets.
        config_settings: Settings of the targets' configuration.
    """
    analysis_test(
        name = name,
        target = targets,
        impl = _fails_with_message_impl,
        attrs = {"message": attr.string()},
        attr_values = {"message": message},
        config_settings = config_settings,
        expect_failure = True,
    )
