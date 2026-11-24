"""
Prototype: one shared tree repository per source, patch list and row of source recipes.

Remote and disk cache keys contain every path of an action, and a recipe repository's
paths contain its name. The recipes of one source, patch list and row compile their
shareable sources in a tree repository instead, which declares the union of their work
under names that digest what each action reads (tools/engine/shared_objects.py).
"""

load("//godot/engine/private:source_build_rows.bzl", "source_build_declarations")
load("//godot/private:patches.bzl", "apply_repository_patches")

visibility(["//godot/..."])

# The godot_engine_source_build parameters every recipe of a source build takes.
_COMMON = {
    "enabled_modules": [],
    "default_modules": False,
    "custom_modules": {},
    "patches": [],
    "patch_strip": 1,
    "renderers": [],
    "build_profile": None,
    "build_options": {},
    "build_name": "custom",
    "python": None,
    "configure_timeout": 600,
}

def expand_source_builds(declarations):
    """
    Replace each godot_engine_source_build declaration by the repositories it declares.

    Args:
        declarations: Repository declarations, structs with `rule` and `attrs`.

    Returns:
        The declarations without godot_engine_source_build.
    """
    result = []
    for declaration in declarations:
        if declaration.rule != "godot_engine_source_build":
            result.append(declaration)
            continue
        attrs = declaration.attrs
        result.extend(source_build_declarations(
            attrs["name"],
            attrs["source"],
            attrs["platforms"],
            attrs.get("cpus", []),
            attrs.get("build_targets", []),
            attrs.get("ios_environments", []),
            {key: attrs.get(key, default) for key, default in _COMMON.items()},
            lock_file = attrs.get("lock_file"),
            engine = attrs.get("engine", ""),
        ))
    return result

def _row(attrs):
    return "_".join([part for part in [attrs["platform"], attrs["cpu"], attrs.get("environment", ""), attrs["build_target"]] if part])

def _tree_key(attrs):
    """What the recipes that share a tree have in common: source, patches and row."""
    return repr([
        str(attrs["source"]),
        [str(patch) for patch in attrs.get("patches", [])],
        attrs.get("patch_strip", 1),
        _row(attrs),
    ])

def _new_tree(key, attrs):
    return dict(
        name = "godot_tree_%s_%x" % (_row(attrs), hash(key) & 0xffffffff),
        source = attrs["source"],
        patches = attrs.get("patches", []),
        patch_strip = attrs.get("patch_strip", 1),
        custom_modules = {},
        build_profiles = [],
        recipes = [],
    )

def _join(tree, attrs):
    """Add a recipe to its tree: its name, custom modules and build profile."""
    tree["custom_modules"].update(attrs.get("custom_modules", {}))
    profile = attrs.get("build_profile")
    if profile and profile not in tree["build_profiles"]:
        tree["build_profiles"].append(profile)
    tree["recipes"].append(attrs["name"])

def with_shared_trees(declarations):
    """
    Give the recipes of each source, patch list and row a shared tree repository.

    Args:
        declarations: Repository declarations, structs with `rule` and `attrs`.

    Returns:
        The declarations, each recipe naming its tree, and the tree repositories.
    """
    trees = {}
    result = []
    for declaration in declarations:
        if declaration.rule != "godot_engine_build":
            result.append(declaration)
            continue
        attrs = dict(declaration.attrs)
        key = _tree_key(attrs)
        tree = trees.setdefault(key, _new_tree(key, attrs))
        _join(tree, attrs)
        attrs["tree"] = tree["name"]
        result.append(struct(rule = declaration.rule, attrs = attrs))
    return result + [struct(rule = "godot_engine_tree", attrs = tree) for tree in trees.values()]

def _tree_command(ctx):
    """The shared_tree.py command that adds the recipes' files and the BUILD file."""
    command = [
        str(ctx.which("python3")),
        str(ctx.path(ctx.attr._shared_tree)),
        "--root",
        str(ctx.path(".")),
        "--macros",
        str(ctx.attr._macros),
    ]
    for module, name in ctx.attr.custom_modules.items():
        marker = ctx.path(module)
        ctx.watch_tree(marker.dirname)
        command.extend(["--custom-module", name + "=" + str(marker.dirname)])
    for profile in ctx.attr.build_profiles:
        command.extend(["--profile", str(ctx.path(profile))])
    for recipe in ctx.attr.recipes:
        command.extend(["--recipe", recipe])
    return command

def engine_tree_impl(ctx, *, _fail = fail):
    """
    Extract and patch the source tree that a row's recipes share.

    Args:
        ctx: Repository rule context of godot_engine_tree.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        The repository's metadata.
    """
    descriptor = json.decode(ctx.read(ctx.path(ctx.attr.source)))
    ctx.extract(ctx.path(ctx.attr.source.same_package_label(descriptor["archive"])), stripPrefix = descriptor["strip_prefix"])
    if not apply_repository_patches(ctx, _fail = _fail):
        return None
    ctx.watch(ctx.path(ctx.attr._shared_tree))
    ctx.watch(ctx.path(ctx.attr._build_profile))
    result = ctx.execute(_tree_command(ctx), quiet = True)
    if result.return_code:
        _fail("Preparing the shared tree failed:\n%s\n%s" % (result.stdout, result.stderr))
        return None
    return ctx.repo_metadata(reproducible = True)
