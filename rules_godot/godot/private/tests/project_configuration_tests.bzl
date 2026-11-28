"""
How a project's settings and main scene reach the configuration of each purpose: imports'
on the project, the others on the view of an operation over it.
"""

load("@bazel_skylib//rules:common_settings.bzl", "bool_flag", "int_flag", "string_flag", "string_list_flag")
load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:util.bzl", "TestingAspectInfo")
load("//godot:defs.bzl", "godot_addon", "godot_pack", "godot_project", "godot_resources", "godot_test")
load("//godot/private:providers.bzl", "GodotProjectInfo")
load("//godot/private:view.bzl", "GodotViewInfo")
load(":expected_failures.bzl", "failure_test")
load(":manifests.bzl", "manifest_content")
load(":pack_actions.bzl", "PackActionsInfo", "pack_actions", "pack_manifest")
load(":views.bzl", "run_view")

visibility("private")

_FIXTURE = "//godot/private/tests/fixtures/import_context"
_PROJECT_FILE = _FIXTURE + ":project.godot"
_CONFIGURED = [_FIXTURE + ":configured_check", _FIXTURE + ":configured_resources"]

# The configuration manifest of each purpose, by the target that writes it and the suffix
# of its file name.
_CONFIGURATIONS = [
    ("view", ".config.json", "runtime"),
    ("view", ".editor.config.json", "editor"),
    ("view", ".export.config.json", "export"),
    ("project", ".import.config.json", "import"),
]

# Imports run under the project's settings like every other purpose.
def _test_settings_reach_every_configuration(name):
    godot_project(
        name = name + "_project",
        project_file = _PROJECT_FILE,
        settings = {"display/window/size/viewport_width": "640"},
        tags = ["manual"],
    )
    analysis_test(
        name = name,
        targets = {
            "project": name + "_project",
            "view": run_view(name + "_run", name + "_project", [_FIXTURE + ":configured_check"]),
        },
        impl = _settings_reach_every_configuration,
    )

def _settings_reach_every_configuration(env, targets):
    for subject, suffix, purpose in _CONFIGURATIONS:
        manifest = manifest_content(getattr(targets, subject), suffix)
        env.expect.where(manifest = suffix).that_str(manifest["purpose"]).equals(purpose)
        env.expect.where(manifest = suffix).that_dict(manifest["settings"]).contains_exactly({
            "display/window/size/viewport_width": "640",
        })

# Imports and exports read the VRAM texture formats the ruleset fixes, so every execution
# platform imports the same variants and every export platform finds its own; the runtime
# and the editor views keep the project's.
def _test_imports_and_exports_pin_the_vram_formats(name):
    analysis_test(
        name = name,
        targets = {
            "project": _FIXTURE,
            "view": run_view(name + "_run", _FIXTURE, _CONFIGURED),
        },
        impl = _imports_and_exports_pin_the_vram_formats,
    )

def _imports_and_exports_pin_the_vram_formats(env, targets):
    for subject, suffix, purpose in _CONFIGURATIONS:
        pinned = manifest_content(getattr(targets, subject), suffix).get("pinned_settings", {})
        env.expect.where(manifest = suffix).that_dict(pinned).contains_exactly({
            "rendering/textures/vram_compression/import_etc2_astc": "true",
            "rendering/textures/vram_compression/import_s3tc_bptc": "true",
        } if purpose in ["import", "export"] else {})

def _pinned_setting_failure_test(name, attr, setting):
    godot_project(
        name = name + "_project",
        project_file = _PROJECT_FILE,
        tags = ["manual"],
        **{attr: {setting: "false"}}
    )
    failure_test(
        name,
        name + "_project",
        "*rules_godot imports every VRAM-compressed texture in both S3TC/BPTC and ETC2/ASTC*remove the setting %s" % setting,
    )

def _test_project_setting_against_a_pinned_format_fails(name):
    _pinned_setting_failure_test(name, "settings", "rendering/textures/vram_compression/import_s3tc_bptc")

def _test_override_against_a_pinned_format_fails(name):
    _pinned_setting_failure_test(name, "setting_overrides", "rendering/textures/vram_compression/import_etc2_astc.mobile")

# The main scene takes its res:// form; imports never start it.
def _test_main_scene_reaches_runtime_but_not_import_configuration(name):
    analysis_test(
        name = name,
        targets = {
            "project": _FIXTURE,
            "view": run_view(name + "_run", _FIXTURE, _CONFIGURED),
        },
        impl = _main_scene_reaches_runtime_but_not_import_configuration,
    )

