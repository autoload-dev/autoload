"""
What an operation contains of the add-ons its selection uses and its project names, which
imports the add-ons' parts declare, and the add-on declarations analysis rejects.

The fixture's content uses `inventory`, which needs `utility` and brings an extension; the
project names the editor-only `tool`, whose editor part no content uses.
"""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:util.bzl", "TestingAspectInfo")
load("//godot:defs.bzl", "godot_addon", "godot_pack", "godot_project", "godot_resources", "godot_test")
load("//godot:providers.bzl", "GodotPackInfo")
load("//godot/private:providers.bzl", "GodotAddonInfo", "GodotProjectInfo")
load("//godot/private:view.bzl", "GodotViewInfo")
load(":expected_failures.bzl", "failure_test")
load(":manifests.bzl", "manifest_content")
load(":views.bzl", "run_view")

visibility("private")

_FIXTURE = "//godot/private/tests/fixtures/project_with_addons"
_PROJECT = _FIXTURE
_CONTEXT = str(Label("//godot/private:project_setting"))

def _label(name):
    return str(Label(_FIXTURE + ":" + name))

# US3: the used add-on's runtime part, autoload, setting and extension, the add-on it
# needs and the add-on the project names reach the operation, in dependency order.
def _test_used_and_named_addons_reach_the_operation(name):
    analysis_test(
        name = name,
        target = run_view(name + "_run", _PROJECT, [_FIXTURE + ":main"]),
        impl = _used_and_named_addons_reach_the_operation,
    )

def _used_and_named_addons_reach_the_operation(env, target):
    view = target[GodotViewInfo]
    env.expect.where(field = "addons").that_collection(
        [str(addon.label) for addon in view.addons],
    ).contains_exactly([_label("utility"), _label("inventory"), _label("tool")]).in_order()
    members = env.expect.where(field = "member_resource_paths").that_collection(sorted(view.member_resource_paths))
    members.contains_at_least([
        "addons/inventory/icon.svg",
        "addons/inventory/inventory.gd",
        "addons/utility/utility.gd",
        "main/main.gd",
    ])

    # The editor part is a tool, never a member.
    members.not_contains("addons/tool/plugin.gd")
    configuration = view.export_configuration
    env.expect.where(field = "autoloads").that_collection(configuration["autoloads"].keys()).contains_exactly(
        ["Utility", "Inventory"],
    ).in_order()
    env.expect.where(field = "settings").that_dict(configuration["settings"]).contains_exactly({
        "inventory/slots": "12",
        "tool/enabled": "true",
    })
    env.expect.where(field = "composed_settings").that_dict(view.composed_settings).contains_exactly({
        "autoload/Inventory": _label("inventory"),
        "autoload/Utility": _label("utility"),
        "inventory/slots": _label("inventory"),
        "tool/enabled": _label("tool"),
    })

    # The export enables no add-on's plugin (D29); only editor views load the editor part.
    env.expect.where(field = "importer_plugins").that_collection(configuration["importer_plugins"]).contains_exactly([])
    env.expect.where(field = "export_extensions").that_collection(
        [extension.descriptor_path for extension in view.export_extensions],
    ).contains_exactly(["addons/inventory/inventory.gdextension"])
    env.expect.where(field = "editor_resource_paths").that_collection(
        sorted(view.editor_resource_paths),
    ).contains_at_least(["addons/inventory/inventory.gd", "addons/tool/plugin.cfg", "addons/tool/plugin.gd"])

# US3 AS3: an operation whose selection uses no add-on contains the named one only.
def _test_named_addon_is_in_every_operation(name):
    analysis_test(
        name = name,
        target = run_view(name + "_run", _PROJECT, [_FIXTURE + ":other"]),
        impl = _named_addon_is_in_every_operation,
    )

def _named_addon_is_in_every_operation(env, target):
    view = target[GodotViewInfo]
    env.expect.that_collection([str(addon.label) for addon in view.addons]).contains_exactly([_label("tool")])
    env.expect.where(field = "autoloads").that_dict(view.export_configuration["autoloads"]).contains_exactly({})

