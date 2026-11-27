"""
Every action an application reaches, for claims about what an edit or a setting reaches.

`//godot/private/tests:action_inputs.bzl` collects the Godot actions of a target. Packaging
claims also name rules_android, rules_apple and C++ actions, and an edit reaches a bundle
through the outputs of other actions, so this aspect collects every action and the target
platforms it configures.
"""

visibility("//godot/platforms/private/tests/...")

_ReachedActionsInfo = provider(
    doc = "Actions a target reaches through its dependencies, and the target platforms of those dependencies.",
    fields = {
        "actions": "depset of struct(owner, action, platform), platform being the target platform label string of the owner's configuration",
        "platforms": "depset of target platform label strings",
    },
)

def _dependencies(value):
    if type(value) == "list":
        return value
    if type(value) == "dict":
        return value.keys() + value.values()
    return [value]

def _reached_actions_impl(target, ctx):
    transitive = []
    platforms = []
    for attribute in dir(ctx.rule.attr):
        for dependency in _dependencies(getattr(ctx.rule.attr, attribute)):
            if type(dependency) == "Target" and _ReachedActionsInfo in dependency:
                transitive.append(dependency[_ReachedActionsInfo].actions)
                platforms.append(dependency[_ReachedActionsInfo].platforms)
    platform = str(ctx.fragments.platform.platform)
    own = [struct(owner = str(target.label), action = action, platform = platform) for action in target.actions]
    return [_ReachedActionsInfo(
        actions = depset(own, transitive = transitive),
        platforms = depset([platform], transitive = platforms),
    )]

reached_actions = aspect(
    implementation = _reached_actions_impl,
    attr_aspects = ["*"],
    fragments = ["platform"],
    doc = "Collect every action and target platform a target reaches through its dependency attributes.",
)

def reached(target):
    """Return every struct(owner, action, platform) the target reaches."""
    return target[_ReachedActionsInfo].actions.to_list()

def platform_slice_cpus(target):
    """Return the CPUs of the platform slices whose configurations the target reaches."""
    return sorted({
        cpu: None
        for platform in target[_ReachedActionsInfo].platforms.to_list()
        for cpu in ["arm64", "x86_64"]
        if platform.endswith(".platform_slice_" + cpu)
    })

# Android resource processing is packaging work, and the Python bytecode of build tools
# belongs to the tool's own build; neither compiles the application's native code.
_NOT_NATIVE_COMPILATION = [
    "StarlarkMergeCompiledAndroidResources",
    "CompileAndroidResources",
    "FixDatabindingCompiledResources",
    "PyCompile",
]

def is_compilation(mnemonic):
    """Whether an action compiles source code: C, C++, Objective-C or Swift."""
    return (
        ("Compile" in mnemonic or mnemonic.startswith("SwiftDriver")) and
        mnemonic not in _NOT_NATIVE_COMPILATION
    )

def reads(action, path):
    """Whether one of the action's inputs has the short path, or ends with it after a slash."""
    return any([
        file.short_path == path or file.short_path.endswith("/" + path)
        for file in action.inputs.to_list()
    ])

def written_contents(entries):
    """
    Return the text that file-writing actions write.

    Args:
        entries: struct(owner, action) values, as reached returns them.

    Returns:
        A dict from each written file's path to its text; for an expanded template, its
        substitutions as JSON.
    """
    contents = {}
    for entry in entries:
        action = entry.action
        if action.mnemonic == "FileWrite" and action.content != None:
            text = action.content
        elif action.mnemonic == "TemplateExpand":
            text = json.encode(action.substitutions)
        else:
            continue
        for output in action.outputs.to_list():
            contents[output.path] = text
    return contents

def mentions(action, text, contents):
    """Whether the action's arguments, or a file it reads that an action writes, contain text."""
    if any([text in argument for argument in action.argv or []]):
        return True
    return any([
        text in contents.get(file.path, "")
        for file in action.inputs.to_list()
    ])