def _main_scene_reaches_runtime_but_not_import_configuration(env, targets):
    for subject, suffix, purpose in _CONFIGURATIONS:
        env.expect.where(manifest = suffix).that_str(
            manifest_content(getattr(targets, subject), suffix)["main_scene"],
        ).equals("" if purpose == "import" else "res://main/main.tscn")

# A source run starts the game, so the main scene its project names must be among its
# resources.
def _test_undeclared_main_scene_fails(name):
    godot_project(
        name = name + "_project",
        main_scene = "absent.tscn",
        project_file = _PROJECT_FILE,
        tags = ["manual"],
    )
    run_view(name + "_run", name + "_project", [_FIXTURE + ":configured_check"])
    failure_test(name, name + "_run", "Main scene res://absent.tscn is not a declared project member")

def _test_main_scene_naming_a_directory_fails(name):
    godot_project(
        name = name + "_project",
        main_scene = "res://main/",
        project_file = _PROJECT_FILE,
        tags = ["manual"],
    )
    run_view(name + "_run", name + "_project", [_FIXTURE + ":configured_check"])
    failure_test(name, name + "_run", "Main scene res://main is not a declared project member; it names a directory")

def _absent_entries_project(name):
    godot_project(
        name = name + "_project",
        autoloads = {"Missing": "*res://absent.gd"},
        main_scene = "absent.tscn",
        project_file = _PROJECT_FILE,
        tags = ["manual"],
    )
    return name + "_project"

# A pack without required packs may start the game, so the main scene its project names
# must be among its resources.
def _test_pack_without_required_packs_needs_main_scene(name):
    godot_pack(
        name = name + "_pack",
        project = _absent_entries_project(name),
        tags = ["manual"],
        deps = [_FIXTURE + ":configured_check"],
    )
    failure_test(name, name + "_pack", "Autoload Missing res://absent.gd is not a declared project member")

# Every other operation leaves out the autoloads and main scene its resources lack, and its
# view names them.
def _test_test_leaves_out_absent_entries(name):
    godot_test(
        name = name + "_test",
        project = _absent_entries_project(name),
        tags = ["manual"],
        deps = [_FIXTURE + ":configured_check"],
    )
    analysis_test(name = name, target = name + "_test.view", impl = _test_leaves_out_absent_entries)

def _test_leaves_out_absent_entries(env, target):
    env.expect.that_collection(target[GodotViewInfo].missing_entries).contains_exactly([
        ("autoload/Missing", "res://absent.gd"),
        ("application/run/main_scene", "res://absent.tscn"),
    ]).in_order()

# A source run starts the game, so the autoload scripts its project names must be among its
# resources.
def _test_source_run_without_autoload_script_fails(name):
    run_view(name + "_run", _absent_entries_project(name), [_FIXTURE + ":configured_check"])
    failure_test(name, name + "_run", "Autoload Missing res://absent.gd is not a declared project member")

# A pack with required packs starts no game, so it leaves out the entries its resources
# lack, as a test does.
def _test_pack_with_required_packs_leaves_out_absent_entries(name):
    godot_project(
        name = name + "_base_project",
        project_file = _PROJECT_FILE,
        tags = ["manual"],
    )
    godot_pack(
        name = name + "_base",
        project = name + "_base_project",
        tags = ["manual"],
        deps = [_FIXTURE + ":configured_resources"],
    )
    godot_pack(
        name = name + "_pack",
        project = _absent_entries_project(name),
        required_packs = [name + "_base"],
        tags = ["manual"],
        deps = [_FIXTURE + ":configured_check"],
    )
    analysis_test(
        name = name,
        target = name + "_pack",
        impl = _pack_with_required_packs_leaves_out_absent_entries,
        extra_target_under_test_aspects = [pack_actions],
    )

def _pack_with_required_packs_leaves_out_absent_entries(env, target):
    env.expect.that_collection(target[PackActionsInfo].view.missing_entries).contains_exactly([
        ("autoload/Missing", "res://absent.gd"),
        ("application/run/main_scene", "res://absent.tscn"),
    ]).in_order()

def _content_settings_project(name, settings):
    godot_project(
        name = name + "_project",
        project_file = _PROJECT_FILE,
        settings = settings,
        tags = ["manual"],
    )
    return name + "_project"

