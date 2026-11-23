"""The valid source-recipe rows a source build can cover, and their selection."""

load("//godot/engine/private:hub.bzl", "component")

visibility(["//godot/..."])

PLATFORMS = ["linux", "macos", "android", "ios"]
CPUS = ["arm64", "x86_64"]
BUILD_TARGETS = ["editor", "template_debug", "template_release"]
IOS_ENVIRONMENTS = ["device", "simulator"]

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
    for cpu in CPUS
    for build_target in BUILD_TARGETS
] + [
    _row("android", cpu, build_target)
    for cpu in CPUS
    for build_target in ["template_debug", "template_release"]
] + [
    _row("ios", cpu, build_target, environment)
    for environment, cpus in [("device", ["arm64"]), ("simulator", CPUS)]
    for cpu in cpus
    for build_target in ["template_debug", "template_release"]
]

def _check(name, field, values, allowed, _fail):
    unknown = [value for value in values if value not in allowed]
    if unknown:
        _fail("Godot source build %r: unknown %s %s; expected some of %s" % (name, field, unknown, allowed))
        return False
    return True

def select_rows(name, platforms, cpus = [], build_targets = [], ios_environments = [], *, _fail = fail):
    """
    Return the valid rows a source build's filters select.

    Args:
        name: Source build name, for diagnostics.
        platforms: Required nonempty list of linux, macos, android or ios.
        cpus: Optional CPU filter; empty selects all.
        build_targets: Optional editor/template_debug/template_release filter; empty selects all.
        ios_environments: Optional device/simulator filter for iOS rows; empty selects both.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        The selected row structs, with platform, cpu, build_target, environment and name;
        None after an error.
    """
    if not platforms:
        _fail("Godot source build %r: platforms must name at least one of %s" % (name, PLATFORMS))
        return None
    for field, values, allowed in [
        ("platforms", platforms, PLATFORMS),
        ("cpus", cpus, CPUS),
        ("build_targets", build_targets, BUILD_TARGETS),
        ("ios_environments", ios_environments, IOS_ENVIRONMENTS),
    ]:
        if not _check(name, field, values, allowed, _fail):
            return None
    rows = [
        row
        for row in ROWS
        if row.platform in platforms and
           (not cpus or row.cpu in cpus) and
           (not build_targets or row.build_target in build_targets) and
           (not ios_environments or not row.environment or row.environment in ios_environments)
    ]
    if not rows:
        _fail("Godot source build %r: the filters select no valid row" % name)
        return None
    return rows

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
        "shell": "@%s_android_shell//:%s.aar" % (name, variant),
        "engine_libraries": {},
    })["engine_libraries"][recipe.row.cpu] = "@%s//:godot" % recipe.repository

def plan_rows(name, rows, version = ""):
    """
    Return the recipes, hub slots and Android runtimes of source recipes for the given rows.

    Args:
        name: Prefix of the recipe repositories and of the Android shell repository.
        rows: Rows of ROWS.
        version: Canonical Godot version of the sources; empty takes the hub's
            version_source descriptor.

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

def recipe_declarations(name, source, plan, common, lock_file = None):
    """
    Return the recipe and Android shell repositories of a plan_rows result.

    Args:
        name: The name plan_rows took.
        source: Label of the `:source.json` descriptor of a godot_engine_source repository.
        plan: A plan_rows result.
        common: The godot_engine_build attributes every recipe takes: enabled_modules,
            custom_modules, patches, patch_strip, renderers, build_profile, build_options, build_name, python and
            configure_timeout.
        lock_file: Optional Label of the lock file that pins every recipe.

    Returns:
        A list of structs with `rule`, the name of a repository rule, and `attrs`, its
        keyword arguments.
    """
    pinning = {}
    if lock_file:
        pinning = dict(lock_file = lock_file, repin = "@%s//:pin" % name)
    declarations = [
        struct(rule = "godot_engine_build", attrs = dict(
            name = recipe.repository,
            source = source,
            platform = recipe.row.platform,
            cpu = recipe.row.cpu,
            build_target = recipe.row.build_target,
            environment = recipe.row.environment,
            lock_key = recipe.row.name if lock_file else "",
            **(common | pinning)
        ))
        for recipe in plan.recipes
    ]
    if plan.android:
        declarations.append(struct(rule = "godot_android_shell", attrs = dict(
            name = name + "_android_shell",
            source = source,
            patches = common["patches"],
            patch_strip = common["patch_strip"],
        )))
    return declarations

def source_build_declarations(name, source, platforms, cpus, build_targets, ios_environments, common, lock_file = None, engine = "", *, _fail = fail):
    """
    Return the repositories godot_engine_source_build declares.

    Args:
        name: Hub repository name and the prefix of the recipe repositories.
        source: Label of the `:source.json` descriptor of a godot_engine_source repository.
        platforms: As for select_rows.
        cpus: As for select_rows.
        build_targets: As for select_rows.
        ios_environments: As for select_rows.
        common: The godot_engine_build attributes every recipe takes: enabled_modules,
            custom_modules, patches, patch_strip, renderers, build_profile, build_options, build_name, python and
            configure_timeout.
        lock_file: Optional Label of the lock file that pins every recipe; the hub then
            declares `:pin`, which writes it.
        engine: Name of the engine the hub's components belong to; empty for the default
            engine.
        _fail: Replaces fail in Starlark unit tests.

    Returns:
        A list of structs with `rule`, the name of a repository rule, and `attrs`, its
        keyword arguments; None after an error.
    """
    rows = select_rows(name, platforms, cpus, build_targets, ios_environments, _fail = _fail)
    if rows == None:
        return None
    plan = plan_rows(name, rows)
    declarations = recipe_declarations(name, source, plan, common, lock_file)
    hub = dict(
        name = name,
        display_name = name,
        components = json.encode(plan.slots),
        android_runtimes = json.encode(plan.android),
        version_source = source,
        engine = engine,
    )
    if lock_file:
        hub["pin_recipes"] = json.encode({
            "@%s//:pin" % recipe.repository: recipe.row.name
            for recipe in plan.recipes
        })
        hub["lock"] = "/".join([part for part in [lock_file.package, lock_file.name] if part])
    declarations.append(struct(rule = "engine_hub", attrs = hub))
    return declarations