def bundle_closure(target):
    """
    Return what the target's default outputs are built from.

    Args:
        target: The target under test, analyzed with the reached_actions aspect.

    Returns:
        struct(files, actions): the short paths of every file the default outputs depend
        on through the reached actions, and those actions.
    """
    producers = {}
    for entry in reached(target):
        for output in entry.action.outputs.to_list():
            producers[output.path] = entry.action
    pending = target[DefaultInfo].files.to_list()
    seen = {}
    files = {}
    actions = {}

    # Starlark has no while loop; the bound exceeds any application's file count.
    for _ in range(10000000):
        if not pending:
            break
        file = pending.pop()
        if file.path in seen:
            continue
        seen[file.path] = True
        files[file.short_path] = True
        action = producers.get(file.path)
        if action == None:
            continue
        key = action.outputs.to_list()[0].path
        if key not in actions:
            actions[key] = action
            pending.extend(action.inputs.to_list())
    return struct(files = files, actions = actions.values())

def _without_configuration(text):
    """Replace each output directory's configuration name, which a test transition sets."""
    parts = text.split("bazel-out/")
    return parts[0] + "".join(["bazel-out/<configuration>/" + part.partition("/")[2] for part in parts[1:]])

# Compile actions whose inputs Bazel extends with discovered headers after they run.
_DISCOVERS_INPUTS = ["CppCompile", "ObjcCompile"]
_HEADER_EXTENSIONS = ["h", "hh", "hpp", "hxx", "inc", "inl", "ipp", "tcc"]

def _action_keys(target, selected):
    """
    Return what decides whether each selected action reruns, by owner, mnemonic and outputs.

    An action reruns when its command line, its inputs or its outputs change, or when a file
    it reads that another action writes changes. Each test configuration is applied through
    a transition, which names the output directories after the settings it changes; a
    command-line setting does not, so the configuration name is removed from paths.

    Args:
        target: The target under test, analyzed with the reached_actions aspect.
        selected: A function of struct(owner, action) that says whether to include the
            action.

    Returns:
        A dict from a description of each action to its rerun-relevant facts as JSON.
    """
    entries = reached(target)
    contents = written_contents(entries)
    keys = {}
    for entry in entries:
        action = entry.action
        if not selected(entry):
            continue
        outputs = sorted([file.short_path for file in action.outputs.to_list()])
        inputs = action.inputs.to_list()
        if action.mnemonic in _DISCOVERS_INPUTS:
            # After a compile has run in this Bazel server, its inputs also list the headers
            # it read, so headers are left out; argv and sources still decide the comparison.
            inputs = [file for file in inputs if file.extension not in _HEADER_EXTENSIONS]
        name = "%s %s %s" % (entry.owner, action.mnemonic, outputs)
        keys[name] = json.encode({
            "argv": [_without_configuration(argument) for argument in action.argv or []],
            "inputs": sorted([file.short_path for file in inputs]),
            "written": sorted([
                _without_configuration(contents[file.path])
                for file in inputs
                if file.path in contents
            ]),
        })
    return keys

def expect_same_actions(env, first, second, selected):
    """
    Assert that two analyzed targets, or two configurations of one, have the same selected actions.

    Args:
        env: The rules_testing environment.
        first: One target, analyzed with the reached_actions aspect.
        second: The other target, analyzed the same way.
        selected: A function of struct(owner, action) that says whether to compare the
            action.
    """
    expected = _action_keys(first, selected)
    actual = _action_keys(second, selected)
    env.expect.that_int(len(expected), expr = "compared actions").is_greater_than(0)
    env.expect.that_collection(sorted(actual.keys()), expr = "actions").contains_exactly(sorted(expected.keys()))
    for name, facts in expected.items():
        if name in actual:
            env.expect.where(action = name).that_str(actual[name]).equals(facts)