# FR-005: a content-bound setting reaches an operation's configurations only when its
# selection holds every file the setting names; a uid:// reference, which analysis cannot
# resolve, always does. Translation remaps name their sources and remapped files, a shader
# global its sampler's file, and an add-on's own key the paths its declaration names. The
# view names the settings it left out.
def _test_content_settings_need_their_files_in_the_selection(name):
    project = _content_settings_project(name, {
        "audio/buses/default_bus_layout": '"uid://b4x1"',
        "gui/theme/custom": '"res://ui/theme.tres"',
        "internationalization/locale/translations": 'PackedStringArray("res://ui/theme.tres", "res://ui/de.translation")',
        "internationalization/locale/translation_remaps": '{"res://ui/theme.tres": PackedStringArray("res://ui/theme_de.tres:de")}',
        "shader_globals/noise": '{"type": "sampler2D", "value": "res://ui/noise.png"}',
        "shader_globals/tint": '{"type": "sampler2D", "value": "res://ui/theme.tres"}',
        "addon_own/data": '"res://ui/data.tres"',
        "addon_own/level": "3",
    })
    godot_resources(
        name = name + "_theme",
        resource_paths = {_FIXTURE + ":main/main.tscn": "ui/theme.tres"},
        tags = ["manual"],
    )
    godot_test(
        name = name + "_test",
        project = project,
        tags = ["manual"],
        deps = [
            name + "_theme",
            _FIXTURE + ":configured_check",
        ],
    )
    analysis_test(name = name, target = name + "_test.view", impl = _content_settings_need_their_files_in_the_selection)

def _content_settings_need_their_files_in_the_selection(env, target):
    view = target[GodotViewInfo]
    env.expect.that_collection(view.missing_entries).contains_exactly([
        ("addon_own/data", "res://ui/data.tres"),
        ("internationalization/locale/translation_remaps", "res://ui/theme_de.tres"),
        ("internationalization/locale/translations", "res://ui/de.translation"),
        ("shader_globals/noise", "res://ui/noise.png"),
    ])
    kept = [
        "addon_own/level",
        "audio/buses/default_bus_layout",
        "gui/theme/custom",
        "shader_globals/tint",
    ]
    env.expect.that_collection(sorted(view.composed_settings)).contains_exactly(kept).in_order()
    for suffix in [".config.json", ".editor.config.json", ".export.config.json"]:
        env.expect.where(manifest = suffix).that_collection(
            sorted(manifest_content(target, suffix)["settings"]),
        ).contains_exactly(kept).in_order()

    # The shell-assets probe's construction drops the game's file settings itself
    # (project_config_test.py).
    shell = manifest_content(target, ".shell.config.json")
    env.expect.where(manifest = ".shell.config.json").that_collection(sorted(shell["settings"])).contains_exactly(kept).in_order()
    env.expect.where(manifest = ".shell.config.json").that_bool(shell["context_only"]).equals(True)

# A pack without required packs fails for a content-bound setting whose file its
# resources lack.
def _test_pack_without_required_packs_needs_content_setting_files(name):
    godot_pack(
        name = name + "_pack",
        project = _content_settings_project(name, {"gui/theme/custom": '"res://ui/theme.tres"'}),
        tags = ["manual"],
        deps = [_FIXTURE + ":configured_check"],
    )
    failure_test(name, name + "_pack", "Setting gui/theme/custom res://ui/theme.tres is not a declared project member")

# An add-on and, with project_settings, the project contribute overrides of a feature,
# debug_tools, whose files the selection lacks; with_feature makes debug_tools one of the
# project's custom features.
def _feature_overrides_project(name, project_settings = {"application/run/main_scene.debug_tools": '"res://debug/main.tscn"'}, with_feature = False):
    godot_addon(
        name = name + "_addon",
        directory = "addons/debug_tools",
        settings = {"gui/theme/custom.debug_tools": '"res://debug/theme.tres"'},
        tags = ["manual"],
    )
    string_flag(
        name = name + "_variant",
        build_setting_default = "debug_tools" if with_feature else "",
    )
    godot_project(
        name = name + "_project",
        project_file = _PROJECT_FILE,
        settings = project_settings,
        custom_features = [name + "_variant"],
        tags = ["manual"],
        deps = [name + "_addon"],
    )
    return name + "_project"

# A pack without required packs needs the files of the overrides its export can have, as
# for the authored project.godot (G6): one of a custom feature the project's settings do
# not give never applies, so the pack leaves it out instead of failing.
def _test_pack_needs_no_file_of_an_impossible_override(name):
    godot_pack(
        name = name + "_pack",
        project = _feature_overrides_project(name),
        tags = ["manual"],
        deps = [_FIXTURE + ":configured_check"],
    )
    analysis_test(
        name = name,
        target = name + "_pack",
        impl = _pack_needs_no_file_of_an_impossible_override,
        extra_target_under_test_aspects = [pack_actions],
    )

