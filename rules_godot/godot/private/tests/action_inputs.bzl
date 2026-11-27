"""
Action-input assertions for analysis tests of cache reuse and invalidation.

A relevant edit reruns an action only when the edited file or setting is one of the
action's declared inputs or arguments; an unrelated edit leaves the action cached when it is
not. The `godot_actions` aspect collects the Godot actions a target reaches through its
dependency graph, so a test can assert both sides for the action a change must or must not
rerun.

Sections: Action aspect, Built graph, Path mapping.
"""

load("//godot/private:paths.bzl", "mapped_path")

visibility([
    "//godot/engine/private/tests/...",
    "//godot/extension/tests/...",
    "//godot/platforms/private/tests/...",
    "//godot/private/config/tests/...",
    "//godot/private/tests/...",
])

# ==== Action aspect ===========================================================

GodotActionsInfo = provider(
    doc = "Godot actions a target reaches through its dependencies, by owner label.",
    fields = {
        "actions": "depset of struct(owner, action) of the Godot actions",
        "every": "depset of struct(owner, action) of all actions, for the helpers that follow outputs",
    },
)

def _godot_actions_impl(target, ctx):
    every = [struct(owner = str(target.label), action = action) for action in target.actions]
    own = [entry for entry in every if entry.action.mnemonic.startswith("Godot")]
    transitive = []
    transitive_every = []
    for attribute in dir(ctx.rule.attr):
        value = getattr(ctx.rule.attr, attribute)
        for dependency in value if type(value) == "list" else [value]:
            if type(dependency) == "Target" and GodotActionsInfo in dependency:
                transitive.append(dependency[GodotActionsInfo].actions)
                transitive_every.append(dependency[GodotActionsInfo].every)
    return [GodotActionsInfo(
        actions = depset(own, transitive = transitive),
        every = depset(every, transitive = transitive_every),
    )]

godot_actions = aspect(
    implementation = _godot_actions_impl,
    attr_aspects = ["*"],
    doc = "Collect the Godot actions a target reaches through every dependency attribute.",
)

def actions_of(target, mnemonic):
    """
    Return the reached actions with one mnemonic.

    Args:
        target: The target under test, analyzed with the godot_actions aspect.
        mnemonic: An action mnemonic, such as GodotPack.

    Returns:
        A list of actions, in a stable order.
    """
    found = [entry for entry in target[GodotActionsInfo].actions.to_list() if entry.action.mnemonic == mnemonic]
    return [entry.action for entry in sorted(found, key = lambda entry: entry.owner)]

def mnemonics_of(target):
    """Return the sorted set of Godot mnemonics a target reaches."""
    return sorted({entry.action.mnemonic: None for entry in target[GodotActionsInfo].actions.to_list()})

def input_paths(action):
    """Return the short paths of an action's inputs."""
    return [file.short_path for file in action.inputs.to_list()]

def source_inputs(actions, prefix):
    """
    Return the short paths of the source files under a prefix that actions read.

    Args:
        actions: The actions, such as those a target under test owns or reaches.
        prefix: The start of the short paths that count, such as a fixture's package.

    Returns:
        A sorted list of short paths.
    """
    return sorted({
        file.short_path: None
        for action in actions
        for file in action.inputs.to_list()
        if file.is_source and file.short_path.startswith(prefix)
    })

def _reads(action, path):
    return any([candidate == path or candidate.endswith("/" + path) for candidate in input_paths(action)])

def expect_reads(env, target, mnemonic, path):
    """
    Assert that every action with the mnemonic declares the file as an input.

    Args:
        env: The rules_testing environment.
        target: The target under test, analyzed with the godot_actions aspect.
        mnemonic: The action that a change of the file must rerun.
        path: The file's short path, or a suffix of it after a slash.
    """
    actions = actions_of(target, mnemonic)
    env.expect.where(mnemonic = mnemonic).that_int(len(actions)).is_greater_than(0)
    for action in actions:
        env.expect.where(mnemonic = mnemonic, path = path).that_bool(_reads(action, path)).equals(True)

