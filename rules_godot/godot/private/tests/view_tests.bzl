"""
What the configuration of each Godot process names: the shell-assets probe's view (FR-029).

The fixture's content uses `inventory`, whose autoload names a script of its runtime part,
and the project names `tool`, an editor-only add-on.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot:defs.bzl", "godot_pack", "godot_run", "godot_test")
load("//godot/private/tests:pack_forms.bzl", "GODOT_EXPORT")
load(":action_inputs.bzl", "GodotActionsInfo", "actions_of", "expect_not_read", "expect_reads", "godot_actions")

visibility("private")

_FIXTURE = "//godot/private/tests/fixtures/project_with_addons"

# #129: the probe creates no autoload whose script it does not stage. Its configuration
# names no autoload at all, while the export's names both, and the probe stages neither
# script; it enables no plugin and stages no editor part (D29).
def _test_shell_probe_names_no_autoload_it_does_not_stage(name):
    godot_pack(
        name = name + "_pack",
        project = _FIXTURE,
        tags = ["manual"],
        deps = [_FIXTURE + ":main"],
    )
    analysis_test(
        name = name,
        target = name + "_pack",
        impl = _shell_probe_names_no_autoload_it_does_not_stage,
        config_settings = GODOT_EXPORT,
        extra_target_under_test_aspects = [godot_actions],
    )

def _written(target, basename):
    """The content of the manifest the target's view writes as basename."""
    for entry in target[GodotActionsInfo].every.to_list():
        if entry.action.mnemonic == "FileWrite" and entry.action.outputs.to_list()[0].basename == basename:
            return json.decode(entry.action.content)
    fail("no action writes " + basename)

def _shell_probe_names_no_autoload_it_does_not_stage(env, target):
    view = target.label.name + ".view"
    shell = _written(target, view + ".shell.config.json")
    env.expect.where(field = "shell autoloads").that_dict(shell["autoloads"]).contains_exactly({})
    env.expect.where(field = "shell main scene").that_str(shell["main_scene"]).equals("")
    env.expect.where(field = "shell context_only").that_bool(shell["context_only"]).equals(True)
    env.expect.where(field = "shell plugins").that_collection(shell["editor_plugins"]).contains_exactly([])
    exported = _written(target, view + ".export.config.json")
    env.expect.where(field = "export autoloads").that_collection(exported["autoloads"].keys()).contains_exactly(
        ["Inventory", "Utility"],
    )

    # The probe starts from the shell configuration, never the export's.
    probes = actions_of(target, "GodotShellAssets")
    env.expect.where(field = "probes").that_collection(probes).has_size(1)
    env.expect.where(field = "probe configuration").that_collection(
        [file.basename for file in probes[0].inputs.to_list() if file.basename.endswith(".project.godot")],
    ).contains_exactly([view + ".shell.project.godot"])
    for script in ["project_with_addons/inventory/inventory.gd", "project_with_addons/utility/utility.gd"]:
        expect_reads(env, target, "GodotPack", script)
        expect_not_read(env, target, ["GodotShellAssets"], script)
    expect_not_read(env, target, ["GodotPack", "GodotShellAssets"], "project_with_addons/tool/plugin.gd")

# FR-005 for the authored project.godot: its values are known only when a configuration is
# constructed. The view of a source run lists the settings it leaves out naming the run,
# and that action fails for any. A pack's view names no program entry; a pack without
# required packs, which only the pack rule resolves, lists them again in a validation
# action naming the pack, which no other action reads; a pack with required packs, here
# through a select, lists none.
def _test_program_entry_checks_authored_entries(name):
    godot_pack(
        name = name + "_pack",
        project = _FIXTURE,
        tags = ["manual"],
        deps = [_FIXTURE + ":main"],
    )
    godot_pack(
        name = name + "_dlc",
        project = _FIXTURE,
        required_packs = select({"//conditions:default": [name + "_pack"]}),
        tags = ["manual"],
        deps = [_FIXTURE + ":other"],
    )
    godot_run(
        name = name + "_run",
        project = _FIXTURE,
        tags = ["manual"],
        deps = [_FIXTURE + ":main"],
    )
    godot_test(
        name = name + "_test",
        project = _FIXTURE,
        tags = ["manual"],
        deps = [_FIXTURE + ":main"],
    )
    analysis_test(
        name = name,
        targets = {
            "dlc": name + "_dlc",
            "pack": name + "_pack",
            "run": name + "_run.view",
            "test": name + "_test.view",
        },
        impl = _program_entry_checks_authored_entries,
        extra_target_under_test_aspects = [godot_actions],
    )

def _program_entry_checks_authored_entries(env, targets):
    pack = str(targets.pack.label).removeprefix("@@")
    run = str(targets.run.label).removeprefix("@@").removesuffix(".view")
    for target, view, program_entry in [
        (targets.pack, targets.pack.label.name + ".view", ""),
        (targets.dlc, targets.dlc.label.name + ".view", ""),
        (targets.run, targets.run.label.name, run),
        (targets.test, targets.test.label.name, ""),
    ]:
        entries = _written(target, view + ".left_out.config.json")
        env.expect.where(operation = view).that_str(entries["program_entry"]).equals(program_entry)
    for target, checked in [(targets.pack, True), (targets.dlc, False)]:
        export = target.label.name + ".export"
        checks = [
            entry.action
            for entry in target[GodotActionsInfo].actions.to_list()
            if entry.action.mnemonic == "GodotConfigurationEntries" and entry.owner.endswith(export)
        ]
        env.expect.where(pack = target.label.name).that_collection(checks).has_size(1 if checked else 0)
        if not checked:
            continue
        entries = _written(target, export + ".left_out.config.json")
        env.expect.where(pack = target.label.name).that_str(entries["program_entry"]).equals(pack)

        # Overrides apply only for tags the export can have: Godot's own and the
        # project's custom features, of which the fixture has none.
        env.expect.where(pack = target.label.name, field = "features").that_collection(entries["features"]).contains_at_least(
            ["mobile", "template"],
        )
        output = checks[0].outputs.to_list()[0]
        env.expect.where(pack = target.label.name, output = "_validation").that_collection(
            target[OutputGroupInfo]._validation.to_list(),
        ).contains(output)
        for entry in target[GodotActionsInfo].actions.to_list():
            env.expect.where(action = entry.action.mnemonic, owner = entry.owner).that_bool(
                output in entry.action.inputs.to_list(),
            ).equals(False)

def view_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_program_entry_checks_authored_entries,
            _test_shell_probe_names_no_autoload_it_does_not_stage,
        ],
    )
