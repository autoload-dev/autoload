"""
Configured evidence of the API contract fixtures, which the contract tests compare with the
documentation.

`contract_evidence` analyzes its targets in one configuration, which a transition sets from
the case's settings, and writes what analysis reports of each: the number of default files
and runfiles, whether it runs, its output groups and which of the providers the checks ask
for it returns. It builds none of them: the file is written from analysis alone.
"""

load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("@rules_java//java/common:java_info.bzl", "JavaInfo")
load("//godot/private:flags.bzl", "FlagInfo")

# The settings a case may give, by the key of its `settings`; a case changes no other one.
SETTINGS = [
    "//command_line_option:platforms",
    str(Label("//godot:variant")),
    str(Label("//godot:android_format")),
]

def _setting_key(key):
    """The key of a setting as SETTINGS names it: a command-line option or a canonical label."""
    return key if key.startswith("//command_line_option:") else str(Label(key))

def _configuration_impl(settings, attr):
    given = {_setting_key(key): value for key, value in attr.settings.items()}
    unknown = [key for key in given if key not in SETTINGS]
    if unknown:
        fail("unsupported contract case settings: %s" % unknown)
    return {key: given.get(key, settings[key]) for key in SETTINGS}

_configuration = transition(
    implementation = _configuration_impl,
    inputs = SETTINGS,
    outputs = SETTINGS,
)

# The providers the checks require of some kinds of target, by the name they report.
_PROVIDERS = {
    "CcInfo": CcInfo,
    "ConstraintSettingInfo": platform_common.ConstraintSettingInfo,
    "ConstraintValueInfo": platform_common.ConstraintValueInfo,
    "JavaInfo": JavaInfo,
    "PlatformInfo": platform_common.PlatformInfo,
    "ToolchainInfo": platform_common.ToolchainInfo,
    "//godot/private:flags.bzl%FlagInfo": FlagInfo,
}

def _facts(label, target):
    """What analysis reports of one configured target, as the checks compare it."""
    default = target[DefaultInfo]
    groups = target[OutputGroupInfo] if OutputGroupInfo in target else None
    return {
        "executable": default.files_to_run.executable != None and
                      default.files_to_run.runfiles_manifest != None,
        "files": len(default.files.to_list()),
        "groups": dir(groups) if groups else [],
        "label": label,
        "providers": [name for name, provider in _PROVIDERS.items() if provider in target],
        # Whether it has runfiles, without flattening those of an engine.
        "runfiles": 1 if default.default_runfiles.files else 0,
    }

def _contract_evidence_impl(ctx):
    if len(ctx.attr.labels) != len(ctx.attr.targets):
        fail("labels must name each target in order")
    output = ctx.actions.declare_file(ctx.label.name + ".json")
    ctx.actions.write(output, json.encode_indent({
        "facts": [
            _facts(label, target)
            for label, target in zip(ctx.attr.labels, ctx.attr.targets)
        ],
        "settings": ctx.attr.settings,
    }) + "\n")
    return [DefaultInfo(files = depset([output]))]

contract_evidence = rule(
    doc = "Write the configured facts of targets, analyzed with the given settings.",
    implementation = _contract_evidence_impl,
    attrs = {
        "labels": attr.string_list(
            doc = """
            The targets' labels as the cases write them, in order: analysis reports an
            alias by its actual target, so the evidence keeps the authored label.
            """,
        ),
        "settings": attr.string_dict(
            doc = "The settings of the configuration, by key of SETTINGS; others keep theirs.",
        ),
        "targets": attr.label_list(
            doc = "The targets to analyze in the configuration of the settings.",
            allow_files = True,
            cfg = _configuration,
            skip_validations = True,
        ),
    },
)
