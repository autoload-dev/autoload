"""Public pack metadata contracts independent of exporting resources."""

load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:truth.bzl", "subjects")
load("//godot:defs.bzl", "godot_pack")
load("//godot:providers.bzl", "GodotPackInfo", "GodotProjectInfo")
load("//godot/private/config:application.bzl", "application_pack")
load(":failures.bzl", "failure_test")

_ContextInfo = provider(doc = "Whether this configured node has an empty application context.", fields = ["empty"])

def _context_probe_impl(ctx):
    return [_ContextInfo(empty = ctx.attr.empty)]

context_probe = rule(implementation = _context_probe_impl, attrs = {"empty": attr.bool()})

_TraceInfo = provider(
    doc = "Configured regression observations.",
    fields = [
        "kind",
        "projects",
        "cc_defines",
        "context_empty",
        "platform_slice_contexts",
        "project_contexts",
    ],
)

# The edges from a pack to its project and its native path: the configured pack's deps
# and the export's native reach the native path, the export's view names the project.
_EDGES = ["deps", "export", "native", "view", "project"]

def _trace_impl(target, ctx):
    projects = [str(target.label)] if GodotProjectInfo in target else []
    defines = target[CcInfo].compilation_context.defines.to_list() if CcInfo in target else []
    platform_slice_contexts = []
    project_contexts = []
    for name in _EDGES:
        values = getattr(ctx.rule.attr, name, [])
        for dep in (values if type(values) == "list" else [values] if values else []):
            if _TraceInfo in dep:
                projects.extend(dep[_TraceInfo].projects.to_list())
                defines.extend(dep[_TraceInfo].cc_defines.to_list())
                platform_slice_contexts.extend(dep[_TraceInfo].platform_slice_contexts)
                project_contexts.extend(dep[_TraceInfo].project_contexts)
                if dep[_TraceInfo].kind == "godot_pack_native":
                    if ctx.rule.kind == "_pack_export":
                        platform_slice_contexts.append(dep[_TraceInfo].context_empty)
                    elif ctx.rule.kind == "_configured_pack":
                        project_contexts.append(dep[_TraceInfo].context_empty)
    return [_TraceInfo(
        kind = ctx.rule.kind,
        projects = depset(projects),
        cc_defines = depset(defines),
        context_empty = ctx.attr._context_probe[_ContextInfo].empty,
        platform_slice_contexts = platform_slice_contexts,
        project_contexts = project_contexts,
    )]

_trace = aspect(
    implementation = _trace_impl,
    attr_aspects = _EDGES,
    attrs = {"_context_probe": attr.label(default = Label("//godot/private/tests/app_pack:context_probe"))},
)

_MACOS = {"//command_line_option:platforms": str(Label("//godot/platforms:macos_arm64"))}

def _pack_exposes_configured_metadata_impl(env, target):
    pack = target[GodotPackInfo]
    for field in ["operating_system", "cpus", "environment"]:
        env.expect.where(field = field).that_bool(hasattr(pack, field), "Configured pack must expose " + field).equals(True)
    env.expect.that_collection(target[_TraceInfo].projects.to_list()).contains_exactly(
        [str(Label("//godot/private/tests/app_pack:project"))],
    ).in_order()
    env.expect.that_collection([str(t.label) for t in pack.project.platform_libraries]).contains_exactly(
        [str(Label("//godot/private/tests/app_pack:platform_library"))],
    ).in_order()
    env.expect.that_collection(target[DefaultInfo].files.to_list()).contains_exactly([pack.pack_file]).in_order()

    # Preset-only and prelude values must not become explicit pack metadata.
    env.expect.that_dict(pack.export_options).contains_exactly({})

def _test_pack_exposes_configured_metadata(name):
    analysis_test(
        name = name,
        target = ":pack",
        impl = _pack_exposes_configured_metadata_impl,
        extra_target_under_test_aspects = [_trace],
    )

def _clearing_test(name, impl):
    analysis_test(
        name = name,
        target = ":pack",
        impl = impl,
        config_settings = {
            str(Label("//godot/private/config:application_context")): '{"application_id":"org.example.context"}',
        },
        extra_target_under_test_aspects = [_trace],
    )

def _platform_slice_clears_application_context_impl(env, target):
    trace = target[_TraceInfo]
    env.expect.that_bool(trace.context_empty, "The pack must enter with a nonempty application context").equals(False)
    env.expect.that_collection(trace.platform_slice_contexts, "platform_slice must clear the project context independently").contains_exactly([True]).in_order()

def _test_platform_slice_clears_application_context(name):
    _clearing_test(name, _platform_slice_clears_application_context_impl)

