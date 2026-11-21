"""
Which actions a change of application format, signing mode or export platform reconfigures.

A setting reruns an action only when it changes the action's command line, inputs or outputs,
or a file the action reads that another action writes. The tests analyze one fixture under
both values of a setting and compare those facts of the actions that must stay cached. A pack
built for an export platform by itself configures its native code as an application of that
platform does.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/private/config:application.bzl", "application_pack")
load("//godot/private/config:settings.bzl", "MERGE_ANDROID_MANIFEST_PERMISSIONS", "platform_slice_name")
load("//godot/private/tests:pack_forms.bzl", "GODOT_EXPORT")
load(
    ":action_graph.bzl",
    "expect_same_actions",
    "is_compilation",
    "platform_slice_cpus",
    "reached",
    "reached_actions",
    "reads",
)
load(":android_settings.bzl", "ANDROID", "ANDROID_SDK", "MOBILE_FIXTURE", "OWN_TOOLCHAINS")

_FORMAT = str(Label("//godot:android_format"))
_SIGNING = str(Label("//godot:macos_signing"))

_MACOS_FIXTURE = "//godot/platforms/private/tests/fixtures/macos_app_with_extension:"

# macOS signing runs on a macOS host only.
_MACOS_HOST = {"size": "small", "target_compatible_with": ["@platforms//os:macos"]}

# A macOS application whose minimum, Godot's default 11.0, is also the build's.
_MACOS = {
    "//command_line_option:platforms": str(Label("//godot/platforms:macos_arm64")),
    "//command_line_option:macos_minimum_os": "11.0",
}

def _configured_transition_impl(settings, attr):
    return {
        _FORMAT: attr.android_format or settings[_FORMAT],
        _SIGNING: attr.macos_signing or settings[_SIGNING],
        MERGE_ANDROID_MANIFEST_PERMISSIONS: attr.merge_android_manifest_permissions or settings[MERGE_ANDROID_MANIFEST_PERMISSIONS],
    }

_configured_transition = transition(
    implementation = _configured_transition_impl,
    inputs = [_FORMAT, _SIGNING, MERGE_ANDROID_MANIFEST_PERMISSIONS],
    outputs = [_FORMAT, _SIGNING, MERGE_ANDROID_MANIFEST_PERMISSIONS],
)

def _configured_impl(ctx):
    return [DefaultInfo(files = ctx.attr.target[0][DefaultInfo].files)]

_configured = rule(
    doc = "Analyze a target with one application format, macOS signing mode or Android permission merging.",
    implementation = _configured_impl,
    attrs = {
        "target": attr.label(mandatory = True, cfg = _configured_transition),
        "android_format": attr.string(),
        "macos_signing": attr.string(),
        "merge_android_manifest_permissions": attr.bool(),
        "_allowlist_function_transition": attr.label(default = "@bazel_tools//tools/allowlists/function_transition_allowlist"),
    },
)

def _arrange(name, target, setting, values):
    """Declare one configured target per value and return them by value."""
    targets = {}
    for value in values:
        _configured(
            name = "%s_%s" % (name, value),
            target = target,
            tags = ["manual"],
            **{setting: value}
        )
        targets[value] = ":%s_%s" % (name, value)
    return targets

# The actions that produce the PCK, the imports and the compiled native code. The bundle's
# own JNI ZIP of extension libraries only collects libraries that are already built.
_CONTENT = (
    "GodotExportConfig",
    "GodotImport",
    "GodotInitialize",
    "GodotPack",
    "GodotProjectConfig",
)
_NATIVE = ("CppCompile", "CppLink", "CppArchive", "ObjcCompile", "GodotCppBindings")

def _content_or_native(entry):
    return entry.action.mnemonic.startswith(_CONTENT + _NATIVE)

def _test_android_bundle_reuses_content_and_native_actions(name):
    analysis_test(
        name = name,
        targets = _arrange(name, MOBILE_FIXTURE + "app", "android_format", ["apk", "aab"]),
        impl = _android_bundle_reuses_content_and_native_actions,
        config_settings = {
            "//command_line_option:platforms": str(Label("//godot/platforms:android_arm64")),
        } | OWN_TOOLCHAINS | GODOT_EXPORT,
        extra_target_under_test_aspects = [reached_actions],
        attr_values = ANDROID_SDK,
    )

def _android_bundle_reuses_content_and_native_actions(env, targets):
    mnemonics = [entry.action.mnemonic for entry in reached(targets.apk)]
    for mnemonic in ["GodotPack", "CppCompile"]:
        env.expect.where(mnemonic = mnemonic).that_collection(mnemonics).contains(mnemonic)
    env.expect.that_collection(
        [file.extension for file in targets.aab[DefaultInfo].files.to_list()],
        expr = "bundle extensions",
    ).contains("aab")
    expect_same_actions(env, targets.apk, targets.aab, _content_or_native)

def _godot_or_compilation(entry):
    return entry.action.mnemonic.startswith("Godot") or is_compilation(entry.action.mnemonic)

def _test_desktop_pack_ignores_android_format(name):
    analysis_test(
        name = name,
        targets = _arrange(name, _MACOS_FIXTURE + "pack", "android_format", ["apk", "aab"]),
        impl = _desktop_pack_ignores_android_format,
        extra_target_under_test_aspects = [reached_actions],
        attr_values = {"size": "small"},
    )

def _desktop_pack_ignores_android_format(env, targets):
    expect_same_actions(env, targets.apk, targets.aab, _godot_or_compilation)

def _test_macos_signing_mode_reruns_only_signing(name):
    analysis_test(
        name = name,
        targets = _arrange(name, _MACOS_FIXTURE + "app", "macos_signing", ["unsigned", "adhoc"]),
        impl = _macos_signing_mode_reruns_only_signing,
        config_settings = _MACOS,
        extra_target_under_test_aspects = [reached_actions],
        attr_values = _MACOS_HOST,
    )

def _not_signing(entry):
    return _godot_or_compilation(entry) and entry.action.mnemonic != "GodotMacosSign"

def _signing(target):
    return [entry for entry in reached(target) if entry.action.mnemonic == "GodotMacosSign"]

def _macos_signing_mode_reruns_only_signing(env, targets):
    env.expect.that_collection(_signing(targets.unsigned), expr = "unsigned GodotMacosSign").has_size(0)
    signing = _signing(targets.adhoc)
    env.expect.that_collection(signing, expr = "ad hoc GodotMacosSign").has_size(1)
    expect_same_actions(env, targets.unsigned, targets.adhoc, _not_signing)

    # The entitlements reach only the signer.
    path = "fixtures/macos_app_with_extension/signing.entitlements"
    for entry in signing:
        env.expect.where(path = path).that_bool(reads(entry.action, path), expr = "GodotMacosSign reads it").equals(True)
    for entry in reached(targets.adhoc):
        if entry.action.mnemonic != "GodotMacosSign":
            env.expect.where(owner = entry.owner, mnemonic = entry.action.mnemonic, path = path).that_bool(
                reads(entry.action, path),
            ).equals(False)

def _platform_slices_test(name, export_platform, cpus):
    analysis_test(
        name = name,
        target = MOBILE_FIXTURE + "app",
        impl = _configures_platform_slices,
        attrs = {"cpus": attr.string_list()},
        config_settings = {
            "//command_line_option:platforms": str(Label(export_platform)),
        } | OWN_TOOLCHAINS,
        extra_target_under_test_aspects = [reached_actions],
        attr_values = ANDROID_SDK | {"cpus": cpus},
    )

def _configures_platform_slices(env, target):
    env.expect.that_collection(platform_slice_cpus(target), expr = "configured platform slices").contains_exactly(env.ctx.attr.cpus)

def _test_arm64_android_app_configures_only_arm64_platform_slice(name):
    _platform_slices_test(name, "//godot/platforms:android_arm64", ["arm64"])

def _test_distribution_android_app_configures_both_platform_slices(name):
    _platform_slices_test(name, MOBILE_FIXTURE + "android_distribution", ["arm64", "x86_64"])

def _test_ios_simulator_pack_compiles_its_extension_for_the_simulator(name):
    analysis_test(
        name = name,
        # The pack itself, without an application whose rules_apple edge configures Apple
        # builds for iOS. The build's own configuration for the export platform is the
        # subject, so the test sets only --platforms instead of using in_platform_slice
        # (//godot/private/tests:configurations.bzl).
        target = MOBILE_FIXTURE + "pack",
        impl = _ios_simulator_pack_compiles_its_extension_for_the_simulator,
        config_settings = {
            "//command_line_option:platforms": str(Label("//godot/platforms:ios_sim_arm64")),
        },
        extra_target_under_test_aspects = [reached_actions],
        attr_values = _MACOS_HOST,
    )

def _ios_simulator_pack_compiles_its_extension_for_the_simulator(env, target):
    triples = [
        entry.action.argv[entry.action.argv.index("-target") + 1]
        for entry in reached(target)
        # The extension's tool view compiles it for the execution platform as well.
        if entry.owner.endswith(":hello.native") and is_compilation(entry.action.mnemonic) and "ios" in entry.platform
    ]
    env.expect.that_bool(bool(triples), expr = "the extension compiles").equals(True)
    for triple in triples:
        env.expect.where(triple = triple).that_bool(
            triple.startswith("arm64-apple-ios") and triple.endswith("-simulator"),
        ).equals(True)

def _test_android_permission_merging_keeps_one_pack_configuration(name):
    # The application's edge to its pack, as godot_app has it.
    application_pack(
        name = name + "_application_pack",
        application_id = "org.example.merging",
        tags = ["manual"],
        deps = [MOBILE_FIXTURE + "pack"],
    )
    _configured(
        name = name + "_merging_application_pack",
        merge_android_manifest_permissions = True,
        tags = ["manual"],
        target = ":%s_application_pack" % name,
    )
    analysis_test(
        name = name,
        targets = {
            "app": MOBILE_FIXTURE + "app",
            "pack": ":%s_application_pack" % name,
            "merging_pack": ":%s_merging_application_pack" % name,
        },
        impl = _android_permission_merging_keeps_one_pack_configuration,
        config_settings = ANDROID | GODOT_EXPORT,
        extra_target_under_test_aspects = [reached_actions],
        attr_values = ANDROID_SDK,
    )

def _output_paths(target, mnemonics):
    return sorted({
        file.path: None
        for entry in reached(target)
        if entry.action.mnemonic in mnemonics
        for file in entry.action.outputs.to_list()
    })

_PACK_ACTIONS = ["GodotPack", "GodotImport", "GodotValidate", "CppCompile", "CppLink", "Javac"]

def _android_permission_merging_keeps_one_pack_configuration(env, targets):
    # The application's merge, not those of its libraries.
    merges = [
        entry.action
        for entry in reached(targets.app)
        if entry.action.mnemonic == "MergeManifests" and entry.owner.endswith(".native_apk")
    ]
    env.expect.that_collection(merges, expr = "application manifest merges").has_size(1)
    for merge in merges:
        env.expect.that_collection(merge.argv, expr = "merge arguments").contains("--mergeManifestPermissions")

    # Below the application's edge to its pack, the export, imports, native code and
    # platform libraries have the same output paths with and without permission merging.
    paths = _output_paths(targets.pack, _PACK_ACTIONS)
    env.expect.that_bool(bool(_output_paths(targets.pack, ["CppCompile"])), expr = "the pack compiles native code").equals(True)
    env.expect.that_collection(_output_paths(targets.merging_pack, _PACK_ACTIONS), expr = "merging pack actions").contains_exactly(paths)

def _compilation_roots(target, accept):
    """The output roots, one per configuration, of the compile actions accept selects."""
    return sorted({
        file.root.path: None
        for entry in reached(target)
        if is_compilation(entry.action.mnemonic) and accept(entry)
        for file in entry.action.outputs.to_list()
    })

def _test_ios_app_compiles_its_platform_slice_in_one_configuration(name):
    analysis_test(
        name = name,
        target = MOBILE_FIXTURE + "app",
        impl = _ios_app_compiles_its_platform_slice_in_one_configuration,
        config_settings = {
            "//command_line_option:platforms": str(Label("//godot/platforms:ios_sim_x86_64")),
        },
        extra_target_under_test_aspects = [reached_actions],
        attr_values = _MACOS_HOST,
    )

def _ios_app_compiles_its_platform_slice_in_one_configuration(env, target):
    # The application's entry support, its platform libraries and the extension's
    # library, which rules_apple's split and the pack's platform slice reach.
    platform_slice = ":" + platform_slice_name("ios_sim_x86_64", "x86_64")
    roots = _compilation_roots(target, lambda entry: entry.platform.endswith(platform_slice))
    env.expect.that_collection(roots, expr = "configurations compiling for the platform slice").has_size(1)

def _test_android_app_compiles_its_extension_once_per_configuration_role(name):
    analysis_test(
        name = name,
        target = MOBILE_FIXTURE + "app",
        impl = _android_app_compiles_its_extension_once_per_configuration_role,
        config_settings = ANDROID,
        extra_target_under_test_aspects = [reached_actions],
        attr_values = ANDROID_SDK,
    )

def _extension_roots(target, platform_suffix):
    """The configurations in which the fixture's extension compiles for a target platform."""
    return _compilation_roots(
        target,
        lambda entry: entry.owner.endswith(":hello.native") and entry.platform.endswith(platform_suffix),
    )