def _pack_needs_no_file_of_an_impossible_override(env, target):
    view = target[PackActionsInfo].view
    env.expect.that_collection(view.missing_entries).contains_exactly([
        ("application/run/main_scene.debug_tools", "res://debug/main.tscn"),
        ("gui/theme/custom.debug_tools", "res://debug/theme.tres"),
    ]).in_order()
    for key in ["application/run/main_scene.debug_tools", "gui/theme/custom.debug_tools"]:
        env.expect.where(key = key).that_collection(view.composed_settings.keys()).not_contains(key)

# The add-on's override fails a pack whose project gives its custom feature.
def _test_pack_needs_the_file_of_a_possible_override(name):
    godot_pack(
        name = name + "_pack",
        project = _feature_overrides_project(name, project_settings = {}, with_feature = True),
        tags = ["manual"],
        deps = [_FIXTURE + ":configured_check"],
    )
    failure_test(name, name + "_pack", "Setting gui/theme/custom.debug_tools res://debug/theme.tres is not a declared project member")

# A source run has the project's custom features as a pack does, so it needs the files of
# exactly the overrides that can apply to it.
def _test_source_run_needs_the_file_of_a_possible_override(name):
    run_view(name + "_run", _feature_overrides_project(name, with_feature = True), [_FIXTURE + ":configured_check"])
    failure_test(name, name + "_run", "Setting application/run/main_scene.debug_tools res://debug/main.tscn is not a declared project member")

def _test_source_run_needs_no_file_of_an_impossible_override(name):
    run_view(name + "_run", _feature_overrides_project(name), [_FIXTURE + ":configured_check"])
    analysis_test(
        name = name,
        target = name + "_run",
        impl = _analyzes,
    )

def _analyzes(_env, _target):
    """The claim is that analysis succeeds."""
    pass

# The project's custom-feature settings give its custom features: a string setting its
# value, none when empty; a boolean setting its own name when true.
def _custom_features_project(name):
    string_flag(name = name + "_channel", build_setting_default = "production")
    string_flag(name = name + "_unset", build_setting_default = "")
    bool_flag(name = name + "_tools", build_setting_default = False)
    bool_flag(name = name + "_automation", build_setting_default = True)
    godot_project(
        name = name + "_project",
        project_file = _PROJECT_FILE,
        custom_features = [
            name + "_channel",
            name + "_unset",
            name + "_tools",
            name + "_automation",
        ],
        tags = ["manual"],
    )
    return name + "_project"

def _test_custom_features_follow_their_settings(name):
    project = _custom_features_project(name)
    godot_pack(
        name = name + "_pack",
        project = project,
        tags = ["manual"],
        deps = [_FIXTURE + ":configured_check"],
    )
    analysis_test(
        name = name,
        targets = {
            "project": project,
            "run": run_view(name + "_run", project, [_FIXTURE + ":configured_check"]).removesuffix(".view"),
            "pack": name + "_pack",
        },
        impl = _custom_features_follow_their_settings,
        config_settings = {
            str(Label("//godot/private/tests:" + name + "_tools")): True,
            str(Label("//godot/private/tests:" + name + "_channel")): "internal",
        },
        extra_target_under_test_aspects = [pack_actions],
    )

def _custom_features_follow_their_settings(env, targets):
    prefix = targets.project.label.name.removesuffix("_project")
    expected = sorted(["internal", prefix + "_automation", prefix + "_tools"])
    env.expect.that_collection(targets.project[GodotProjectInfo].custom_features).contains_exactly(expected).in_order()

    # A source run starts with them; a pack exports with them before the derived tags.
    run = manifest_content(targets.run, ".run.json")["project"]
    env.expect.that_collection(run["custom_features"]).contains_exactly(expected).in_order()
    env.expect.that_collection(pack_manifest(targets.pack)["features"]).contains_exactly(expected).in_order()

def _custom_feature_failure_test(name, value, message):
    string_flag(name = name + "_feature", build_setting_default = value)
    godot_project(
        name = name + "_project",
        project_file = _PROJECT_FILE,
        custom_features = [name + "_feature"],
        tags = ["manual"],
    )
    failure_test(name, name + "_project", message)