def expect_not_read(env, target, mnemonics, path):
    """
    Assert that no action with one of the mnemonics declares the file as an input.

    Args:
        env: The rules_testing environment.
        target: The target under test, analyzed with the godot_actions aspect.
        mnemonics: The actions that a change of the file must leave cached; an empty list
            means every Godot action the target reaches.
        path: The file's short path, or a suffix of it after a slash.
    """
    reached = target[GodotActionsInfo].actions.to_list()
    for entry in reached:
        if mnemonics and entry.action.mnemonic not in mnemonics:
            continue
        env.expect.where(mnemonic = entry.action.mnemonic, owner = entry.owner, path = path).that_bool(
            _reads(entry.action, path),
        ).equals(False)

# ==== Built graph =============================================================

# The import of each unit is a directory template (`map_directory`), which analysis does
# not show: no target lists it among its actions. A build that needs a unit's import
# result, the `<unit>.import` directory, also runs the actions whose outputs only the
# import reads: these, of the project whose import configuration the unit's import
# manifest `<unit>.import.json` names.
_IMPORT_INPUT_MNEMONICS = ["GodotImportConfig", "GodotImportFeatures", "GodotImportableSuffixes"]

_GENERATED = ["FileWrite", "TemplateExpand"]

def _matches(file, path):
    return file.short_path == path or file.short_path.endswith("/" + path)

def _import_inputs_by_project(every):
    """Return the outputs of the _IMPORT_INPUT_MNEMONICS actions by owner and output directory."""
    import_inputs = {}
    for entry in every:
        if entry.action.mnemonic not in _IMPORT_INPUT_MNEMONICS:
            continue
        outputs = entry.action.outputs.to_list()
        for output in outputs:
            import_inputs.setdefault((entry.owner, output.dirname), []).extend(outputs)
    return import_inputs

def _index_outputs(target):
    """
    Map each output of the target's actions to the action that produces it.

    The index also finds outputs by mapped path and holds each project's import inputs.
    """
    every = target[GodotActionsInfo].every.to_list()
    producers = {}
    by_path = {}
    for entry in every:
        for output in entry.action.outputs.to_list():
            producers[output] = entry

            # Manifests name outputs by their mapped paths.
            by_path[mapped_path(output)] = output
    return struct(producers = producers, by_path = by_path, import_inputs = _import_inputs_by_project(every))

def _requested(target):
    """Return the files a build of the target requests: its default outputs, runfiles and validation outputs."""
    info = target[DefaultInfo]
    files = info.files.to_list()
    if info.files_to_run and info.files_to_run.executable:
        files += info.default_runfiles.files.to_list()
    if OutputGroupInfo in target:
        groups = target[OutputGroupInfo]
        for group in ["_validation", "_hidden_top_level_INTERNAL_"]:
            if group in dir(groups):
                files += getattr(groups, group).to_list()
    return files

def _import_inputs(index, directory):
    """Return what a build of an import directory needs: the unit's import manifest and the outputs of its project's import configuration."""
    manifest = index.by_path.get(mapped_path(directory) + ".json")
    if not manifest:
        return []
    configuration = index.by_path.get(json.decode(index.producers[manifest].action.content)["project_file"])
    if not configuration:
        return [manifest]
    return [manifest] + index.import_inputs.get((index.producers[configuration].owner, configuration.dirname), [])

def _build(index, built, file):
    """Record the action that produces the file as built and return the files it needs in turn."""
    entry = index.producers.get(file)
    if not entry:
        if file.is_directory and file.basename.endswith(".import"):
            return _import_inputs(index, file)
        return []
    if entry.action in built:
        return []
    inputs = entry.action.inputs.to_list()
    built[entry.action] = struct(
        owner = entry.owner,
        action = entry.action,
        mnemonic = entry.action.mnemonic,
        inputs = inputs,
    )
    return inputs