# FR-020, D2: under the project's context, a named add-on imports its parts like a used one;
# the project imports none of them.
def _test_named_addons_import_their_parts(name):
    analysis_test(
        name = name,
        targets = {
            "inventory": _FIXTURE + ":inventory",
            "project": _PROJECT,
            "tool": _FIXTURE + ":tool",
        },
        impl = _named_addons_import_their_parts,
        config_settings = {_CONTEXT: str(Label(_PROJECT))},
    )

def _named_addons_import_their_parts(env, targets):
    project = targets.project[GodotProjectInfo]
    env.expect.where(field = "named_addons").that_collection(
        [str(addon.label) for addon in project.named_addons.to_list()],
    ).contains_exactly([_label("tool")])
    tool = targets.tool[GodotAddonInfo]
    env.expect.where(addon = "tool").that_collection(tool.editor_files.imports.to_list()).has_size(1)
    inventory = targets.inventory[GodotAddonInfo]

    # Its own import result and that of utility, which it needs.
    env.expect.where(addon = "inventory").that_collection(inventory.runtime_files.imports.to_list()).has_size(2)

# FR-020: a named add-on's own .md file imports with the add-on's own importer, staged and
# enabled in its runtime part's import, which its editor part imports after; the editor part
# has no such file and stages no importer.
_IMPORTER_FIXTURE = "//godot/private/tests/fixtures/project_with_importer"

def _test_named_addon_imports_its_own_files_with_its_importer(name):
    analysis_test(
        name = name,
        target = _IMPORTER_FIXTURE + ":self_importing",
        impl = _named_addon_imports_its_own_files_with_its_importer,
        config_settings = {_CONTEXT: str(Label(_IMPORTER_FIXTURE + ":self_importing_project"))},
    )

def _named_addon_imports_its_own_files_with_its_importer(env, target):
    runtime = manifest_content(target, ".runtime.import.json")
    env.expect.where(part = "runtime", field = "outputs").that_collection(runtime["outputs"]).contains_exactly(["addons/self_importing/own.md"])
    env.expect.where(part = "runtime", field = "editor_plugins").that_collection(runtime["editor_plugins"]).contains_exactly(
        ["res://addons/self_importing/plugin.cfg"],
    )
    env.expect.where(part = "runtime", field = "tools").that_collection(runtime["tools"]).contains_exactly([
        "addons/self_importing/icon.svg",
        "addons/self_importing/importer.gd",
        "addons/self_importing/plugin.cfg",
        "addons/self_importing/plugin.gd",
    ])
    env.expect.where(part = "editor").that_collection(manifest_content(target, ".editor.import.json").keys()).contains_none_of(["editor_plugins", "tools"])
    addon = target[GodotAddonInfo]
    env.expect.where(part = "editor", field = "unit deps").that_collection(addon.editor_files.units[0]["deps"]).contains_exactly(
        [str(Label(_IMPORTER_FIXTURE + ":self_importing"))],
    )

# FR-024: the runtime part imports after the runtime parts of the add-ons it needs, staging
# their assets but not their scripts, as resources import after their dependencies.
def _test_runtime_part_imports_after_needed_runtime_parts(name):
    analysis_test(
        name = name,
        targets = {
            "inventory": _FIXTURE + ":inventory",
            "utility": _FIXTURE + ":utility",
        },
        impl = _runtime_part_imports_after_needed_runtime_parts,
        config_settings = {_CONTEXT: str(Label(_PROJECT))},
    )