def _test_custom_feature_with_a_dot_fails(name):
    _custom_feature_failure_test(name, "debug.tools", "*custom feature \"debug.tools\" may hold only letters, digits, _ and -")

def _test_reserved_custom_feature_fails(name):
    _custom_feature_failure_test(name, "arm64", "*custom feature arm64 is a feature tag Godot or the configuration sets")

# An autoload name is an identifier: a letter or _ first, then letters, digits and _.
def _test_autoload_name_that_is_no_identifier_fails(name):
    projects = []
    for index, autoload in enumerate(["", "1Menu", "Main-Menu"]):
        godot_project(
            name = "%s_project%d" % (name, index),
            project_file = _PROJECT_FILE,
            autoloads = {autoload: "res://menu.gd"},
            tags = ["manual"],
        )
        projects.append("%s_project%d" % (name, index))
    failure_test(name, projects, "*Invalid Godot autoload name: *")

# A pack's own settings replace exported keys after its view checked its members, so they
# name no main scene, also not one of a feature; add-ons and the project may.
def _test_pack_settings_name_no_main_scene_of_a_feature(name):
    godot_project(
        name = name + "_project",
        project_file = _PROJECT_FILE,
        tags = ["manual"],
    )
    godot_pack(
        name = name + "_pack",
        project = name + "_project",
        settings = {"application/run/main_scene.mobile": '"res://absent.tscn"'},
        tags = ["manual"],
        deps = [_FIXTURE + ":configured_check"],
    )
    failure_test(
        name,
        name + "_pack",
        "*Use autoloads, main_scene and the editor parts of add-ons instead of the setting application/run/main_scene.mobile",
    )

_FLAG_VALUE = "flag-value-0f1c"

def _flag_project(name):
    string_flag(name = name + "_commit", build_setting_default = "")
    int_flag(name = name + "_build", build_setting_default = 0)
    bool_flag(name = name + "_beta", build_setting_default = False)
    godot_project(
        name = name + "_project",
        project_file = _PROJECT_FILE,
        settings_from_flags = {
            name + "_commit": "application/config/commit",
            name + "_build": "application/config/build_number",
            name + "_beta": "application/config/beta.mobile",
        },
        tags = ["manual"],
    )
    return name + "_project"

# A flag's value reaches the configuration a pack exports and the staged project of a
# source run, and no other action: imports, initialization, views and the shell probe
# keep their action keys across values, so a new value reruns only exports.
def _test_settings_from_flags_reach_only_exports(name):
    project = _flag_project(name)
    godot_pack(
        name = name + "_pack",
        project = project,
        tags = ["manual"],
        deps = [_FIXTURE + ":configured_check"],
    )
    analysis_test(
        name = name,
        targets = {
            "project": project,
            "run": run_view(name + "_run", project, [_FIXTURE + ":configured_check"]).removesuffix(".view"),
            "run_view": name + "_run.view",
            "pack": name + "_pack",
        },
        impl = _settings_from_flags_reach_only_exports,
        config_settings = {
            str(Label("//godot/private/tests:" + name + "_commit")): _FLAG_VALUE,
            str(Label("//godot/private/tests:" + name + "_build")): 57,
            str(Label("//godot/private/tests:" + name + "_beta")): True,
        },
        extra_target_under_test_aspects = [pack_actions],
    )

def _carrying_flag_value(actions):
    """The basenames of the first outputs of the actions whose command or content holds the value."""
    return [
        action.outputs.to_list()[0].basename
        for action in actions
        if _FLAG_VALUE in (action.content if action.mnemonic == "FileWrite" else " ".join(action.argv or []))
    ]

def _settings_from_flags_reach_only_exports(env, targets):
    expected = {
        "application/config/commit": json.encode(_FLAG_VALUE),
        "application/config/build_number": "57",
        "application/config/beta.mobile": "true",
    }
    env.expect.that_dict(targets.project[GodotProjectInfo].flag_settings).contains_exactly(expected)

    # The project checks the authored file for overrides of these settings once.
    checks = [file.basename for file in targets.project[OutputGroupInfo]._validation.to_list()]
    env.expect.that_collection(checks).contains_exactly([targets.project.label.name + ".flag_overrides.checked"])
    env.expect.that_dict(manifest_content(targets.run, ".run.json")["project"]["flag_settings"]).contains_exactly(expected)

    env.expect.where(target = "pack").that_collection(_carrying_flag_value(targets.pack[PackActionsInfo].actions)).contains_exactly([
        targets.pack.label.name + ".export.pack.config.json",
    ])

    # The run's view is the view a pack declares, without its program entry.
    for subject in ["project", "run_view"]:
        actions = getattr(targets, subject)[TestingAspectInfo].actions
        env.expect.where(target = subject).that_collection(_carrying_flag_value(actions)).contains_exactly([])