def build_graph(target):
    """
    Return the actions a build of the target runs, with the producers of their inputs.

    A build runs the actions that produce the target's default outputs, the runfiles of
    its executable and its validation outputs, and transitively those that produce their
    inputs. An action the target reaches but this build does not request, such as an
    output group's, is not part of it. The imports themselves are not part of it, since
    analysis does not show them; the actions in _IMPORT_INPUT_MNEMONICS whose outputs they
    read are.

    Args:
        target: The target under test, analyzed with the godot_actions aspect.

    Returns:
        A struct with `built`, a list of struct(owner, action, mnemonic, inputs) in a
        stable order, and `producers`, a dict from every produced file to its
        struct(owner, action).
    """
    index = _index_outputs(target)
    pending = _requested(target)
    seen = {}
    built = {}

    # Each round follows one more level of producers; the graph has fewer levels than
    # actions.
    for _ in range(len(index.producers) + 1):
        following = []
        for file in pending:
            if file in seen:
                continue
            seen[file] = True
            following += _build(index, built, file)
        if not following:
            break
        pending = following
    ordered = sorted(built.values(), key = lambda entry: (entry.mnemonic, entry.owner, [output.short_path for output in entry.action.outputs.to_list()]))
    return struct(built = ordered, producers = index.producers)

def _selected(graph, mnemonic, owner, producing):
    return [
        entry
        for entry in graph.built
        if entry.mnemonic == mnemonic and
           (not owner or entry.owner.endswith(":" + owner)) and
           (not producing or [output for output in entry.action.outputs.to_list() if _matches(output, producing)])
    ]

def _godot(graph, mnemonics, readers):
    """
    Return the built Godot actions a check covers.

    Without mnemonics, that means all of them. The readers' actions are left out.
    """
    return [
        entry
        for entry in graph.built
        if entry.mnemonic.startswith("Godot") and
           (not mnemonics or entry.mnemonic in mnemonics) and
           entry.mnemonic not in readers
    ]

def _describe(entry):
    return "%s of %s producing %s" % (entry.mnemonic, entry.owner, ", ".join([output.short_path for output in entry.action.outputs.to_list()]))

def _written_inputs(graph, entry):
    """Return the contents of the inputs that analysis writes for a built action."""
    producers = [graph.producers.get(file) for file in entry.inputs]
    return [
        producer.action.content or ""
        for producer in producers
        if producer and producer.action.mnemonic in _GENERATED
    ]

def _command_mentions(graph, entry, text):
    return any([text in part for part in (entry.action.argv or []) + _written_inputs(graph, entry)])

def _expect_some(env, entries, mnemonic, owner, producing):
    env.expect.where(mnemonic = mnemonic, owner = owner, producing = producing).that_int(len(entries)).is_greater_than(0)

def expect_built_reads(env, graph, mnemonic, path, *, owner = None, producing = None):
    """
    Assert that every built action with the mnemonic declares the file as an input.

    Args:
        env: The rules_testing environment.
        graph: The result of build_graph.
        mnemonic: The action that a change of the file must rerun.
        path: The file's short path, or a suffix of it after a slash.
        owner: The name of the target that owns the action, if only its action counts.
        producing: The short path, or a suffix, of an output of the action, if only
            that action counts.
    """
    entries = _selected(graph, mnemonic, owner, producing)
    _expect_some(env, entries, mnemonic, owner, producing)
    for entry in entries:
        env.expect.where(action = _describe(entry), path = path).that_bool(
            bool([file for file in entry.inputs if _matches(file, path)]),
        ).equals(True)

def expect_built_reads_output_of(env, graph, mnemonic, producer, *, owner = None, producer_owner = None, producing = None):
    """
    Assert that every built action with the mnemonic reads an output of a producer.

    Args:
        env: The rules_testing environment.
        graph: The result of build_graph.
        mnemonic: The action that a changed output of the producer must rerun.
        producer: The mnemonic of the action whose output it reads.
        owner: The name of the target that owns the reading action, if only its action
            counts.
        producer_owner: The name of the target that owns the producer, if only its
            action counts.
        producing: The short path, or a suffix, of an output of the producer, if only
            that producer counts.
    """
    producers = _selected(graph, producer, producer_owner, producing)
    _expect_some(env, producers, producer, producer_owner, producing)
    outputs = {output: True for entry in producers for output in entry.action.outputs.to_list()}
    entries = _selected(graph, mnemonic, owner, None)
    _expect_some(env, entries, mnemonic, owner, None)
    for entry in entries:
        env.expect.where(action = _describe(entry), producer = producer).that_bool(
            bool([file for file in entry.inputs if file in outputs]),
        ).equals(True)

