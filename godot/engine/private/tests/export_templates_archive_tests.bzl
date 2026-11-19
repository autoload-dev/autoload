"""godot_export_templates_archive declares the runtimes its archive's contents and layout provide."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")

# buildifier: disable=bzl-visibility
load("//godot/engine/private:archives.bzl", "templates_archive_impl")

# buildifier: disable=bzl-visibility
load("//godot/private/tests:mocks.bzl", "mocks")

_INTEGRITY = "sha512-" + "B" * 86 + "=="
_MACOS = "macos/macos_template.app/Contents/MacOS/godot_macos_%s.%s"
_LINUX = [
    "templates/linux_%s.%s" % (variant, cpu)
    for cpu in ["arm32", "arm64", "x86_32", "x86_64"]
    for variant in ["release", "debug"]
]
_UNIVERSAL = ["templates/macos.zip", _MACOS % ("release", "universal"), _MACOS % ("debug", "universal")]
_IOS = [
    "templates/ios.zip",
    "ios/libgodot.ios.debug.xcframework/Info.plist",
    "ios/libgodot.ios.release.xcframework/Info.plist",
]

# Each template shows its substitutions; repository_ctx.template keeps the file's text.
_TEMPLATES = {
    "runtime.tpl": "{NAME}|{CPU}|{BINARY}|{PLATFORM}|{VARIANT}|{VERSION}|{DIGEST}{DATA}\n",
    "ios.tpl": "ios {SIMULATOR}{LIBRARIES}|{DEBUG_DEPS}|{RELEASE_DEPS}\n",
    "moltenvk.tpl": "moltenvk\n",
    "accesskit.tpl": "accesskit\n",
    "camera.tpl": "camera {VARIANT} {XCFRAMEWORK}\n",
}

def _templates(*, tree, **overrides):
    ctx = mocks.repository_ctx(
        attr = {
            "urls": ["https://example.com/export_templates.tpz"],
            "integrity": _INTEGRITY,
            "version": "4.7.2",
            "macos_cpus": ["universal"],
            "linux_cpus": ["arm32", "arm64", "x86_32", "x86_64"],
            "_prebuilt_bzl": "@@//godot/engine/private:prebuilt.bzl",
            "_build_template": "export_templates.BUILD.tpl",
            "_runtime_template": "runtime.tpl",
            "_apple_bzl": "@@rules_apple+//apple:apple.bzl",
            "_simulator_constraint": "@@apple_support+//constraints:simulator",
            "_ios_template": "ios.tpl",
            "_ios_moltenvk_template": "moltenvk.tpl",
            "_ios_accesskit_template": "accesskit.tpl",
            "_ios_camera_template": "camera.tpl",
        } | overrides,
        files = _TEMPLATES,
        tree = tree,
    )
    errors, fail_ = mocks.errors()
    templates_archive_impl(ctx, _fail = fail_)
    return ctx, errors

def _substitutions(ctx):
    templates = mocks.calls(ctx, "template")
    return templates[0].substitutions if templates else None

def _runtimes(ctx):
    """The filled runtime templates by target name."""
    text = _substitutions(ctx)["{RUNTIMES}"].strip("\n")
    rules = text.split("\n\n") if text else []
    return {rule.partition("|")[0].strip('"'): rule for rule in rules}

def _runtime(name, cpu, binary, platform, variant, data = ""):
    return "|".join([repr(name), repr(cpu), repr(binary), repr(platform), repr(variant), repr("4.7.2"), repr(_INTEGRITY)]) + data

def _test_universal_macos_exposes_macos_variants(env):
    ctx, errors = _templates(tree = _LINUX + _UNIVERSAL)
    env.expect.that_collection(errors).contains_exactly([])
    extracts = mocks.calls(ctx, "extract")
    env.expect.that_collection([(call.archive, call.output) for call in extracts]).contains_exactly(
        [("templates/macos.zip", "macos")],
    )
    runtimes = _runtimes(ctx)
    env.expect.that_collection(runtimes.keys()).contains_exactly([
        "linux_arm32_release",
        "linux_arm32_debug",
        "linux_arm64_release",
        "linux_arm64_debug",
        "linux_x86_32_release",
        "linux_x86_32_debug",
        "linux_x86_64_release",
        "linux_x86_64_debug",
        "macos_release",
        "macos_debug",
    ]).in_order()
    env.expect.that_str(runtimes["macos_release"]).equals(_runtime(
        "macos_release",
        "universal",
        _MACOS % ("release", "universal"),
        "macos",
        "release",
        data = '\n    data = [":macos_files"],',
    ))
    env.expect.that_str(runtimes["linux_arm64_debug"]).equals(_runtime(
        "linux_arm64_debug",
        "arm64",
        "templates/linux_debug.arm64",
        "linux",
        "debug",
    ))
    substitutions = _substitutions(ctx)
    env.expect.that_str(mocks.calls(ctx, "template")[0].template).equals("export_templates.BUILD.tpl")
    env.expect.that_str(substitutions["{PREBUILT_BZL}"]).equals(repr("@@//godot/engine/private:prebuilt.bzl"))
    env.expect.that_str(substitutions["{APPLE_LOAD}"]).equals("")
    env.expect.that_str(substitutions["{IOS}"]).equals("")

def _test_split_macos_exposes_cpu_variants(env):
    ctx, errors = _templates(
        macos_cpus = ["arm64", "x86_64"],
        tree = _LINUX + [
            "templates/macos.zip",
            _MACOS % ("release", "arm64"),
            _MACOS % ("debug", "arm64"),
            _MACOS % ("release", "x86_64"),
        ],
    )
    env.expect.that_collection(errors).contains_exactly([])
    runtimes = _runtimes(ctx)
    env.expect.that_collection([name for name in runtimes if name.startswith("macos")]).contains_exactly([
        "macos_arm64_release",
        "macos_arm64_debug",
        "macos_x86_64_release",
    ]).in_order()
    env.expect.that_str(runtimes["macos_x86_64_release"]).equals(_runtime(
        "macos_x86_64_release",
        "x86_64",
        _MACOS % ("release", "x86_64"),
        "macos",
        "release",
        data = '\n    data = [":macos_files"],',
    ))

def _test_missing_debug_template_omits_debug(env):
    ctx, errors = _templates(tree = [path for path in _LINUX if path != "templates/linux_debug.arm64"] + [
        "templates/macos.zip",
        _MACOS % ("release", "universal"),
    ])
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(_runtimes(ctx).keys()).contains_exactly([
        "linux_arm32_release",
        "linux_arm32_debug",
        "linux_arm64_release",
        "linux_x86_32_release",
        "linux_x86_32_debug",
        "linux_x86_64_release",
        "linux_x86_64_debug",
        "macos_release",
    ]).in_order()

def _test_archive_without_a_linux_cpu_fails(env):
    _, errors = _templates(tree = [path for path in _LINUX if not path.endswith(".x86_32")])
    env.expect.that_collection(errors).contains_exactly([
        "Godot template archive does not contain templates/linux_release.x86_32; " +
        "its Linux CPUs differ from the catalogue's",
    ])

def _test_archive_without_macos_zip_omits_macos(env):
    ctx, errors = _templates(tree = _LINUX)
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(mocks.calls(ctx, "extract")).contains_exactly([])
    env.expect.that_collection([name for name in _runtimes(ctx) if name.startswith("macos")]).contains_exactly([])

def _test_ios_zip_exposes_ios_variants(env):
    ctx, errors = _templates(tree = _LINUX + _IOS + [
        "ios/MoltenVK.xcframework/Info.plist",
        "ios/AccessKit.xcframework/Info.plist",
        "ios/libgodot_camera.ios.release.xcframework/Info.plist",
    ])
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection([(call.archive, call.output) for call in mocks.calls(ctx, "extract")]).contains_exactly(
        [("templates/ios.zip", "ios")],
    )
    substitutions = _substitutions(ctx)
    env.expect.that_str(substitutions["{APPLE_LOAD}"]).equals(
        'load("@@rules_apple+//apple:apple.bzl", "apple_static_xcframework_import")',
    )
    env.expect.that_str(substitutions["{IOS}"]).equals(
        'ios "@@apple_support+//constraints:simulator"' +
        "\nmoltenvk\n\naccesskit\n\ncamera release libgodot_camera.ios.release.xcframework\n" +
        '|[\n        ":ios_accesskit",\n        ":ios_moltenvk",\n    ]' +
        '|[\n        ":ios_accesskit",\n        ":ios_camera_release",\n        ":ios_moltenvk",\n    ]',
    )

def _test_ios_zip_without_dependencies_imports_the_engine_alone(env):
    ctx, errors = _templates(tree = _LINUX + _IOS)
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_str(_substitutions(ctx)["{IOS}"]).equals('ios "@@apple_support+//constraints:simulator"|[]|[]')

def _test_invalid_macos_cpus_fail(env):
    for cpus in [["universal", "arm64"], ["arm64", "arm64"], ["ppc64"]]:
        ctx, errors = _templates(macos_cpus = cpus, tree = _LINUX + _UNIVERSAL)
        env.expect.where(macos_cpus = cpus).that_collection(errors).contains_exactly([
            'macos_cpus must be ["universal"] or a subset of ["arm64", "x86_64"]',
        ])
        env.expect.where(macos_cpus = cpus).that_collection(ctx.calls).contains_exactly([])

def _test_templates_archive_without_integrity_fails(env):
    ctx, errors = _templates(integrity = "", tree = _LINUX + _UNIVERSAL)
    env.expect.that_collection(errors).contains_exactly([
        "integrity is required: every Godot download must be checksum-pinned",
    ])
    env.expect.that_collection(ctx.calls).contains_exactly([])

def _test_missing_macos_release_template_fails(env):
    ctx, errors = _templates(macos_cpus = ["arm64"], tree = _LINUX + _UNIVERSAL)
    env.expect.that_collection(errors).contains_exactly([
        "Godot template archive does not contain " +
        "macos/macos_template.app/Contents/MacOS/godot_macos_release.arm64; " +
        "set macos_cpus to match the archive layout",
    ])
    env.expect.that_collection(mocks.calls(ctx, "template")).contains_exactly([])

def _test_ios_zip_without_xcframework_layout_fails(env):
    ctx, errors = _templates(tree = _LINUX + ["templates/ios.zip", "ios/libgodot.ios.release.xcframework/Info.plist"])
    env.expect.that_collection(errors).contains_exactly([
        "Godot templates ios.zip is missing ios/libgodot.ios.debug.xcframework/Info.plist; " +
        "expected Godot's ios.zip layout",
    ])
    env.expect.that_collection(mocks.calls(ctx, "template")).contains_exactly([])

def export_templates_archive_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_universal_macos_exposes_macos_variants,
            _test_split_macos_exposes_cpu_variants,
            _test_missing_debug_template_omits_debug,
            _test_archive_without_a_linux_cpu_fails,
            _test_archive_without_macos_zip_omits_macos,
            _test_ios_zip_exposes_ios_variants,
            _test_ios_zip_without_dependencies_imports_the_engine_alone,
            _test_invalid_macos_cpus_fail,
            _test_templates_archive_without_integrity_fails,
            _test_missing_macos_release_template_fails,
            _test_ios_zip_without_xcframework_layout_fails,
        ],
    )
