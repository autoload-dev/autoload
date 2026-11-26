"""The valid source-recipe rows of an engine, and the recipes, slots and pins that cover them."""

load("//godot/engine/private:hub.bzl", "component")

visibility(["//godot/..."])

_CPUS = ["arm64", "x86_64"]

_BUILD_TARGETS = ["editor", "template_debug", "template_release"]

def _row(platform, cpu, build_target, environment = ""):
    return struct(
        platform = platform,
        cpu = cpu,
        build_target = build_target,
        environment = environment,
        name = "_".join([part for part in [platform, cpu, environment, build_target] if part]),
    )

# Editors exist for desktop editor platforms only; mobile rows are templates. iOS device
# rows are arm64; simulators run on either Mac CPU.
ROWS = [
    _row(platform, cpu, build_target)
    for platform in ["linux", "macos"]
    for cpu in _CPUS
    for build_target in _BUILD_TARGETS
] + [
    _row("android", cpu, build_target)
    for cpu in _CPUS
    for build_target in ["template_debug", "template_release"]
] + [
    _row("ios", cpu, build_target, environment)
    for environment, cpus in [("device", ["arm64"]), ("simulator", _CPUS)]
    for cpu in cpus
    for build_target in ["template_debug", "template_release"]
]

def _variant(row):
    return row.build_target.removeprefix("template_")

def slot_name(row):
    """
    Return the hub component name of a row's slot.

    Args:
        row: Row of ROWS.

    Returns:
        The slot name, such as runtime_ios_arm64_simulator_debug.
    """
    if row.build_target == "editor":
        return "editor_%s_%s" % (row.platform, row.cpu)
    return "_".join([part for part in ["runtime", row.platform, row.cpu, row.environment, _variant(row)] if part])

def _slot(recipe, version):
    """The hub slot of a recipe."""
    row = recipe.row
    if row.build_target == "editor":
        return component(
            role = "editor",
            name = slot_name(row),
            payload = "@%s//:godot" % recipe.repository,
            platform = row.platform,
            cpu = row.cpu,
            version = version,
        )
    payload = "@%s//:godot" % recipe.repository
    if row.platform == "android":
        payload = "//android:" + _variant(row)
    elif row.platform == "ios":
        payload = "@%s//:engine_library" % recipe.repository
    return component(
        role = "runtime",
        name = slot_name(row),
        payload = payload,
        platform = row.platform,
        cpu = row.cpu,
        version = version,
        variant = _variant(row),
        environment = row.environment,
    )

def _add_android_library(android, name, recipe):
    """Add an Android recipe's engine library to the hub's Android runtime of its variant."""
    variant = _variant(recipe.row)
    android.setdefault(variant, {
        "shell": "@%s_source_android_shell//:%s.aar" % (name, variant),
        "engine_libraries": {},
    })["engine_libraries"][recipe.row.cpu] = "@%s//:godot" % recipe.repository

def plan_rows(name, rows, version):
    """
    Return the recipes, hub slots and Android runtimes of source recipes for the given rows.

    Args:
        name: The engine's name: the hub's, and the prefix of the recipe repositories and of
            the Android shell repository.
        rows: Rows of ROWS.
        version: Canonical Godot version of the sources, as their version.py names it.

    Returns:
        A struct of `recipes`, one struct per godot_engine_build repository with its
        `repository` name and row, `slots`, the hub's component descriptions, and `android`,
        the hub's Android runtimes by variant.
    """
    recipes = []
    slots = []
    android = {}
    for row in rows:
        recipe = struct(repository = "%s_%s" % (name, row.name), row = row)
        recipes.append(recipe)
        slots.append(_slot(recipe, version))
        if row.platform == "android" and row.build_target != "editor":
            _add_android_library(android, name, recipe)
    return struct(recipes = recipes, slots = slots, android = android)

def _recipe_profiles(row, runtime_profiles):
    """The runtime profiles a recipe declares variants of: a runtime's, not an editor's."""
    return {} if row.build_target == "editor" else runtime_profiles

def recipe_declarations(name, source, plan, common, lock_file = None, runtime_profiles = {}):
    """
    Return the recipe and Android shell repositories of a plan_rows result.

    Args:
        name: The name plan_rows took.
        source: Label of the `:source.json` descriptor of a godot_engine_source repository.
        plan: A plan_rows result.
        common: The godot_engine_build attributes every recipe takes: enabled_modules,
            default_modules, custom_modules, patches, patch_strip, renderers, build_options
            and build_name.
        lock_file: Optional Label of the lock file that pins every recipe.
        runtime_profiles: The engine's registered runtime profiles: each label string's
            build options as JSON; each runtime recipe declares a runtime variant of each.

    Returns:
        A list of structs with `rule`, the name of a repository rule, and `attrs`, its
        keyword arguments.
    """
    pins = {}
    if lock_file:
        pins = dict(lock_file = lock_file, repin = "@%s//:pin" % name)
    declarations = [
        struct(rule = "godot_engine_build", attrs = dict(
            name = recipe.repository,
            source = source,
            platform = recipe.row.platform,
            cpu = recipe.row.cpu,
            build_target = recipe.row.build_target,
            environment = recipe.row.environment,
            lock_key = recipe.row.name if lock_file else "",
            runtime_profiles = _recipe_profiles(recipe.row, runtime_profiles),
            **(common | pins)
        ))
        for recipe in plan.recipes
    ]
    if plan.android:
        declarations.append(struct(rule = "godot_android_shell", attrs = dict(
            name = name + "_source_android_shell",
            source = source,
            patches = common["patches"],
            patch_strip = common["patch_strip"],
        )))
    return declarations

def pinning(plan, lock_file, runtime_profiles):
    """
    Return the hub attributes that let `@<hub>//:pin` write the lock file of a plan's recipes.

    Args:
        plan: A plan_rows result.
        lock_file: Optional Label of the lock file that pins every recipe.
        runtime_profiles: The engine's registered runtime profiles, as recipe_declarations
            takes them.

    Returns:
        The engine_hub attributes of its pins; none without a lock file.
    """
    if not lock_file:
        return {}
    return {
        "pin_recipes": json.encode({
            "@%s//:pin" % recipe.repository: recipe.row.name
            for recipe in plan.recipes
        }),
        # Each runtime variant's pin target: its recipe's key and its runtime profile.
        "pin_variants": json.encode({
            "@%s//:pin_variant_%d" % (recipe.repository, index): [recipe.row.name, profile]
            for recipe in plan.recipes
            for index, profile in enumerate(sorted(_recipe_profiles(recipe.row, runtime_profiles)))
        }),
        # Each recipe's platform, by its key, for the hub's :pin_<platform>.
        "pin_platforms": json.encode({recipe.row.name: recipe.row.platform for recipe in plan.recipes}),
        "lock": "/".join([part for part in [lock_file.package, lock_file.name] if part]),
    }