def expect_built_not_read(env, graph, path, *, readers = [], mnemonics = []):
    """
    Assert that the file is a direct input of no built Godot action but the readers.

    Args:
        env: The rules_testing environment.
        graph: The result of build_graph.
        path: The file's short path, or a suffix of it after a slash.
        readers: The mnemonics a change of the file reruns; their actions are skipped.
        mnemonics: The actions that a change of the file must leave cached; an empty
            list means every built Godot action.
    """
    for entry in _godot(graph, mnemonics, readers):
        env.expect.where(action = _describe(entry), path = path).that_bool(
            bool([file for file in entry.inputs if _matches(file, path)]),
        ).equals(False)

def _reads_changed(entry, changed, path):
    return bool([file for file in entry.inputs if file in changed or _matches(file, path)])

def _downstream(graph, path):
    """Return the built actions that read the file, directly or through outputs downstream of it."""
    changed = {}
    reached = {}

    # Each round marks the actions one more level downstream of the file.
    for _ in range(len(graph.built) + 1):
        newly = [
            entry
            for entry in graph.built
            if entry.action not in reached and _reads_changed(entry, changed, path)
        ]
        if not newly:
            break
        for entry in newly:
            reached[entry.action] = True
            for output in entry.action.outputs.to_list():
                changed[output] = True
    return reached

def expect_unreached(env, graph, path, *, readers = [], mnemonics = []):
    """
    Assert that the file reaches no built Godot action but the readers, directly or through outputs.

    Args:
        env: The rules_testing environment.
        graph: The result of build_graph.
        path: The file's short path, or a suffix of it after a slash.
        readers: The mnemonics a change of the file reruns; their actions are skipped.
        mnemonics: The actions that a change of the file must leave cached; an empty
            list means every built Godot action.
    """
    reached = _downstream(graph, path)
    for entry in _godot(graph, mnemonics, readers):
        env.expect.where(action = _describe(entry), path = path).that_bool(entry.action in reached).equals(False)

def expect_built_mentions(env, graph, mnemonic, text, *, mentioned = True, owner = None):
    """
    Assert whether the command of every built action with the mnemonic contains a text.

    The command is the action's arguments and the content of the inputs that analysis
    writes for it, such as a JSON manifest.

    Args:
        env: The rules_testing environment.
        graph: The result of build_graph.
        mnemonic: An action mnemonic.
        text: A substring of an argument or of a written input, such as a setting.
        mentioned: Whether the text must appear.
        owner: The name of the target that owns the action, if only its action counts.
    """
    entries = _selected(graph, mnemonic, owner, None)
    _expect_some(env, entries, mnemonic, owner, None)
    for entry in entries:
        env.expect.where(action = _describe(entry), text = text).that_bool(_command_mentions(graph, entry, text)).equals(mentioned)

def expect_mentioned_only_by(env, graph, text, mnemonics):
    """
    Assert that no built Godot action but the ones with the mnemonics mentions a text.

    Args:
        env: The rules_testing environment.
        graph: The result of build_graph.
        text: A substring of an argument or of a written input, such as a setting.
        mnemonics: The actions a change of the text reruns.
    """
    for entry in _godot(graph, [], mnemonics):
        env.expect.where(action = _describe(entry), text = text).that_bool(_command_mentions(graph, entry, text)).equals(False)

def expect_not_built(env, graph, mnemonic, *, owner = None):
    """
    Assert that a build of the target runs no action with the mnemonic.

    Args:
        env: The rules_testing environment.
        graph: The result of build_graph.
        mnemonic: An action mnemonic.
        owner: The name of the target that owns the action, if only its action counts.
    """
    env.expect.where(mnemonic = mnemonic, owner = owner).that_collection(
        [_describe(entry) for entry in _selected(graph, mnemonic, owner, None)],
    ).contains_exactly([])

