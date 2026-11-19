"""
An engine upgrade reruns the editor's actions but not the native actions of a godot-cpp
extension.

Each test analyzes the fixture's pack twice, with the stable and with the beta engine's
toolchains. An action stays cached after the upgrade when its command and inputs are the
same under both engines and no input derives from the engine; an action that reads the
editor or a file derived from it reruns.
"""

load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/private/tests:pack_forms.bzl", "GODOT_EXPORT")
load(":engines.bzl", "ENGINES", "with_engine")

visibility("private")

_FIXTURE = "//godot/extension/tests/compatibility/fixtures/godot_cpp_extension_project:pack"
_NATIVE = ["GodotCppBindings", "CppCompile", "CppArchive", "CppLink"]

# Actions that run the editor. The imports run it in action templates, which analysis does
# not expose; the metadata index reruns because it reads their results.
_RUNS_EDITOR = ["GodotImportFeatures", "GodotImportableSuffixes", "GodotPack"]
_READS_EDITOR_RESULTS = ["GodotMetadataIndex"]

# The project.godot file of the export purpose. The import purpose's file reads the editor's
# feature list, so whether it stays cached depends on that output, not on its inputs.
_PROJECT_FILES = ["GodotExportConfig"]

# A C++ compile action replaces its inputs with the headers its compiler read once it has run
# or hit the action cache in the Bazel server, so its inputs depend on what earlier builds
# executed. Its declared headers stand in for them: the headers it reads are among them.
_DISCOVERS_INPUTS = ["CppCompile"]
_HEADER_EXTENSIONS = ["h", "hh", "hpp", "hxx", "inc", "inl", "ipp"]

_ReachedActionsInfo = provider(
    doc = "Native and Godot actions a target reaches, by owner label.",
    fields = {"actions": "depset of struct(owner, action, headers)"},
)

def _reached_actions_impl(target, ctx):
    dependencies = []
    for attribute in dir(ctx.rule.attr):
        value = getattr(ctx.rule.attr, attribute)
        if type(value) == "dict":
            # Label-keyed dicts, such as an extension's libraries.
            value = list(value.keys()) + list(value.values())
        dependencies.extend([
            dependency
            for dependency in (value if type(value) == "list" else [value])
            if type(dependency) == "Target"
        ])

    # The headers the target's compile actions may read: its own and its dependencies'.
    headers = depset(
        [file for file in getattr(ctx.rule.files, "srcs", []) if file.extension in _HEADER_EXTENSIONS],
        transitive = [
            dependency[CcInfo].compilation_context.headers
            for dependency in [target] + dependencies
            if CcInfo in dependency
        ],
    )
    own = [
        struct(owner = str(target.label), action = action, headers = headers)
        for action in target.actions
        if action.mnemonic in _NATIVE or action.mnemonic.startswith("Godot")
    ]
    transitive = [
        dependency[_ReachedActionsInfo].actions
        for dependency in dependencies
        if _ReachedActionsInfo in dependency
    ]
    return [_ReachedActionsInfo(actions = depset(own, transitive = transitive))]

_reached_actions = aspect(
    implementation = _reached_actions_impl,
    attr_aspects = ["*"],
    doc = "Collect the native and Godot actions a target reaches through every dependency.",
)

def _arrange(name):
    for engine in ENGINES:
        with_engine(
            name = "%s_%s" % (name, engine),
            engine = engine,
            target = _FIXTURE,
            tags = ["manual"],
        )
    return {engine: ":%s_%s" % (name, engine) for engine in ENGINES}

def _entries(target, mnemonics):
    return [
        entry
        for entry in target[_ReachedActionsInfo].actions.to_list()
        if entry.action.mnemonic in mnemonics
    ]

def _without_configuration(text):
    # Output directories name the configuration, such as darwin_arm64-fastbuild-ST-<hash>.
    parts = text.split("bazel-out/")
    return parts[0] + "".join([
        "bazel-out/<configuration>" + (part[part.find("/"):] if "/" in part else "")
        for part in parts[1:]
    ])

def _inputs(entry):
    """Return the action's inputs, the same whatever earlier builds executed."""
    inputs = entry.action.inputs.to_list()
    if entry.action.mnemonic not in _DISCOVERS_INPUTS:
        return inputs
    headers = entry.headers.to_list()
    declared = {file.path: None for file in headers}
    return [file for file in inputs if file.path not in declared] + headers

def _signature(entry):
    action = entry.action
    return json.encode({
        "argv": [_without_configuration(argument) for argument in action.argv or []],
        "env": {key: _without_configuration(value) for key, value in action.env.items()},
        "inputs": sorted([file.short_path for file in _inputs(entry)]),
        "mnemonic": action.mnemonic,
        "outputs": sorted([file.short_path for file in action.outputs.to_list()]),
        "owner": entry.owner,
    })

