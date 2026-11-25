"""
How resources compose their members, import inputs and configuration into a project, and
which resource paths, prefixes, settings and autoloads analysis rejects.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:util.bzl", "TestingAspectInfo")
load("//godot:defs.bzl", "godot_project", "godot_resources", "godot_run")
load("//godot/private:providers.bzl", "GodotResourcesInfo")
load("//godot/private:view.bzl", "GodotViewInfo")
load(":expected_failures.bzl", "failure_test")
load(":views.bzl", "run_view")

_FIXTURE = "//godot/private/tests/fixtures/import_context"
_PROJECT_FILE = _FIXTURE + ":project.godot"
_CONFIGURED = [_FIXTURE + ":configured_check", _FIXTURE + ":configured_resources"]

# A resource lists every member and import input of its dependencies, but writes only its
# own paths; its relationships keep the declared runtime references.
def _test_resources_compose_members_and_import_inputs(name):
    analysis_test(name = name, target = _FIXTURE + ":content", impl = _resources_compose_members_and_import_inputs)

def _resources_compose_members_and_import_inputs(env, target):
    resources = target[GodotResourcesInfo]
    env.expect.that_collection(sorted(resources.member_resource_paths), expr = "member resource paths").contains_exactly([
        "external/LICENSE",
        "foreign/main.gd",
        "generated/data.gd",
        "main/main.gd",
        "main/main.tscn",
        "main/shared/helper.gd",
        "main/shared/helper.gd.uid",
    ]).in_order()
    env.expect.that_collection(sorted(resources.import_resource_paths), expr = "import resource paths").contains_exactly([
        "main/importer_data.txt",
    ])

    # The target writes only its own paths that imports stage, never scripts or scenes;
    # dependencies list theirs.
    actions = target[TestingAspectInfo].actions
    env.expect.that_collection([action.mnemonic for action in actions], expr = "action mnemonics").contains_exactly(["FileWrite"])
    env.expect.that_collection(sorted(json.decode(actions[0].content)), expr = "written resource paths").contains_exactly([
        "external/LICENSE",
    ])
    env.expect.that_int(len(resources.resource_path_manifests.to_list()), expr = "resource path manifests").equals(3)
    references = [
        (source, reference)
        for source, reference, kind, _ in resources.relationships.to_list()
        if kind == "runtime"
    ]
    env.expect.that_collection(references, expr = "runtime references").contains_at_least([
        ("main/main.gd", "main/shared/helper.gd"),
        ("main/shared/helper.gd", "main/main.gd"),
    ])
    env.expect.that_bool(resources.member_resource_paths["generated/data.gd"].is_source, expr = "generated/data.gd is a source").equals(False)
    license_owner = resources.member_resource_paths["external/LICENSE"].owner
    env.expect.that_bool(
        license_owner.workspace_name != target.label.workspace_name,
        expr = "external/LICENSE comes from another repository",
    ).equals(True)

# An operation's view names its runtime project file after itself and keeps import inputs
# out of its members.
def _test_project_keeps_import_inputs_out_of_members(name):
    godot_project(
        name = name + "_project",
        autoload_overrides = {"Helper": "*res://generated/data.gd"},
        main_scene = "main/main.tscn",
        project_file = _PROJECT_FILE,
        setting_overrides = {"application/config/name": '"Demo"'},
        tags = ["manual"],
    )
    analysis_test(
        name = name,
        target = run_view(name + "_run", name + "_project", [_FIXTURE + ":combined"]),
        impl = _project_keeps_import_inputs_out_of_members,
    )

def _project_keeps_import_inputs_out_of_members(env, target):
    project = target[GodotViewInfo]
    env.expect.that_str(project.runtime_project_file.basename).equals(target.label.name + ".project.godot")
    env.expect.that_collection(sorted(project.member_resource_paths), expr = "member resource paths").not_contains("main/importer_data.txt")
    env.expect.that_collection(sorted(project.import_resource_paths), expr = "import resource paths").contains_exactly([
        "main/importer_data.txt",
    ])
    env.expect.that_collection(sorted(project.member_owners), expr = "member owners").contains("main/main.gd")

# An operation's view names the label that declares each import input, through the
# resources that take it as an import input.
def _test_project_names_import_input_owners(name):
    godot_project(
        name = name + "_project",
        project_file = _PROJECT_FILE,
        tags = ["manual"],
    )
    analysis_test(
        name = name,
        target = run_view(name + "_run", name + "_project", [_FIXTURE + ":import_input_consumer"]),
        impl = _project_names_import_input_owners,
    )

def _project_names_import_input_owners(env, target):
    env.expect.where(field = "import_owners").that_dict(target[GodotViewInfo].import_owners).contains_exactly({
        "private_import_input.gd": str(Label(_FIXTURE + ":private_import_input")),
    })

# Resources name the label that declares each of their import inputs.
def _test_resources_name_import_input_owners(name):
    analysis_test(name = name, target = _FIXTURE + ":content", impl = _resources_name_import_input_owners)

def _resources_name_import_input_owners(env, target):
    env.expect.where(field = "import_owners").that_dict(target[GodotResourcesInfo].import_owners).contains_exactly({
        "main/importer_data.txt": str(Label(_FIXTURE + ":import_data")),
    })

def _test_resource_path_collision_fails(name):
    godot_resources(
        name = name + "_resources",
        resource_paths = {_FIXTURE + ":main/other.gd": "main/main.gd"},
        tags = ["manual"],
        deps = [_FIXTURE + ":content"],
    )
    failure_test(name, name + "_resources", "Conflicting Godot resource paths res://main/main.gd")

def _test_file_directory_collision_fails(name):
    godot_resources(
        name = name + "_resources",
        resource_paths = {_FIXTURE + ":main/other.gd": "generated"},
        tags = ["manual"],
        deps = [_FIXTURE + ":content"],
    )
    failure_test(name, name + "_resources", "Conflicting Godot file/directory paths res://generated")

def _test_nonadjacent_file_directory_collision_fails(name):
    godot_resources(
        name = name + "_resources",
        resource_paths = {
            _FIXTURE + ":main/main.gd": "a",
            _FIXTURE + ":main/other.gd": "a-b",
            _FIXTURE + ":main/importer_data.txt": "a/b",
        },
        tags = ["manual"],
    )
    failure_test(name, name + "_resources", "Conflicting Godot file/directory paths res://a")

# Two dependencies set one setting to different values, and the project overrides neither.
def _test_conflicting_settings_fail(name):
    godot_project(
        name = name + "_project",
        project_file = _PROJECT_FILE,
        tags = ["manual"],
    )
    failure_test(name, run_view(name + "_run", name + "_project", [_FIXTURE + ":combined"]), "Conflicting Godot configuration")

def _test_case_collision_fails(name):
    godot_resources(
        name = name + "_resources",
        resource_paths = {
            _FIXTURE + ":main/main.gd": "A.gd",
            _FIXTURE + ":main/other.gd": "a.gd",
        },
        tags = ["manual"],
    )
    failure_test(name, name + "_resources", "Portable Godot resource path collision")

def _test_case_file_directory_collision_fails(name):
    godot_resources(
        name = name + "_resources",
        resource_paths = {
            _FIXTURE + ":main/main.gd": "Assets",
            _FIXTURE + ":main/other.gd": "assets/file.gd",
        },
        tags = ["manual"],
    )
    failure_test(name, name + "_resources", "Portable Godot file/directory path collision")

def _test_directory_case_collision_fails(name):
    godot_resources(
        name = name + "_resources",
        resource_paths = {
            _FIXTURE + ":main/main.gd": "Assets/main.gd",
            _FIXTURE + ":main/other.gd": "assets/other.gd",
        },
        tags = ["manual"],
    )
    failure_test(name, name + "_resources", "Portable Godot directory path collision")

def _test_undeclared_autoload_fails(name):
    godot_project(
        name = name + "_project",
        autoloads = {"Missing": "*res://absent.gd"},
        project_file = _PROJECT_FILE,
        tags = ["manual"],
    )
    run_view(name + "_run", name + "_project", [])
    failure_test(name, name + "_run", "Autoload Missing res://absent.gd is not a declared project member")

# Like main_scene, run entry points accept an optional res:// prefix.
def _test_run_entry_point_accepts_res_prefix(name):
    godot_run(
        name = name + "_run",
        main = "res://main/configured_test.gd",
        project = _FIXTURE,
        tags = ["manual"],
        deps = _CONFIGURED,
    )
    analysis_test(name = name, target = name + "_run", impl = _analyzes)

def _analyzes(_env, _target):
    """The claim is that analysis succeeds; analysis_test fails the test otherwise."""
    pass

# An add-on's sources move under its prefix after strip_prefix; explicit resource paths stay.
def _test_prefix_places_sources_after_strip_prefix(name):
    analysis_test(name = name, target = _FIXTURE + ":prefixed_addon", impl = _prefix_places_sources_after_strip_prefix)

def _prefix_places_sources_after_strip_prefix(env, target):
    env.expect.that_collection(sorted(target[GodotResourcesInfo].member_resource_paths), expr = "member resource paths").contains_exactly([
        "addons/inventory/inventory.gd",
        "addons/inventory/other.gd",
    ]).in_order()

def _test_prefix_without_strip_prefix_keeps_package_path(name):
    analysis_test(name = name, target = _FIXTURE + ":prefixed_package", impl = _prefix_without_strip_prefix_keeps_package_path)

def _prefix_without_strip_prefix_keeps_package_path(env, target):
    env.expect.that_collection(sorted(target[GodotResourcesInfo].member_resource_paths), expr = "member resource paths").contains_exactly([
        "lib/main/addon/inventory.gd",
    ])

def _test_escaping_prefix_fails(name):
    godot_resources(
        name = name + "_resources",
        srcs = [_FIXTURE + ":main/addon/inventory.gd"],
        prefix = "../outside",
        tags = ["manual"],
    )
    failure_test(name, name + "_resources", "Resource paths cannot contain empty, '.' or '..' components")

def _test_prefixed_path_collision_fails(name):
    godot_resources(
        name = name + "_resources",
        resource_paths = {_FIXTURE + ":main/other.gd": "addons/inventory/inventory.gd"},
        tags = ["manual"],
        deps = [_FIXTURE + ":prefixed_addon"],
    )
    failure_test(name, name + "_resources", "Conflicting Godot resource paths res://addons/inventory/inventory.gd")

# runtime_deps members join the resources and every view over them, like deps members.
def _test_runtime_deps_become_project_members(name):
    analysis_test(
        name = name,
        targets = {"view": _runtime_deps_arrangement(name), "resources": name + "_resources"},
        impl = _runtime_deps_become_project_members,
    )

def _runtime_deps_arrangement(name):
    godot_resources(
        name = name + "_resources",
        runtime_deps = [_FIXTURE + ":configured_check"],
        tags = ["manual"],
        deps = [_FIXTURE + ":configured_resources"],
    )
    godot_project(
        name = name + "_project",
        project_file = _PROJECT_FILE,
        tags = ["manual"],
    )
    return run_view(name + "_run", name + "_project", [name + "_resources"])

def _runtime_deps_become_project_members(env, targets):
    check = str(Label(_FIXTURE + ":configured_check"))

    # The view adds the runtime part of the add-on configured_resources uses.
    for subject, info, addon_members in [
        ("resources", targets.resources[GodotResourcesInfo], []),
        ("view", targets.view[GodotViewInfo], ["addons/configuration/configuration.gd"]),
    ]:
        env.expect.where(subject = subject).that_collection(
            sorted(info.member_resource_paths),
            expr = "member resource paths",
        ).contains_exactly(addon_members + [
            "main/configured_test.gd",
            "main/main.tscn",
        ]).in_order()
        env.expect.where(subject = subject).that_str(
            info.member_owners.get("main/configured_test.gd", ""),
        ).equals(check)

# Each runtime_deps member is a runtime group relationship of the declaring target, which
# a pack's reachable selection keeps together; a plain deps member is none.
def _test_runtime_deps_add_runtime_group_relationships(name):
    analysis_test(
        name = name,
        targets = {"view": _runtime_deps_arrangement(name), "resources": name + "_resources"},
        impl = _runtime_deps_add_runtime_group_relationships,
    )

def _runtime_deps_add_runtime_group_relationships(env, targets):
    owner = str(targets.resources.label)
    for subject, info in [
        ("resources", targets.resources[GodotResourcesInfo]),
        ("view", targets.view[GodotViewInfo]),
    ]:
        groups = [
            edge
            for edge in info.relationships.to_list()
            if edge[0] == "" and edge[2] == "runtime"
        ]
        env.expect.where(subject = subject).that_collection(
            groups,
            expr = "runtime group relationships",
        ).contains_exactly([("", "main/configured_test.gd", "runtime", owner)])

# Resources pass on the add-ons they and their dependencies use; the add-ons carry the
# settings and autoloads, each with the label that declares it.
def _test_resources_pass_on_the_addons_they_use(name):
    analysis_test(
        name = name,
        targets = {"combined": _FIXTURE + ":combined", "content": _FIXTURE + ":content"},
        impl = _resources_pass_on_the_addons_they_use,
    )

def _resources_pass_on_the_addons_they_use(env, targets):
    configuration = str(Label(_FIXTURE + ":content_configuration"))
    branding = str(Label(_FIXTURE + ":branding"))
    env.expect.that_collection(
        [str(addon.label) for addon in targets.content[GodotResourcesInfo].addons.to_list()],
        expr = "own add-ons",
    ).contains_exactly([configuration])
    env.expect.that_collection(
        [str(addon.label) for addon in targets.combined[GodotResourcesInfo].addons.to_list()],
        expr = "transitive add-ons",
    ).contains_exactly([branding, configuration])
    addon = targets.content[GodotResourcesInfo].addons.to_list()[0]
    env.expect.that_collection(addon.settings, expr = "settings").contains_exactly([
        ("application/config/name", '"Content"', configuration),
    ])
    env.expect.that_collection(addon.autoloads, expr = "autoloads").contains_exactly([
        ("Helper", "*res://addons/content_configuration/helper.gd", configuration),
    ])

# An operation's view resolves the contributions of its add-ons under its project and
# names the origin of each composed setting.
def _test_project_resolves_contributed_settings_and_autoloads(name):
    analysis_test(
        name = name,
        targets = {
            "project": _FIXTURE,
            "view": run_view(name + "_run", _FIXTURE, _CONFIGURED),
        },
        impl = _project_resolves_contributed_settings_and_autoloads,
    )

def _project_resolves_contributed_settings_and_autoloads(env, targets):
    project = targets.view[GodotViewInfo]
    owner = str(targets.project.label)
    env.expect.where(field = "composed_settings").that_dict(project.composed_settings).contains_exactly({
        "application/config/name": owner,
        "application/run/main_scene": owner,
        "autoload/State": str(Label(_FIXTURE + ":configuration")),
    })
    env.expect.where(field = "export autoloads").that_dict(
        project.export_configuration["autoloads"],
    ).contains_exactly({"State": "*res://addons/configuration/configuration.gd"})
    env.expect.where(field = "export settings").that_dict(
        project.export_configuration["settings"],
    ).contains_exactly({"application/config/name": '"Configured"'})

def resource_composition_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_case_collision_fails,
            _test_case_file_directory_collision_fails,
            _test_conflicting_settings_fail,
            _test_directory_case_collision_fails,
            _test_escaping_prefix_fails,
            _test_file_directory_collision_fails,
            _test_nonadjacent_file_directory_collision_fails,
            _test_prefix_places_sources_after_strip_prefix,
            _test_prefix_without_strip_prefix_keeps_package_path,
            _test_prefixed_path_collision_fails,
            _test_project_keeps_import_inputs_out_of_members,
            _test_project_names_import_input_owners,
            _test_project_resolves_contributed_settings_and_autoloads,
            _test_resource_path_collision_fails,
            _test_resources_compose_members_and_import_inputs,
            _test_resources_pass_on_the_addons_they_use,
            _test_resources_name_import_input_owners,
            _test_run_entry_point_accepts_res_prefix,
            _test_runtime_deps_add_runtime_group_relationships,
            _test_runtime_deps_become_project_members,
            _test_undeclared_autoload_fails,
        ],
    )