# ==== Path mapping ============================================================

def _mapped(text):
    """Remove the configuration from each output path in text, as path mapping does."""
    parts = text.split("bazel-out/")
    return parts[0] + "".join(["bazel-out/cfg/" + part.partition("/")[2] for part in parts[1:]])

def _output_paths(action):
    return tuple(sorted([file.short_path for file in action.outputs.to_list()]))

def _cache_key(action, written):
    """
    Return the parts of an action that go into its cache key, as JSON.

    `written` maps each path that analysis writes to its content.
    """
    inputs = action.inputs.to_list()
    return json.encode({
        "argv": [_mapped(argument) for argument in action.argv or []],
        "inputs": sorted([mapped_path(file) for file in inputs]),
        "written": sorted([written[file.path] for file in inputs if file.path in written]),
    })

def mapped_cache_keys(target, mnemonics):
    """
    Return what decides the cache key of each reached action under path mapping.

    Path mapping removes the configuration from the output paths of an action's command
    line and inputs, but not from what a file it reads holds, so the manifests that
    analysis writes compare as written.

    Args:
        target: The target under test, analyzed with the godot_actions aspect.
        mnemonics: The mnemonics of the actions to include.

    Returns:
        A dict from (owner, mnemonic, output short paths) to the action's facts as JSON.
    """
    every = target[GodotActionsInfo].every.to_list()
    written = {
        entry.action.outputs.to_list()[0].path: entry.action.content
        for entry in every
        if entry.action.mnemonic == "FileWrite"
    }
    return {
        (entry.owner, entry.action.mnemonic, _output_paths(entry.action)): _cache_key(entry.action, written)
        for entry in every
        if entry.action.mnemonic in mnemonics
    }

def written_manifests(target, suffix):
    """
    Return the JSON manifests a target reaches whose paths end in a suffix.

    Args:
        target: The target under test, analyzed with the godot_actions aspect.
        suffix: The end of the manifests' paths, such as ".resource_paths.json"; a
            leading slash matches whole file names.

    Returns:
        A dict from each manifest's path to its decoded content.
    """
    return {
        entry.action.outputs.to_list()[0].path: json.decode(entry.action.content)
        for entry in target[GodotActionsInfo].every.to_list()
        if entry.action.mnemonic == "FileWrite" and
           entry.action.outputs.to_list()[0].path.endswith(suffix)
    }

def import_manifests(target, unit):
    """
    Return the import manifests of a unit that a target reaches, one per import.

    A unit's resources target declares its import together with the manifest
    `<unit>.import.json`, which analysis writes and the import reads; one manifest path
    is one configured resources target and so one import action.

    Args:
        target: The target under test, analyzed with the godot_actions aspect.
        unit: The name of the godot_resources target that declares the unit.

    Returns:
        A dict from each manifest's path to its decoded content.
    """
    return written_manifests(target, "/" + unit + ".import.json")

def expect_import_lists(env, graph, unit, resource_path, *, listed = True):
    """
    Assert whether the import manifest of a unit lists a resource path as its own.

    Analysis does not show an import's declared inputs. Its manifest, `<unit>.import.json`,
    which analysis writes, lists the unit's own resource paths, the files the import stages
    for that unit and whose edits rerun it.

    Args:
        env: The rules_testing environment.
        graph: The result of build_graph.
        unit: The name of the godot_resources target that declares the unit.
        resource_path: A resource path, such as main/icon.svg.
        listed: Whether the manifest must list it.
    """
    manifests = [
        entry.action
        for file, entry in graph.producers.items()
        if file.basename == unit + ".import.json" and entry.action.mnemonic == "FileWrite"
    ]
    env.expect.where(unit = unit).that_int(len(manifests)).is_greater_than(0)
    for manifest in manifests:
        env.expect.where(unit = unit, resource_path = resource_path).that_bool(
            resource_path in json.decode(manifest.content)["outputs"],
        ).equals(listed)