def _editor_repository(engine):
    # The hub's editor repositories are its siblings, such as <hub>_editor_macos.
    return "../" + Label(ENGINES[engine]).repo_name + "_editor_"

def _is_editor(file, engine):
    return file.short_path.startswith(_editor_repository(engine))

def _reads_editor(action, engine):
    return any([_is_editor(file, engine) for file in action.inputs.to_list()])

def _engine_derived(target):
    """
    Return the paths of the files that change with the engine.

    These are the editor's files and, transitively, the outputs of Godot actions that read
    one. The results of action templates, which analysis does not expose, count as derived.
    """
    entries = target[_ReachedActionsInfo].actions.to_list()
    godot = [entry.action for entry in entries if entry.action.mnemonic.startswith("Godot")]
    produced = {file.path: None for entry in entries for file in entry.action.outputs.to_list()}
    derived = {}
    for action in godot:
        for file in action.inputs.to_list():
            hidden_result = file.is_directory and not file.is_source and file.path not in produced
            if hidden_result or any([_is_editor(file, engine) for engine in ENGINES]):
                derived[file.path] = None
    for _ in range(len(godot)):
        changed = False
        for action in godot:
            outputs = [file.path for file in action.outputs.to_list() if file.path not in derived]
            if outputs and any([file.path in derived for file in action.inputs.to_list()]):
                derived.update({path: None for path in outputs})
                changed = True
        if not changed:
            break
    return derived

def _expect_unchanged(env, targets, mnemonics):
    """Assert that the actions have the same command and inputs under both engines, none derived."""
    for engine in ENGINES:
        target = getattr(targets, engine)
        derived = _engine_derived(target)
        for entry in _entries(target, mnemonics):
            env.expect.where(configuration = engine, mnemonic = entry.action.mnemonic, owner = entry.owner).that_collection(
                [file.short_path for file in _inputs(entry) if file.path in derived],
            ).contains_exactly([])
    stable = _entries(targets.stable, mnemonics)
    env.expect.that_collection([_signature(entry) for entry in _entries(targets.beta, mnemonics)]).contains_exactly(
        [_signature(entry) for entry in stable],
    )
    return {entry.action.mnemonic: None for entry in stable}.keys()

def _test_engine_upgrade_leaves_native_actions_unchanged(name):
    analysis_test(
        name = name,
        targets = _arrange(name),
        impl = _engine_upgrade_leaves_native_actions_unchanged,
        extra_target_under_test_aspects = [_reached_actions],
    )

def _engine_upgrade_leaves_native_actions_unchanged(env, targets):
    reached = _expect_unchanged(env, targets, _NATIVE)
    env.expect.that_collection(reached).contains_at_least(["GodotCppBindings", "CppCompile"])

def _test_engine_upgrade_leaves_export_project_file_unchanged(name):
    analysis_test(
        name = name,
        targets = _arrange(name),
        impl = _engine_upgrade_leaves_export_project_file_unchanged,
        extra_target_under_test_aspects = [_reached_actions],
    )

def _engine_upgrade_leaves_export_project_file_unchanged(env, targets):
    reached = _expect_unchanged(env, targets, _PROJECT_FILES)
    env.expect.that_collection(reached).contains_exactly(_PROJECT_FILES)

def _test_engine_upgrade_reruns_editor_actions(name):
    analysis_test(
        name = name,
        targets = _arrange(name),
        impl = _engine_upgrade_reruns_editor_actions,
        config_settings = GODOT_EXPORT,
        extra_target_under_test_aspects = [_reached_actions],
    )

def _engine_upgrade_reruns_editor_actions(env, targets):
    for engine in ENGINES:
        target = getattr(targets, engine)
        derived = _engine_derived(target)
        for mnemonic in _RUNS_EDITOR + _READS_EDITOR_RESULTS:
            entries = _entries(target, [mnemonic])
            env.expect.where(configuration = engine, mnemonic = mnemonic).that_int(len(entries)).is_greater_than(0)
            for entry in entries:
                if mnemonic in _READS_EDITOR_RESULTS:
                    env.expect.where(configuration = engine, mnemonic = mnemonic, owner = entry.owner).that_bool(
                        any([file.path in derived for file in entry.action.inputs.to_list()]),
                    ).equals(True)
                    continue

                # The selected engine's editor, and not the other one's.
                for editor in ENGINES:
                    env.expect.where(configuration = engine, mnemonic = mnemonic, owner = entry.owner, editor = editor).that_bool(
                        _reads_editor(entry.action, editor),
                    ).equals(editor == engine)

def engine_upgrade_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_engine_upgrade_leaves_native_actions_unchanged,
            _test_engine_upgrade_leaves_export_project_file_unchanged,
            _test_engine_upgrade_reruns_editor_actions,
        ],
    )