def _runtime_part_imports_after_needed_runtime_parts(env, targets):
    written = {
        action.outputs.to_list()[0]: action.content
        for target in [targets.inventory, targets.utility]
        for action in target[TestingAspectInfo].actions
        if action.mnemonic == "FileWrite"
    }
    inventory = targets.inventory[GodotAddonInfo].runtime_files
    utility = targets.utility[GodotAddonInfo].runtime_files
    staged = {}
    for manifest in inventory.resource_path_manifests.to_list():
        staged.update(json.decode(written[manifest]))
    env.expect.where(field = "staged resource paths").that_collection(sorted(staged)).contains_exactly([
        "addons/inventory/icon.svg",
        "addons/utility/utility_icon.svg",
    ])
    env.expect.where(addon = "utility", field = "imports").that_collection(utility.imports.to_list()).has_size(1)
    env.expect.where(addon = "inventory", field = "imports").that_collection(
        inventory.imports.to_list(),
    ).contains_at_least(utility.imports.to_list())
    env.expect.where(addon = "inventory", field = "unit deps").that_collection(
        inventory.units[0]["deps"],
    ).contains_exactly([_label("utility")])

# Outside every operation an add-on imports nothing, like resources.
def _test_addon_outside_operations_imports_nothing(name):
    analysis_test(
        name = name,
        target = _FIXTURE + ":inventory",
        impl = _addon_outside_operations_imports_nothing,
    )

def _addon_outside_operations_imports_nothing(env, target):
    addon = target[GodotAddonInfo]
    env.expect.that_collection(addon.runtime_files.imports.to_list() + addon.editor_files.imports.to_list()).has_size(0)

def _versioned_inventory(name, index):
    """An add-on whose autoload Inventory names its runtime part's script."""
    godot_addon(
        name = name,
        srcs = [_FIXTURE + ":inventory/inventory.gd"],
        autoloads = {"Inventory": "*res://addons/inventory_v%s/inventory.gd" % index},
        directory = "addons/inventory_v" + index,
        strip_prefix = "inventory",
        tags = ["manual"],
    )

# FR-021: the same autoload from two add-ons with different values needs an override.
def _test_conflicting_autoloads_need_an_override(name):
    for index in ["1", "2"]:
        _versioned_inventory(name + "_addon" + index, index)
    godot_resources(
        name = name + "_resources",
        tags = ["manual"],
        deps = [name + "_addon1", name + "_addon2"],
    )
    failure_test(
        name,
        run_view(name + "_run", _FIXTURE, [name + "_resources"]),
        'Conflicting Godot configuration "Inventory"*declare an explicit override',
    )

def _test_project_override_resolves_conflicting_autoloads(name):
    for index in ["1", "2"]:
        _versioned_inventory(name + "_addon" + index, index)
    godot_project(
        name = name + "_project",
        autoload_overrides = {"Inventory": "*res://addons/inventory/inventory.gd"},
        project_file = _FIXTURE + ":project.godot",
        tags = ["manual"],
    )
    analysis_test(
        name = name,
        target = run_view(name + "_run", name + "_project", [name + "_addon1", name + "_addon2", _FIXTURE + ":main"]),
        impl = _project_override_resolves_conflicting_autoloads,
    )

def _project_override_resolves_conflicting_autoloads(env, target):
    env.expect.that_str(target[GodotViewInfo].export_configuration["autoloads"]["Inventory"]).equals(
        "*res://addons/inventory/inventory.gd",
    )

# FR-013: platform libraries belong to an add-on, never to resources.
def _test_platform_library_on_resources_fails(name):
    cc_library(name = name + "_library", tags = ["manual"])
    godot_resources(
        name = name + "_resources",
        tags = ["manual"],
        deps = [name + "_library"],
    )
    failure_test(name, name + "_resources", "*_library in deps is no godot_resources, godot_addon or extension; declare it on a godot_addon*")

# FR-012: two add-ons of one operation may not claim overlapping directories, also when a
# sibling's directory sorts between theirs.
def _test_overlapping_addon_directories_fail(name):
    godot_addon(name = name + "_outer", directory = "addons/shared", tags = ["manual"])
    godot_addon(name = name + "_sibling", directory = "addons/shared-extra", tags = ["manual"])
    godot_addon(name = name + "_inner", directory = "addons/shared/inner", tags = ["manual"])
    failure_test(
        name,
        run_view(name + "_run", _PROJECT, [name + "_inner", name + "_outer", name + "_sibling"]),
        "Add-ons * (res://addons/shared*/) and * (res://addons/shared*/) have overlapping directories",
    )

