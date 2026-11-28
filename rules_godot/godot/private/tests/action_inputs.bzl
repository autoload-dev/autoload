"""
Action-input assertions for analysis tests of cache reuse and invalidation.

A relevant edit reruns an action only when the edited file or setting is one of the
action's declared inputs or arguments; an unrelated edit leaves the action cached when it is
not. The `godot_actions` aspect collects the Godot actions a target reaches through its
dependency graph, so a test can assert both sides for the action a change must or must not
rerun. built_graph.bzl narrows them to the actions that a build of the target runs.

Sections: Action aspect, Path mapping.
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
        graph: The result of build_graph from built_graph.bzl.
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
