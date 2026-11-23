"""Independent expectations for the bounded owned export policy."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/private:export_options.bzl", "resolve_export_options")
load("//godot/private/engine:profiles.bzl", "engine_profile")
load(":failures.bzl", "failure_test")

_APPLICATION_CONTEXT = {
    "application_id": "org.example.policy",
    "macos_minimum_os_version": "11.0",
    "ios_minimum_os_version": "15.0",
    "ios_families": ["ipad", "iphone"],
    "android_min_sdk_version": 0,
    "android_target_sdk_version": 0,
}
_PACK = {
    "linux": {},
    "macos": {
        "application/bundle_identifier": '"org.example.policy"',
        "application/min_macos_version_arm64": '"11.0"',
        "application/min_macos_version_x86_64": '"11.0"',
    },
    "android": {
        "package/unique_name": '"org.example.policy"',
        "gradle_build/min_sdk": '"24"',
        "gradle_build/target_sdk": '"36"',
    },
    "ios": {
        "application/bundle_identifier": '"org.example.policy"',
        "application/min_ios_version": '"15.0"',
        "application/targeted_device_family": "2",
    },
}
_PRESET = {
    "linux": {},
    "macos": {},
    "android": {
        "architectures/armeabi-v7a": "false",
        "architectures/arm64-v8a": "true",
        "architectures/x86": "false",
        "architectures/x86_64": "false",
    },
    "ios": {"architectures/arm64": "true"},
}
_DESKTOP_PRELUDE = {"binary_format/architecture": '"arm64"', "binary_format/embed_pck": "false"}
_PRELUDE = {"linux": _DESKTOP_PRELUDE, "macos": _DESKTOP_PRELUDE, "android": {}, "ios": {}}

def _context(operating_system, application_context = _APPLICATION_CONTEXT, cpus = ["arm64"]):
    return struct(operating_system = operating_system, application_context = application_context, cpus = cpus)

def _test_owned_options_follow_the_baseline_policy(env):
    for version in ["4.7.2", "4.8.0-beta1"]:
        profile = engine_profile(version)
        for operating_system in ["linux", "macos", "android", "ios"]:
            for application_context in [_APPLICATION_CONTEXT, {}]:
                authored = {"application/name": '"Policy fixture"'}
                result = resolve_export_options(authored, _context(operating_system, application_context), profile, version)
                pack = authored | (_PACK[operating_system] if application_context else {})
                expect = env.expect.where(version = version, operating_system = operating_system, application_context = application_context)
                expect.that_dict(result.pack_options).contains_exactly(pack)
                expect.that_dict(result.preset_options).contains_exactly(pack | _PRESET[operating_system])
                expect.that_dict(result.preset_prelude).contains_exactly(_PRELUDE[operating_system])
                result.pack_options["fixture/mutation"] = "true"
                expect.that_dict(result.preset_options).keys().not_contains("fixture/mutation")
                expect.that_dict(authored).contains_exactly({"application/name": '"Policy fixture"'})

def _test_owned_options_follow_the_engine_profile(env):
    stable = engine_profile("4.7.2")
    preview = engine_profile("4.8.0-beta1")
    changed = dict(preview)
    changed["owned_export_options"] = dict(preview["owned_export_options"])
    changed["owned_export_options"]["ios"] = [dict(row) for row in preview["owned_export_options"]["ios"]]
    for row in changed["owned_export_options"]["ios"]:
        if row["derive"] == "application_enum":
            row["choices"] = dict(row["choices"])
            row["choices"]["ipad,iphone"] = 0
    altered = resolve_export_options({}, _context("ios"), changed, "4.8.0-beta1")
    env.expect.that_str(altered.pack_options["application/targeted_device_family"]).equals("0")
    for profile, version in [(stable, "4.7.2"), (preview, "4.8.0-beta1")]:
        result = resolve_export_options({}, _context("ios"), profile, version)
        env.expect.where(version = version).that_str(result.pack_options["application/targeted_device_family"]).equals("2")
    for operating_system in ["linux", "macos", "android"]:
        expect = env.expect.where(operating_system = operating_system)
        original = resolve_export_options({}, _context(operating_system), preview, "4.8.0-beta1")
        result = resolve_export_options({}, _context(operating_system), changed, "4.8.0-beta1")

        # Unrelated exporter retained.
        expect.that_bool(result == original, "result == original").equals(True)
        older = resolve_export_options({}, _context(operating_system), stable, "4.7.2")
        delta = "gradle_build/minification" if operating_system == "android" else "debug/export_debug_symbols"
        expect.that_dict(result.rejected_options).keys().contains(delta)
        expect.that_dict(older.rejected_options).keys().not_contains(delta)
        expect.that_dict(result.preset_options).keys().not_contains(delta)
        expect.that_dict(result.preset_prelude).keys().not_contains(delta)

def _test_policy_row_change_reaches_only_its_exporter(env):
    baseline = engine_profile("4.7.2")
    preview = engine_profile("4.8.0-beta1")
    originals = {}
    for operating_system in _PACK:
        originals[operating_system] = resolve_export_options({}, _context(operating_system), baseline, "4.7.2")
        expect = env.expect.where(operating_system = operating_system)
        expect.where(profile = "baseline").that_dict(originals[operating_system].pack_options).contains_exactly(_PACK[operating_system])
        expect.where(profile = "preview").that_dict(
            resolve_export_options({}, _context(operating_system), preview, "4.8.0-beta1").pack_options,
        ).contains_exactly(_PACK[operating_system])
    for family, operating_system, key, update, literal in [
        ("cpu", "android", "architectures/arm64-v8a", {"cpu": "x86_64"}, "false"),
        # A deliberately changed scalar mapping in disposable policy data. This
        # tests propagation, not approval of a new application identifier policy.
        ("identity", "ios", "application/bundle_identifier", {"source": "ios_minimum_os_version"}, '"15.0"'),
        ("sdk", "android", "gradle_build/target_sdk", {}, '"37"'),
        ("fixed", "linux", "binary_format/embed_pck", {"value": True}, "true"),
    ]:
        changed = dict(baseline)
        changed["owned_export_options"] = dict(baseline["owned_export_options"])
        changed["owned_export_options"][operating_system] = [row | update if row["key"] == key else row for row in baseline["owned_export_options"][operating_system]]
        if family == "sdk":
            changed["android"] = baseline["android"] | {"target_sdk": "37"}
        result = resolve_export_options({}, _context(operating_system), changed, "4.7.2")
        expected_pack = dict(_PACK[operating_system])
        expected_preset = _PACK[operating_system] | _PRESET[operating_system]
        expected_prelude = dict(_PRELUDE[operating_system])
        if family in ["identity", "sdk"]:
            expected_pack[key] = literal
            expected_preset[key] = literal
        elif family == "cpu":
            expected_preset[key] = literal
        else:
            expected_prelude[key] = literal
        expect = env.expect.where(family = family)
        expect.where(output = "provider").that_dict(result.pack_options).contains_exactly(expected_pack)
        expect.where(output = "export/probe").that_dict(result.preset_options).contains_exactly(expected_preset)
        expect.where(output = "prelude").that_dict(result.preset_prelude).contains_exactly(expected_prelude)
        for other, original in originals.items():
            if other != operating_system:
                # Other exporter unchanged.
                expect.where(other = other).that_bool(
                    resolve_export_options({}, _context(other), changed, "4.7.2") == original,
                    "result == original",
                ).equals(True)

def _unsupported_profile_impl(_ctx):
    engine_profile("4.9.0")
    return []

_unsupported_profile = rule(implementation = _unsupported_profile_impl)

def _test_unsupported_engine_profile_fails(name):
    _unsupported_profile(name = name + "_subject", tags = ["manual"])
    failure_test(name, "rules_godot has no engine profile for Godot 4.9", [":" + name + "_subject"])

def _policy_fixture_impl(ctx):
    profile = dict(engine_profile("4.7.2"))
    profile["owned_export_options"] = {"macos": json.decode(ctx.attr.rows)}
    if ctx.attr.invalid_enum_keys:
        profile["owned_export_options"]["macos"][0]["choices"][1] = 1
    profile["rejected_export_options"] = {"macos": json.decode(ctx.attr.rejected)}
    resolve_export_options({}, _context("macos", json.decode(ctx.attr.application_context)), profile, "4.7.2")
    return []

_policy_fixture = rule(
    implementation = _policy_fixture_impl,
    attrs = {
        "rows": attr.string(),
        "rejected": attr.string(default = "{}"),
        "application_context": attr.string(default = "{}"),
        "invalid_enum_keys": attr.bool(),
    },
)

def _test_malformed_owned_policy_fails(name):
    row = {
        "key": "binary_format/embed_pck",
        "owner": "output-layout",
        "authored": "reject",
        "placement": "prelude",
        "when": "always",
        "derive": "constant",
        "value": False,
    }
    unvalued = {key: value for key, value in row.items() if key != "value"}
    cases = {
        "unknown_field": row | {"expression": "anything"},
        "unknown_owner": row | {"owner": "missing"},
        "unknown_authored": row | {"authored": "missing"},
        "unknown_placement": row | {"placement": "missing"},
        "unknown_guard": row | {"when": "missing"},
        "unknown_derive": row | {"derive": "missing"},
        "missing_derive": {key: value for key, value in row.items() if key != "derive"},
        "missing_value": unvalued,
        "invalid_value": row | {"value": []},
        "match_prelude": row | {"authored": "match"},
        "undocumented_live": row | {"authored": "live"},
        "live_nonconstant": unvalued | {"derive": "first_cpu", "authored": "live", "exception": "Fixture reason; remove when unused."},
        "invalid_enum_keys": unvalued | {"derive": "application_enum", "source": "ios_families", "choices": {"iphone": 0}},
        "cpu_pack_mirror": unvalued | {"derive": "first_cpu", "placement": "pack", "authored": "match"},
        "missing_application_input": unvalued | {"derive": "application_value", "source": "ios_minimum_os_version", "when": "ios_application", "placement": "pack", "authored": "match"},
    }
    targets = []
    for case, invalid in cases.items():
        _policy_fixture(
            name = name + "_" + case,
            rows = json.encode([invalid]),
            application_context = json.encode({"ios_families": ["iphone"]}),
            invalid_enum_keys = case == "invalid_enum_keys",
            tags = ["manual"],
        )
        targets.append(":" + name + "_" + case)
    for case in ["duplicate", "overlap"]:
        _policy_fixture(
            name = name + "_" + case,
            rows = json.encode([row, row] if case == "duplicate" else [row]),
            rejected = json.encode({row["key"]: row["owner"]} if case == "overlap" else {}),
            tags = ["manual"],
        )
        targets.append(":" + name + "_" + case)
    failure_test(name, "Godot 4.7.2 / macos / binary_format/embed_pck", targets)

def owned_options_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_unsupported_engine_profile_fails,
            _test_malformed_owned_policy_fails,
        ],
        basic_tests = [
            _test_owned_options_follow_the_baseline_policy,
            _test_owned_options_follow_the_engine_profile,
            _test_policy_row_change_reaches_only_its_exporter,
        ],
    )
