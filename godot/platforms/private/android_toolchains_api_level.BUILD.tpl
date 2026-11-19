# config_settings are visible to consumers by default.
config_setting(
    name = "api_level_{LEVEL}",
    flag_values = {"@androidsdk//:api_level": "{LEVEL}"},
    visibility = ["//visibility:private"],
)
