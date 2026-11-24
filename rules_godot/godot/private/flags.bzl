"""Command-line build settings of rules_godot."""

visibility("//godot/...")

FlagInfo = provider(
    doc = "The value of a rules_godot build setting, for rules that read it.",
    fields = {"value": "The build setting's string, int or bool value."},
)

def _bool_flag_impl(ctx):
    return [FlagInfo(value = ctx.build_setting_value)]

bool_flag = rule(
    doc = "A boolean build setting, set on the command line like --//godot:headless=false; config_setting or FlagInfo reads it.",
    implementation = _bool_flag_impl,
    build_setting = config.bool(flag = True),
)

def _value_flag_impl(ctx):
    values = getattr(ctx.attr, "values", None)
    if values and ctx.build_setting_value not in values:
        fail("%s must be %s or %s, got %s" % (
            ctx.label.name,
            ", ".join(values[:-1]),
            values[-1],
            ctx.build_setting_value,
        ))
    return [FlagInfo(value = ctx.build_setting_value)]

string_flag = rule(
    doc = "A string build setting that rules read through FlagInfo; values restricts it.",
    implementation = _value_flag_impl,
    build_setting = config.string(flag = True),
    attrs = {"values": attr.string_list(doc = "Allowed values; empty allows any.")},
)

int_flag = rule(
    doc = "An integer build setting that rules read through FlagInfo.",
    implementation = _value_flag_impl,
    build_setting = config.int(flag = True),
)

def _value_impl(ctx):
    return [FlagInfo(value = ctx.attr.value)]

bool_value = rule(
    doc = """
    A boolean that rules read through FlagInfo, such as whether Bazel's --stamp
    is set, which a select decides.
    """,
    implementation = _value_impl,
    attrs = {"value": attr.bool(doc = "The value rules read.")},
)