def _flag_failure_test(name, message, flags):
    godot_project(
        name = name + "_project",
        project_file = _PROJECT_FILE,
        settings_from_flags = flags,
        tags = ["manual"],
    )
    failure_test(name, name + "_project", message)

def _test_two_flags_for_one_setting_fail(name):
    string_flag(name = name + "_a", build_setting_default = "")
    string_flag(name = name + "_b", build_setting_default = "")
    _flag_failure_test(name, "*_a and *_b both set the setting application/config/commit", {
        name + "_a": "application/config/commit",
        name + "_b": "application/config/commit",
    })

def _test_list_flag_fails(name):
    string_list_flag(name = name + "_list", build_setting_default = [])
    _flag_failure_test(name, "*_list: settings_from_flags takes string, int and bool build settings, not list", {
        name + "_list": "application/config/commit",
    })

def _test_reserved_flag_setting_fails(name):
    string_flag(name = name + "_scene", build_setting_default = "")
    _flag_failure_test(name, "*Use autoloads, main_scene and the editor parts of add-ons instead of the setting application/run/main_scene", {
        name + "_scene": "application/run/main_scene",
    })

# A project setting of the same key would conflict with the flag's value; an override
# of it would hide that value where its tag applies.
def _test_project_override_of_flag_setting_fails(name):
    string_flag(name = name + "_commit", build_setting_default = "")
    godot_project(
        name = name + "_project",
        project_file = _PROJECT_FILE,
        settings = {"application/config/commit.mobile": '"x"'},
        settings_from_flags = {name + "_commit": "application/config/commit"},
        tags = ["manual"],
    )
    failure_test(
        name,
        run_view(name + "_run", name + "_project", [_FIXTURE + ":configured_check"]),
        "*sets application/config/commit.mobile, which conflicts with application/config/commit from settings_from_flags",
    )

# An add-on's contribution conflicts like the project's own.
def _test_addon_setting_of_flag_setting_fails(name):
    string_flag(name = name + "_commit", build_setting_default = "")
    godot_addon(
        name = name + "_addon",
        directory = "addons/commit",
        settings = {"application/config/commit": '"addon"'},
        tags = ["manual"],
    )
    godot_project(
        name = name + "_project",
        project_file = _PROJECT_FILE,
        settings_from_flags = {name + "_commit": "application/config/commit"},
        tags = ["manual"],
    )
    failure_test(
        name,
        run_view(name + "_run", name + "_project", [_FIXTURE + ":configured_check", name + "_addon"]),
        "*_addon sets application/config/commit, which conflicts with application/config/commit from settings_from_flags",
    )

def project_configuration_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_main_scene_reaches_runtime_but_not_import_configuration,
            _test_settings_reach_every_configuration,
            _test_imports_and_exports_pin_the_vram_formats,
            _test_project_setting_against_a_pinned_format_fails,
            _test_override_against_a_pinned_format_fails,
            _test_undeclared_main_scene_fails,
            _test_main_scene_naming_a_directory_fails,
            _test_pack_without_required_packs_needs_main_scene,
            _test_pack_settings_name_no_main_scene_of_a_feature,
            _test_test_leaves_out_absent_entries,
            _test_source_run_without_autoload_script_fails,
            _test_pack_with_required_packs_leaves_out_absent_entries,
            _test_content_settings_need_their_files_in_the_selection,
            _test_pack_without_required_packs_needs_content_setting_files,
            _test_pack_needs_no_file_of_an_impossible_override,
            _test_pack_needs_the_file_of_a_possible_override,
            _test_source_run_needs_the_file_of_a_possible_override,
            _test_source_run_needs_no_file_of_an_impossible_override,
            _test_custom_features_follow_their_settings,
            _test_custom_feature_with_a_dot_fails,
            _test_reserved_custom_feature_fails,
            _test_autoload_name_that_is_no_identifier_fails,
            _test_settings_from_flags_reach_only_exports,
            _test_two_flags_for_one_setting_fail,
            _test_list_flag_fails,
            _test_reserved_flag_setting_fails,
            _test_project_override_of_flag_setting_fails,
            _test_addon_setting_of_flag_setting_fails,
        ],
    )