# FR-023: a test-only add-on reaches only test-only operations. Bazel's testonly check is the
# diagnostic: the first target of a production operation's chain that reaches the add-on
# fails, naming its test-only dependency.
def _test_production_operation_reaching_a_test_only_addon_fails(name):
    godot_addon(name = name + "_suite_tool", directory = "addons/suite_tool", testonly = True, tags = ["manual"])
    godot_resources(name = name + "_suites", testonly = True, tags = ["manual"], deps = [name + "_suite_tool"])
    godot_pack(name = name + "_pack", project = _PROJECT, testonly = False, tags = ["manual"], deps = [name + "_suites"])
    failure_test(
        name,
        name + "_pack",
        "*non-test target '*_pack.view' depends on testonly target '*_suites' and doesn't have testonly attribute set*",
    )

# US8 AS2: an add-on declared from a release directory with prebuilt libraries lists its
# descriptor in packs and delivers the library of the configured operating system.
def _test_vendored_release_lists_its_descriptor_and_delivers_its_library(name):
    analysis_test(
        name = name,
        targets = {
            "pack": "//godot/private/tests/fixtures/vendored_release:pack",
            "addon": "//godot/private/tests/fixtures/vendored_release:sentry",
        },
        impl = _vendored_release_lists_its_descriptor_and_delivers_its_library,
    )

def _vendored_release_lists_its_descriptor_and_delivers_its_library(env, targets):
    addon = targets.addon[GodotAddonInfo]
    env.expect.where(field = "runtime part").that_collection(addon.runtime_files.member_resource_paths.keys()).contains_exactly(
        ["addons/sentry/sentry_logger.gd"],
    )
    extensions = targets.pack[GodotPackInfo].project.runtime_extensions
    env.expect.where(field = "runtime extensions").that_collection(
        [extension.descriptor_path for extension in extensions],
    ).contains_exactly(["addons/sentry/sentry.gdextension"])
    env.expect.where(field = "library").that_collection(
        [path for extension in extensions for path in extension.runtime_resource_paths if "/bin/" in path],
    ).has_size(1)

# FR-032, #134: a directory a setting names resolves against each operation's selection;
# the project depends on none of its contents. The project names the inventory add-on's
# directory: an operation using the add-on keeps the setting, one without leaves it out.
def _test_directory_setting_resolves_per_operation(name):
    godot_project(
        name = name + "_project",
        project_file = _FIXTURE + ":project.godot",
        settings = {"game/inventory_directory": '"res://addons/inventory"'},
        tags = ["manual"],
    )
    analysis_test(
        name = name,
        targets = {
            "using": run_view(name + "_using", name + "_project", [_FIXTURE + ":main"]),
            "without": run_view(name + "_without", name + "_project", [_FIXTURE + ":other"]),
        },
        impl = _directory_setting_resolves_per_operation,
    )

def _directory_setting_resolves_per_operation(env, targets):
    env.expect.where(operation = "using").that_dict(targets.using[GodotViewInfo].export_configuration["settings"]).contains_at_least(
        {"game/inventory_directory": '"res://addons/inventory"'},
    )
    env.expect.where(operation = "without").that_collection(
        targets.without[GodotViewInfo].export_configuration["settings"].keys(),
    ).not_contains("game/inventory_directory")

# FR-012: resources may not hold a file in an add-on's directory, such as a copy of an
# editor-part script a test loads.
def _test_resources_in_an_addon_directory_fail(name):
    godot_resources(
        name = name + "_copy",
        resource_paths = {_FIXTURE + ":tool/plugin.gd": "addons/inventory/plugin.gd"},
        tags = ["manual"],
    )
    failure_test(
        name,
        run_view(name + "_run", _PROJECT, [_FIXTURE + ":main", name + "_copy"]),
        "res://addons/inventory/plugin.gd of *_copy lies in the directory res://addons/inventory/ of the add-on *inventory; declare it in the add-on",
    )