def _project_clears_application_context_impl(env, target):
    trace = target[_TraceInfo]
    env.expect.that_bool(trace.context_empty, "The pack must enter with a nonempty application context").equals(False)
    env.expect.that_collection(trace.project_contexts, "project must clear the project context independently").contains_exactly([True]).in_order()

def _test_project_clears_application_context(name):
    _clearing_test(name, _project_clears_application_context_impl)

def _application_context_sets_pack_export_options_impl(env, target):
    env.expect.that_dict(target[GodotPackInfo].export_options).contains_exactly({
        "application/bundle_identifier": '\"org.example.packcontract\"',
        "application/min_macos_version_arm64": '\"11.0\"',
        "application/min_macos_version_x86_64": '\"11.0\"',
    })

def _test_application_context_sets_pack_export_options(name):
    analysis_test(
        name = name,
        target = ":application_context",
        impl = _application_context_sets_pack_export_options_impl,
        config_settings = _MACOS,
    )

def _project_platform_libraries_build_without_application_context_impl(env, target):
    env.expect.that_collection([str(t.label) for t in target[GodotPackInfo].project.platform_libraries]).contains_exactly(
        [str(Label("//godot/private/tests/app_pack:platform_library"))],
    ).in_order()
    env.expect.that_collection(
        target[_TraceInfo].cc_defines.to_list(),
        "The application context must not configure the project's platform libraries",
    ).not_contains("APPLICATION_CONTEXT_PRESENT")

def _test_project_platform_libraries_build_without_application_context(name):
    application_pack(
        name = name + "_subject",
        application_id = "org.example.packcontract",
        tags = ["manual"],
        deps = [":pack"],
    )
    analysis_test(
        name = name,
        target = ":" + name + "_subject",
        impl = _project_platform_libraries_build_without_application_context_impl,
        extra_target_under_test_aspects = [_trace],
    )

def _selected_application_id_sets_bundle_identifier_impl(env, target):
    env.expect.that_str(target[GodotPackInfo].export_options.get("application/bundle_identifier")).equals('\"org.example.other\"')

def _test_selected_application_id_sets_bundle_identifier(name):
    application_pack(
        name = name + "_subject",
        application_id = select({
            "@platforms//os:macos": "org.example.other",
            "//conditions:default": "org.example.other",
        }),
        tags = ["manual"],
        deps = [":empty_pack"],
    )
    analysis_test(
        name = name,
        target = ":" + name + "_subject",
        impl = _selected_application_id_sets_bundle_identifier_impl,
        config_settings = _MACOS,
    )

def _test_authored_bundle_identifier_conflict_fails(name):
    godot_pack(
        name = name + "_pack",
        export_options = {"application/bundle_identifier": '\"org.example.wrong\"'},
        preset_settings = {"script_export_mode": "0"},
        project = ":empty_project",
        tags = ["manual"],
    )
    application_pack(
        name = name + "_subject",
        application_id = "org.example.actual",
        tags = ["manual"],
        deps = [":" + name + "_pack"],
    )
    failure_test(name, "conflicts with authoritative godot_app value", [":" + name + "_subject"], config_settings = _MACOS)

_VariablesInfo = provider(doc = "Make variables an application_pack resolves.", fields = ["application_id"])

def _variable_fixture_impl(ctx):
    return [_VariablesInfo(application_id = ctx.var.get("GODOT_APPLICATION_ID", ""))]

_variable_fixture = rule(implementation = _variable_fixture_impl)

def _application_id_variable_follows_the_platform_impl(env, target):
    env.expect.that_str(target[_VariablesInfo].application_id).equals("org.example.android")

def _test_application_id_variable_follows_the_platform(name):
    application_pack(
        name = name + "_variables",
        application_id = select({
            "@platforms//os:android": "org.example.android",
            "//conditions:default": "org.example.desktop",
        }),
        tags = ["manual"],
        deps = [":empty_pack"],
    )
    _variable_fixture(
        name = name + "_subject",
        tags = ["manual"],
        toolchains = [":" + name + "_variables"],
    )
    analysis_test(
        name = name,
        target = ":" + name + "_subject",
        impl = _application_id_variable_follows_the_platform_impl,
        config_settings = {"//command_line_option:platforms": str(Label("//godot/platforms:android_arm64"))},
    )

def _pack_carries_deprecation_impl(env, target):
    env.expect.that_target(target).attr("deprecation", factory = subjects.str).equals("Use another pack")

