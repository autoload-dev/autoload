"""
The files a target under test writes at analysis, such as runner and configuration manifests.

Rules write their manifests with FileWrite actions named after the target, as
`<name>.run.json` or `<name>.import.config.json`; an analysis test reads them through
TestingAspectInfo.
"""

load("@rules_testing//lib:util.bzl", "TestingAspectInfo")

visibility([
    "//godot/engine/private/tests/...",
    "//godot/extension/tests/...",
    "//godot/platforms/private/tests/...",
    "//godot/private/config/tests/...",
    "//godot/private/tests/...",
])

def _write(target, suffix):
    basename = target.label.name + suffix
    for action in target[TestingAspectInfo].actions:
        if action.mnemonic == "FileWrite" and action.outputs.to_list()[0].basename == basename:
            return action
    return None

def written_file(target, suffix):
    """
    Return the file a target's FileWrite writes to `<name><suffix>`.

    Args:
        target: The target under test, analyzed with TestingAspectInfo.
        suffix: What follows the target's name in the output's file name, such as
            ".resource_paths.json".

    Returns:
        The File, or None when the target writes no such file.
    """
    action = _write(target, suffix)
    return action.outputs.to_list()[0] if action else None

def written_content(target, suffix):
    """
    Return the text a target's FileWrite writes to `<name><suffix>`.

    Args:
        target: The target under test, analyzed with TestingAspectInfo.
        suffix: What follows the target's name in the output's file name, such as
            ".run.json".

    Returns:
        The written text; analysis of the test fails when the target writes no such file.
    """
    action = _write(target, suffix)
    if not action:
        fail("%s writes no %s%s" % (target.label, target.label.name, suffix))
    return action.content

def manifest_content(target, suffix):
    """
    Decode the JSON manifest a target's FileWrite writes to `<name><suffix>`.

    Args:
        target: The target under test, analyzed with TestingAspectInfo.
        suffix: What follows the target's name in the output's file name, such as
            ".run.json" or ".import.config.json".

    Returns:
        The decoded manifest.
    """
    return json.decode(written_content(target, suffix))