# The former workaround for tests of an editor part: a copy of its script at its own path.
def _test_copy_of_an_editor_part_file_fails(name):
    godot_resources(
        name = name + "_copy",
        testonly = True,
        resource_paths = {_FIXTURE + ":tool/plugin.gd": "addons/tool/plugin.gd"},
        tags = ["manual"],
    )
    godot_test(name = name + "_test", project = _PROJECT, tags = ["manual"], deps = [name + "_copy"])
    failure_test(
        name,
        name + "_test.view",
        "res://addons/tool/plugin.gd of *_copy lies in the directory res://addons/tool/ of the add-on *tool; declare it in the add-on",
    )

# FR-015: a test-only operation reaches an add-on's editor part through `<addon>.editor`,
# whose files become its members, together with the add-on; a product cannot (Bazel's
# testonly check), so no pack, source run or application contains an editor part.
def _test_tests_reach_editor_parts_through_the_editor_target(name):
    godot_resources(name = name + "_suites", testonly = True, tags = ["manual"], deps = [_FIXTURE + ":tool.editor"])
    godot_test(name = name + "_test", project = _PROJECT, tags = ["manual"], deps = [name + "_suites"])
    analysis_test(
        name = name,
        target = name + "_test.view",
        impl = _tests_reach_editor_parts_through_the_editor_target,
    )

def _tests_reach_editor_parts_through_the_editor_target(env, target):
    view = target[GodotViewInfo]
    env.expect.that_collection(sorted(view.member_resource_paths)).contains_at_least(
        ["addons/tool/plugin.cfg", "addons/tool/plugin.gd"],
    )
    env.expect.that_collection([str(addon.label) for addon in view.addons]).contains(_label("tool"))

def _test_products_cannot_reach_editor_parts(name):
    godot_resources(name = name + "_resources", testonly = False, tags = ["manual"], deps = [_FIXTURE + ":tool.editor"])
    failure_test(
        name,
        name + "_resources",
        "*non-test target '*_resources' depends on testonly target '*tool.editor' and doesn't have testonly attribute set*",
    )

def _declaration_failure_test(name, target, message):
    failure_test(name, _FIXTURE + ":" + target, message)

# FR-012: every file lives below the directory, in one part; the editor part holds exactly
# one plugin.cfg.
def _test_file_outside_the_addon_fails(name):
    _declaration_failure_test(name, "outside_directory", "*main/main.gd is outside strip_prefix *; give it its path in resource_paths")

def _test_file_in_both_parts_fails(name):
    _declaration_failure_test(name, "in_both_parts", "*res://addons/in_both_parts/plugin.gd is in both srcs and editor_srcs*")

def _test_plugin_config_in_runtime_part_fails(name):
    _declaration_failure_test(name, "plugin_in_runtime_part", "*res://addons/plugin_in_runtime_part/plugin.cfg belongs in editor_srcs*")

# FR-032: a sidecar is metadata of its file and belongs to the file's part.
def _test_sidecar_in_the_other_part_fails(name):
    _declaration_failure_test(name, "split_sidecar", "*res://addons/split_sidecar/plugin.gd.uid belongs in editor_srcs with res://addons/split_sidecar/plugin.gd; a sidecar is metadata of its file")

def _test_editor_part_without_plugin_config_fails(name):
    _declaration_failure_test(name, "editor_part_without_plugin", "*editor_srcs must contain exactly one plugin.cfg, found []")

# An autoload names a file of the runtime part or of the runtime part of a needed add-on.
def _test_autoload_outside_runtime_parts_fails(name):
    _declaration_failure_test(name, "autoload_outside_runtime_part", "*autoload Inventory names res://addons/inventory/inventory.gd, which is no file of the add-on's runtime part or of the runtime parts of the add-ons it needs")

def _test_autoload_of_a_needed_addon_is_contributed(name):
    analysis_test(
        name = name,
        target = _FIXTURE + ":autoload_of_needed_addon",
        impl = _autoload_of_a_needed_addon_is_contributed,
    )

def _autoload_of_a_needed_addon_is_contributed(env, target):
    env.expect.that_collection(target[GodotAddonInfo].autoloads).contains_exactly([
        ("Shared", "res://addons/utility/utility.gd", _label("autoload_of_needed_addon")),
    ])

