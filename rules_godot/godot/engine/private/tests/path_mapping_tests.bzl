"""
The engine's own actions keep one command in every configuration under path mapping.

With --experimental_output_paths=strip, an action that declares supports-path-mapping keeps
one cache key in every configuration if its command line names output files only through
File arguments and the files it reads name no output directory. Starlark cannot read an
action's execution requirements, so these tests check the second condition.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")

_ANALYSIS = "//godot/engine/private/tests/define_analysis:analysis"

def _action(target, mnemonic):
    return [action for action in target.actions if action.mnemonic == mnemonic][0]

def _test_the_define_analysis_script_names_no_output_directory(name):
    analysis_test(name = name, target = _ANALYSIS, impl = _test_the_define_analysis_script_names_no_output_directory_impl)

def _test_the_define_analysis_script_names_no_output_directory_impl(env, target):
    # The script the analysis runs is the same file in every configuration; the output
    # directories come as arguments, which path mapping rewrites.
    script = _action(target, "FileWrite")
    env.expect.that_bool("bazel-out/" in script.content, "the script names an output directory").equals(False)

def path_mapping_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_the_define_analysis_script_names_no_output_directory,
        ],
    )