# Bazel reports no deprecation within a package, so the warning reaches consumers only
# from the public pack target.
def _test_pack_carries_deprecation(name):
    godot_pack(
        name = name + "_subject",
        deprecation = "Use another pack",
        preset_settings = {"script_export_mode": "0"},
        project = ":empty_project",
        tags = ["manual"],
    )
    analysis_test(
        name = name,
        target = ":" + name + "_subject",
        impl = _pack_carries_deprecation_impl,
    )

# A pack's files are its one exported PCK.
def _pack_files_hold_the_exported_pck_impl(env, target):
    pack = target[GodotPackInfo]
    env.expect.where(field = "pack_files").that_collection(pack.pack_files.to_list()).contains_exactly([pack.pack_file])
    env.expect.where(field = "pack_file").that_str(pack.pack_file.basename).equals("pack.pck")

def _test_pack_files_hold_the_exported_pck(name):
    analysis_test(name = name, target = ":pack", impl = _pack_files_hold_the_exported_pck_impl)

_MEMBERSHIP = "//godot/private/tests/fixtures/project_with_pack_membership"

# A pack lists its own content and that of every pack it requires.
def _available_lists_required_packs_impl(env, targets):
    env.expect.where(pack = "base_pack", field = "available").that_collection(
        [file.basename for file in targets.base[GodotPackInfo].available.to_list()],
    ).contains_exactly(["base_pack.content.json"])
    env.expect.where(pack = "dlc_pack", field = "available").that_collection(
        [file.basename for file in targets.dlc[GodotPackInfo].available.to_list()],
    ).contains_exactly(["base_pack.content.json", "dlc_pack.content.json"])

def _test_available_lists_required_packs(name):
    analysis_test(
        name = name,
        targets = {"base": _MEMBERSHIP + ":base_pack", "dlc": _MEMBERSHIP + ":dlc_pack"},
        impl = _available_lists_required_packs_impl,
    )

# A pack names the registered prebuilt editor that exports it.
def _pack_names_exporting_editor_component_impl(env, target):
    component = target[GodotPackInfo].editor_component
    for field, value in [("role", "editor"), ("kind", "prebuilt"), ("version", "4.7.2"), ("variant", "")]:
        env.expect.where(field = "editor_component " + field).that_str(getattr(component, field)).equals(value)
    env.expect.where(field = "editor_component component").that_str(
        Label(component.component).repo_name.split("+")[-1],
    ).equals("godot")

def _test_pack_names_exporting_editor_component(name):
    analysis_test(name = name, target = ":pack", impl = _pack_names_exporting_editor_component_impl)

# Analysis owns the authored-option and preset checks that need no Godot facts.
def _pack_failure_test(name, message, **kwargs):
    godot_pack(name = name + "_subject", project = ":empty_project", tags = ["manual"], **kwargs)
    failure_test(name, message, [":" + name + "_subject"])

def _test_bazel_owned_export_option_fails(name):
    _pack_failure_test(
        name,
        "Export option binary_format/architecture is bazel-owned; export_platform owns it",
        export_options = {"binary_format/architecture": '\"x86_64\"'},
    )

# Custom features come from the project's build settings only.
def _test_preset_custom_features_fail(name):
    _pack_failure_test(
        name,
        "Unsupported preset_settings key custom_features; use settings/export_options for their namespaces, godot_project.custom_features for custom features",
        preset_settings = {"custom_features": '\"game\"'},
    )

def _test_unknown_preset_setting_fails(name):
    _pack_failure_test(
        name,
        "Unsupported preset_settings key export_filter",
        preset_settings = {"export_filter": '\"all_resources\"'},
    )

def _test_invalid_script_export_mode_fails(name):
    _pack_failure_test(
        name,
        "preset_settings.script_export_mode must be integer 0, 1 or 2",
        preset_settings = {"script_export_mode": "3"},
    )

def _test_preset_setting_as_export_option_fails(name):
    _pack_failure_test(
        name,
        "script_export_mode belongs to preset_settings",
        export_options = {"script_export_mode": "0"},
    )

def pack_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_pack_exposes_configured_metadata,
            _test_pack_files_hold_the_exported_pck,
            _test_available_lists_required_packs,
            _test_pack_names_exporting_editor_component,
            _test_platform_slice_clears_application_context,
            _test_project_clears_application_context,
            _test_application_context_sets_pack_export_options,
            _test_project_platform_libraries_build_without_application_context,
            _test_selected_application_id_sets_bundle_identifier,
            _test_authored_bundle_identifier_conflict_fails,
            _test_application_id_variable_follows_the_platform,
            _test_pack_carries_deprecation,
            _test_bazel_owned_export_option_fails,
            _test_preset_custom_features_fail,
            _test_unknown_preset_setting_fails,
            _test_invalid_script_export_mode_fails,
            _test_preset_setting_as_export_option_fails,
        ],
    )
