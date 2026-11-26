"""godot_engine_source_build selects valid rows and declares one recipe per row, a shell and a hub."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")

# buildifier: disable=bzl-visibility
load(
    "//godot/engine/private:source_build_rows.bzl",
    "ROWS",
    "select_rows",
    "source_build_declarations",
)

# buildifier: disable=bzl-visibility
load("//godot/private/tests:mocks.bzl", "mocks")

_SOURCE = "@godot_sources//:source.json"

_COMMON = {
    "enabled_modules": ["gdscript", "text_server_fb", "svg"],
    "custom_modules": {"//modules/rive:config.py": "rive"},
    "patches": ["//patches:fork.patch"],
    "patch_strip": 2,
    "build_options": {"production": "yes"},
    "build_name": "studio",
    "python": "//tools:python3",
    "configure_timeout": 900,
}

def _declare(platforms, cpus = [], build_targets = [], ios_environments = [], lock_file = None, engine = "", version = ""):
    errors, fail_ = mocks.errors()
    declarations = source_build_declarations(
        "godot_source_build",
        _SOURCE,
        platforms,
        cpus,
        build_targets,
        ios_environments,
        _COMMON,
        lock_file = lock_file,
        engine = engine,
        version = version,
        _fail = fail_,
    )
    return declarations, errors

def _names(rows):
    return [row.name for row in rows]

def _test_ios_environments_filter_ios_rows(env):
    rows = select_rows(
        "godot_source_build",
        ["ios", "linux"],
        cpus = ["arm64"],
        build_targets = ["template_release"],
        ios_environments = ["simulator"],
    )
    env.expect.that_collection(_names(rows)).contains_exactly([
        "linux_arm64_template_release",
        "ios_arm64_simulator_template_release",
    ])

def _test_empty_filters_select_every_valid_row(env):
    env.expect.that_collection(_names(select_rows("godot_source_build", ["ios"]))).contains_exactly([
        "ios_arm64_device_template_debug",
        "ios_arm64_device_template_release",
        "ios_arm64_simulator_template_debug",
        "ios_arm64_simulator_template_release",
        "ios_x86_64_simulator_template_debug",
        "ios_x86_64_simulator_template_release",
    ])
    env.expect.that_collection(_names(select_rows("godot_source_build", ["linux"]))).contains_exactly([
        "linux_%s_%s" % (cpu, target)
        for cpu in ["arm64", "x86_64"]
        for target in ["editor", "template_debug", "template_release"]
    ])
    env.expect.that_collection(_names(select_rows("godot_source_build", ["android"]))).contains_exactly([
        "android_%s_%s" % (cpu, target)
        for cpu in ["arm64", "x86_64"]
        for target in ["template_debug", "template_release"]
    ])
    every = select_rows("godot_source_build", ["linux", "macos", "android", "ios"])
    env.expect.that_collection(_names(every)).contains_exactly(_names(ROWS))

def _test_android_rows_declare_one_shell(env):
    declarations, errors = _declare(["android"], build_targets = ["template_release"])
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection([declaration.rule for declaration in declarations]).contains_exactly([
        "godot_engine_build",
        "godot_engine_build",
        "godot_android_shell",
        "engine_hub",
    ]).in_order()
    for declaration in declarations[:2]:
        env.expect.where(recipe = declaration.attrs["name"]).that_dict(declaration.attrs).contains_at_least(
            _COMMON | {"source": _SOURCE, "platform": "android", "environment": ""},
        )
    env.expect.that_collection([declaration.attrs["name"] for declaration in declarations[:2]]).contains_exactly([
        "godot_source_build_android_arm64_template_release",
        "godot_source_build_android_x86_64_template_release",
    ]).in_order()
    env.expect.that_dict(declarations[2].attrs).contains_exactly({
        "name": "godot_source_build_android_shell",
        "source": _SOURCE,
        "patches": ["//patches:fork.patch"],
        "patch_strip": 2,
    })
    hub = declarations[3].attrs
    env.expect.that_str(hub["name"]).equals("godot_source_build")
    env.expect.that_str(hub["display_name"]).equals("godot_source_build")
    env.expect.that_str(hub["version_source"]).equals(_SOURCE)
    env.expect.that_dict(json.decode(hub["android_runtimes"])).contains_exactly({
        "release": {
            "shell": "@godot_source_build_android_shell//:release.aar",
            "engine_libraries": {
                "arm64": "@godot_source_build_android_arm64_template_release//:godot",
                "x86_64": "@godot_source_build_android_x86_64_template_release//:godot",
            },
        },
    })

def _test_desktop_rows_declare_no_shell(env):
    declarations, errors = _declare(["linux"], cpus = ["x86_64"], build_targets = ["editor"])
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection([declaration.rule for declaration in declarations]).contains_exactly(
        ["godot_engine_build", "engine_hub"],
    ).in_order()
    env.expect.that_dict(declarations[0].attrs).contains_at_least({
        "name": "godot_source_build_linux_x86_64_editor",
        "platform": "linux",
        "cpu": "x86_64",
        "build_target": "editor",
    })

def _test_a_lock_file_pins_every_recipe_and_gives_the_hub_its_pin(env):
    lock = Label("//engines:godot_source_build.lock.json")
    declarations, errors = _declare(["linux", "macos"], cpus = ["x86_64"], build_targets = ["editor"], lock_file = lock)
    env.expect.that_collection(errors).contains_exactly([])
    for declaration in declarations[:2]:
        env.expect.where(recipe = declaration.attrs["name"]).that_dict(declaration.attrs).contains_at_least({
            "lock_file": lock,
            "repin": "@godot_source_build//:pin",
        })
    env.expect.that_collection([declaration.attrs["lock_key"] for declaration in declarations[:2]]).contains_exactly(
        ["linux_x86_64_editor", "macos_x86_64_editor"],
    ).in_order()
    hub = declarations[2].attrs
    env.expect.that_str(hub["lock"]).equals("engines/godot_source_build.lock.json")
    env.expect.that_dict(json.decode(hub["pin_recipes"])).contains_exactly({
        "@godot_source_build_linux_x86_64_editor//:pin": "linux_x86_64_editor",
        "@godot_source_build_macos_x86_64_editor//:pin": "macos_x86_64_editor",
    })
    unpinned, _ = _declare(["linux"], cpus = ["x86_64"], build_targets = ["editor"])
    env.expect.that_bool("lock_file" in unpinned[0].attrs).equals(False)
    env.expect.that_bool("pin_recipes" in unpinned[1].attrs).equals(False)

def _test_the_engine_name_reaches_the_hub(env):
    declarations, errors = _declare(["linux"], cpus = ["x86_64"], build_targets = ["editor"], engine = "petri")
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_str(declarations[-1].attrs["engine"]).equals("petri")
    unnamed, _ = _declare(["linux"], cpus = ["x86_64"], build_targets = ["editor"])
    env.expect.that_str(unnamed[-1].attrs["engine"]).equals("")

def _test_a_known_version_spares_the_hub_the_source_archive(env):
    declarations, errors = _declare(["linux"], cpus = ["x86_64"], build_targets = ["editor"], version = "4.7.2")
    env.expect.that_collection(errors).contains_exactly([])
    hub = declarations[-1].attrs
    env.expect.that_dict(hub).keys().not_contains("version_source")
    env.expect.that_collection([slot["version"] for slot in json.decode(hub["components"])]).contains_exactly(["4.7.2"])

def _test_empty_platforms_fail(env):
    declarations, errors = _declare([])
    env.expect.that_collection(errors).contains_exactly([
        'Godot source build "godot_source_build": platforms must name at least one of ' +
        '["linux", "macos", "android", "ios"]',
    ])
    env.expect.that_bool(declarations == None).equals(True)

def _test_unknown_filter_value_fails(env):
    for arguments, message in [
        (dict(platforms = ["windows"]), 'unknown platforms ["windows"]; expected some of ["linux", "macos", "android", "ios"]'),
        (dict(platforms = ["linux"], cpus = ["riscv64"]), 'unknown cpus ["riscv64"]; expected some of ["arm64", "x86_64"]'),
        (dict(platforms = ["linux"], build_targets = ["debug"]), 'unknown build_targets ["debug"]; expected some of ["editor", "template_debug", "template_release"]'),
        (dict(platforms = ["ios"], ios_environments = ["catalyst"]), 'unknown ios_environments ["catalyst"]; expected some of ["device", "simulator"]'),
    ]:
        declarations, errors = _declare(**arguments)
        env.expect.where(filters = arguments).that_collection(errors).contains_exactly([
            'Godot source build "godot_source_build": ' + message,
        ])
        env.expect.where(filters = arguments).that_bool(declarations == None).equals(True)

def _test_filters_selecting_no_row_fail(env):
    declarations, errors = _declare(["android"], build_targets = ["editor"])
    env.expect.that_collection(errors).contains_exactly([
        'Godot source build "godot_source_build": the filters select no valid row',
    ])
    env.expect.that_bool(declarations == None).equals(True)

def source_build_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_ios_environments_filter_ios_rows,
            _test_empty_filters_select_every_valid_row,
            _test_android_rows_declare_one_shell,
            _test_desktop_rows_declare_no_shell,
            _test_a_lock_file_pins_every_recipe_and_gives_the_hub_its_pin,
            _test_the_engine_name_reaches_the_hub,
            _test_a_known_version_spares_the_hub_the_source_archive,
            _test_empty_platforms_fail,
            _test_unknown_filter_value_fails,
            _test_filters_selecting_no_row_fail,
        ],
    )