# Platform libraries go in platform_deps, never in deps.
def _test_platform_library_in_addon_deps_fails(name):
    cc_library(name = name + "_library", tags = ["manual"])
    godot_addon(name = name + "_addon", tags = ["manual"], deps = [name + "_library"])
    failure_test(name, name + "_addon", "*_library in deps is no godot_addon or extension; declare platform libraries such as an android_library in platform_deps")

# Every extension in an add-on's deps is the add-on's, wherever its descriptor lies: the
# importer probe loads it and the graph attributes its files to the add-on.
def _test_extension_outside_the_directory_is_the_addons(name):
    analysis_test(
        name = name,
        target = _FIXTURE + ":foreign_extension",
        impl = _extension_outside_the_directory_is_the_addons,
    )

def _extension_outside_the_directory_is_the_addons(env, target):
    addon = target[GodotAddonInfo]
    env.expect.where(field = "extensions").that_collection(
        [extension.descriptor_path for extension in addon.extensions],
    ).contains_exactly(["addons/inventory/inventory.gdextension"])
    env.expect.where(field = "addons").that_collection(addon.addons.to_list()).has_size(0)

# The main scene of a feature, such as a test runner's host scene, is an add-on's setting
# like any other; the main scene itself is the project's main_scene.
def _test_main_scene_of_a_feature_is_an_addon_setting(name):
    godot_addon(
        name = name + "_addon",
        directory = "addons/host",
        settings = {"application/run/main_scene.test_host": '"res://addons/host/host.tscn"'},
        tags = ["manual"],
    )
    analysis_test(
        name = name,
        target = name + "_addon",
        impl = _main_scene_of_a_feature_is_an_addon_setting,
    )

def _main_scene_of_a_feature_is_an_addon_setting(env, target):
    env.expect.that_collection(
        [(key, value) for key, value, _owner in target[GodotAddonInfo].settings],
    ).contains_exactly([("application/run/main_scene.test_host", '"res://addons/host/host.tscn"')])

def _test_main_scene_setting_on_an_addon_fails(name):
    godot_addon(
        name = name + "_addon",
        directory = "addons/host",
        settings = {"application/run/main_scene": '"res://addons/host/host.tscn"'},
        tags = ["manual"],
    )
    failure_test(
        name,
        name + "_addon",
        "*Use autoloads, main_scene and the editor parts of add-ons instead of the setting application/run/main_scene",
    )

def addon_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_addon_outside_operations_imports_nothing,
            _test_autoload_of_a_needed_addon_is_contributed,
            _test_autoload_outside_runtime_parts_fails,
            _test_conflicting_autoloads_need_an_override,
            _test_copy_of_an_editor_part_file_fails,
            _test_directory_setting_resolves_per_operation,
            _test_editor_part_without_plugin_config_fails,
            _test_extension_outside_the_directory_is_the_addons,
            _test_file_in_both_parts_fails,
            _test_file_outside_the_addon_fails,
            _test_main_scene_of_a_feature_is_an_addon_setting,
            _test_main_scene_setting_on_an_addon_fails,
            _test_named_addon_is_in_every_operation,
            _test_named_addon_imports_its_own_files_with_its_importer,
            _test_named_addons_import_their_parts,
            _test_overlapping_addon_directories_fail,
            _test_platform_library_in_addon_deps_fails,
            _test_platform_library_on_resources_fails,
            _test_plugin_config_in_runtime_part_fails,
            _test_resources_in_an_addon_directory_fail,
            _test_production_operation_reaching_a_test_only_addon_fails,
            _test_products_cannot_reach_editor_parts,
            _test_project_override_resolves_conflicting_autoloads,
            _test_runtime_part_imports_after_needed_runtime_parts,
            _test_sidecar_in_the_other_part_fails,
            _test_tests_reach_editor_parts_through_the_editor_target,
            _test_used_and_named_addons_reach_the_operation,
            _test_vendored_release_lists_its_descriptor_and_delivers_its_library,
        ],
    )