def _android_app_compiles_its_extension_once_per_configuration_role(env, target):
    # rules_android's split, which the application packages: android_binary's own
    # configuration and the bootstrap reach no native code of the pack.
    env.expect.that_collection(
        _extension_roots(target, ":" + platform_slice_name("android_arm64", "arm64")),
        expr = "configurations compiling the extension for the platform slice",
    ).has_size(1)

    # The content configuration of the pack's export: the application's own edges, such as
    # the one its ID comes from, reach no native code of the pack.
    env.expect.that_collection(
        _extension_roots(target, ":android_arm64"),
        expr = "configurations compiling the extension for the export platform",
    ).has_size(1)

def _test_macos_app_extension_shares_the_project_context_configuration(name):
    analysis_test(
        name = name,
        target = _MACOS_FIXTURE + "app",
        impl = _macos_app_extension_shares_the_project_context_configuration,
        # The signing test's configuration: unsigned is the default, so its unsigned
        # application shares this test's configurations.
        config_settings = _MACOS,
        extra_target_under_test_aspects = [reached_actions],
        attr_values = _MACOS_HOST,
    )

def _macos_app_extension_shares_the_project_context_configuration(env, target):
    # The extension's library is reached through the application's pack and through the
    # project context. It passes because the build's minimum equals the application's
    # default: with another build minimum, the project context compiles it for that one.
    env.expect.that_collection(
        _extension_roots(target, ":macos_arm64"),
        expr = "configurations compiling the extension",
    ).has_size(1)

def configuration_invariance_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_android_app_compiles_its_extension_once_per_configuration_role,
            _test_android_bundle_reuses_content_and_native_actions,
            _test_android_permission_merging_keeps_one_pack_configuration,
            _test_arm64_android_app_configures_only_arm64_platform_slice,
            _test_desktop_pack_ignores_android_format,
            _test_distribution_android_app_configures_both_platform_slices,
            _test_ios_app_compiles_its_platform_slice_in_one_configuration,
            _test_ios_simulator_pack_compiles_its_extension_for_the_simulator,
            _test_macos_app_extension_shares_the_project_context_configuration,
            _test_macos_signing_mode_reruns_only_signing,
        ],
    )
