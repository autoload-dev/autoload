"""godot_export_templates_archive declares the runtimes of one platform that its archive's contents and layout provide."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/engine/private:archives.bzl", "templates_archive_impl")
load("//godot/private/tests:mocks.bzl", "mocks")

visibility("private")

_INTEGRITY = "sha512-" + "B" * 86 + "=="
_ARCHIVE = "@godot_templates_archive//file:export_templates.tpz"
_MACOS = "macos/macos_template.app/Contents/MacOS/godot_macos_%s.%s"
_LINUX_CPUS = ["arm32", "arm64", "x86_32", "x86_64"]
_LINUX = [
    "templates/linux_%s.%s" % (variant, cpu)
    for cpu in _LINUX_CPUS
    for variant in ["release", "debug"]
]
_UNIVERSAL = [_MACOS % ("release", "universal"), _MACOS % ("debug", "universal")]
_IOS = [
    "ios/libgodot.ios.debug.xcframework/Info.plist",
    "ios/libgodot.ios.release.xcframework/Info.plist",
]

# Each template shows its substitutions; repository_ctx.template keeps the file's text.
_TEMPLATES = {
    "runtime.tpl": "{NAME}|{CPU}|{BINARY}|{PLATFORM}|{VARIANT}|{VERSION}|{DIGEST}{DATA}\n",
    "ios.tpl": "ios {SIMULATOR}{LIBRARIES}|{ENGINES}\n",
    "ios_engine.tpl": "{NAME} {XCFRAMEWORK} {DEPS}\n",
    "moltenvk.tpl": "moltenvk {XCFRAMEWORK}\n",
    "accesskit.tpl": "accesskit {XCFRAMEWORK}\n",
    "camera.tpl": "camera {VARIANT} {XCFRAMEWORK}\n",
}

def _templates(*, platform, tree, **overrides):
    """
    Run the rule for one platform over an extracted tree.

    The tree is what the archive members of the platform extract to; a nested ZIP the
    tree names is the archive's member, its expanded entries the extracted ZIP.
    """
    ctx = mocks.repository_ctx(
        attr = {
            "archive": _ARCHIVE,
            "integrity": _INTEGRITY,
            "version": "4.7.2",
            "copyright": None,
            "platform": platform,
            "cpus": {"linux": _LINUX_CPUS, "macos": ["universal"], "ios": []}[platform],
            "_prebuilt_bzl": "@@//godot/engine/private:prebuilt.bzl",
            "_build_template": "export_templates.BUILD.tpl",
            "_runtime_template": "runtime.tpl",
            "_apple_bzl": "@@rules_apple+//apple:apple.bzl",
            "_simulator_constraint": "@@apple_support+//constraints:simulator",
            "_ios_template": "ios.tpl",
            "_ios_engine_template": "ios_engine.tpl",
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

def _declarations(ctx):
    """The target declarations of the BUILD file, each set off by blank lines."""
    text = _substitutions(ctx)["{TARGETS}"].strip("\n")
    return text.split("\n\n") if text else []

def _runtimes(ctx):
    """The filled runtime templates by target name."""
    return {rule.partition("|")[0].strip('"'): rule for rule in _declarations(ctx) if "|" in rule}

def _runtime(name, cpu, binary, platform, variant, data = ""):
    return "|".join([repr(name), repr(cpu), repr(binary), repr(platform), repr(variant), repr("4.7.2"), repr(_INTEGRITY)]) + data

def _extracted_members(ctx):
    """The archive entries the rule extracts, which strip_prefix keeps by their renaming."""
    extract = [call for call in mocks.calls(ctx, "extract") if call.archive == _ARCHIVE][0]
    if extract.strip_prefix != "kept" or extract.type != "zip":
        return None
    return [member for member, renamed in extract.rename_files.items() if renamed == "kept/" + member]

def _nested_extracts(ctx):
    """The archive and output of each extraction of a ZIP inside the repository."""
    return [(call.archive, call.output) for call in mocks.calls(ctx, "extract") if call.archive != _ARCHIVE]

def _test_each_platform_extracts_only_its_members(env):
    for platform, tree, members in [
        ("linux", _LINUX, _LINUX),
        ("macos", ["templates/macos.zip"] + _UNIVERSAL, ["templates/macos.zip"]),
        ("ios", ["templates/ios.zip"] + _IOS, ["templates/ios.zip"]),
    ]:
        ctx, errors = _templates(platform = platform, tree = tree)
        env.expect.where(platform = platform).that_collection(errors).contains_exactly([])
        env.expect.where(platform = platform).that_collection(_extracted_members(ctx)).contains_exactly(
            ["templates/version.txt"] + members,
        )

def _test_linux_exposes_cpu_variants(env):
    ctx, errors = _templates(platform = "linux", tree = _LINUX)
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(_nested_extracts(ctx)).contains_exactly([])
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
    ]).in_order()
    env.expect.that_str(runtimes["linux_arm64_debug"]).equals(_runtime(
        "linux_arm64_debug",
        "arm64",
        "templates/linux_debug.arm64",
        "linux",
        "debug",
    ))
    substitutions = _substitutions(ctx)
    env.expect.that_str(mocks.calls(ctx, "template")[0].template).equals("export_templates.BUILD.tpl")
    env.expect.that_str(substitutions["{LOADS}"]).equals(
        'load("@@//godot/engine/private:prebuilt.bzl", "prebuilt_runtime")',
    )

    # Only the runtimes; the macOS bundle's files belong to the macOS repository.
    env.expect.that_collection(_declarations(ctx)).has_size(8)

def _test_universal_macos_exposes_macos_variants(env):
    ctx, errors = _templates(platform = "macos", tree = ["templates/macos.zip"] + _UNIVERSAL)
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(_nested_extracts(ctx)).contains_exactly([("templates/macos.zip", "macos")])

    # The expanded ZIP replaces the archive's copy.
    env.expect.that_collection([call.path for call in mocks.calls(ctx, "delete")]).contains_exactly(
        ["templates/macos.zip"],
    )
    env.expect.that_str(_declarations(ctx)[0]).equals(
        'filegroup(\n    name = "macos_files",\n    srcs = glob(["macos/**"]),\n)',
    )
    runtimes = _runtimes(ctx)
    env.expect.that_collection(runtimes.keys()).contains_exactly(["macos_release", "macos_debug"]).in_order()
    env.expect.that_str(runtimes["macos_release"]).equals(_runtime(
        "macos_release",
        "universal",
        _MACOS % ("release", "universal"),
        "macos",
        "release",
        data = '\n    data = [":macos_files"],',
    ))

def _test_split_macos_exposes_cpu_variants(env):
    ctx, errors = _templates(
        platform = "macos",
        cpus = ["arm64", "x86_64"],
        tree = [
            "templates/macos.zip",
            _MACOS % ("release", "arm64"),
            _MACOS % ("debug", "arm64"),
            _MACOS % ("release", "x86_64"),
        ],
    )
    env.expect.that_collection(errors).contains_exactly([])
    runtimes = _runtimes(ctx)
    env.expect.that_collection(runtimes.keys()).contains_exactly([
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
    ctx, errors = _templates(platform = "linux", tree = [path for path in _LINUX if path != "templates/linux_debug.arm64"])
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(_runtimes(ctx).keys()).contains_exactly([
        "linux_arm32_release",
        "linux_arm32_debug",
        "linux_arm64_release",
        "linux_x86_32_release",
        "linux_x86_32_debug",
        "linux_x86_64_release",
        "linux_x86_64_debug",
    ]).in_order()

def _test_archive_without_a_linux_cpu_fails(env):
    _, errors = _templates(platform = "linux", tree = [path for path in _LINUX if not path.endswith(".x86_32")])
    env.expect.that_collection(errors).contains_exactly([
        "Godot template archive does not contain templates/linux_release.x86_32; " +
        "its Linux CPUs differ from the catalogue's",
    ])

def _test_archive_without_the_platform_zip_fails(env):
    for platform in ["macos", "ios"]:
        ctx, errors = _templates(platform = platform, tree = _LINUX)
        env.expect.where(platform = platform).that_collection(errors).contains_exactly([
            "Godot template archive does not contain templates/%s.zip" % platform,
        ])
        env.expect.where(platform = platform).that_collection(mocks.calls(ctx, "template")).contains_exactly([])

def _test_ios_zip_exposes_ios_variants(env):
    ctx, errors = _templates(platform = "ios", tree = ["templates/ios.zip"] + _IOS + [
        "ios/MoltenVK.xcframework/Info.plist",
        "ios/AccessKit.xcframework/Info.plist",
        "ios/libgodot_camera.ios.release.xcframework/Info.plist",
    ])
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_collection(_nested_extracts(ctx)).contains_exactly([("templates/ios.zip", "ios")])
    env.expect.that_collection([call.path for call in mocks.calls(ctx, "delete")]).contains_exactly(
        ["templates/ios.zip"],
    )
    substitutions = _substitutions(ctx)
    env.expect.that_str(substitutions["{LOADS}"]).equals(
        'load("@@rules_apple+//apple:apple.bzl", "apple_static_xcframework_import")',
    )
    env.expect.that_str(substitutions["{TARGETS}"]).equals(
        '\nios "@@apple_support+//constraints:simulator"' +
        "\nmoltenvk ios/MoltenVK.xcframework\n\naccesskit ios/AccessKit.xcframework\n" +
        "\ncamera release ios/libgodot_camera.ios.release.xcframework\n|" +
        '"ios_debug" ios/libgodot.ios.debug.xcframework [\n        ":ios_accesskit",\n        ":ios_moltenvk",\n    ]\n\n' +
        '"ios_release" ios/libgodot.ios.release.xcframework [\n        ":ios_accesskit",\n        ":ios_camera_release",\n        ":ios_moltenvk",\n    ]\n',
    )

def _test_ios_zip_without_dependencies_imports_the_engine_alone(env):
    ctx, errors = _templates(platform = "ios", tree = ["templates/ios.zip"] + _IOS)
    env.expect.that_collection(errors).contains_exactly([])
    env.expect.that_str(_substitutions(ctx)["{TARGETS}"]).equals(
        '\nios "@@apple_support+//constraints:simulator"|' +
        '"ios_debug" ios/libgodot.ios.debug.xcframework []\n\n' +
        '"ios_release" ios/libgodot.ios.release.xcframework []\n',
    )

def _test_invalid_cpus_fail(env):
    macos = 'cpus of macOS templates must be ["universal"] or a subset of ["arm64", "x86_64"]'
    for platform, cpus, message in [
        ("macos", ["universal", "arm64"], macos),
        ("macos", ["arm64", "arm64"], macos),
        ("macos", ["ppc64"], macos),
        ("macos", [], macos),
        ("linux", ["ppc64"], "cpus of Linux templates must be Godot CPU tags: "),
        ("linux", [], "cpus of Linux templates must be Godot CPU tags: "),
        ("ios", ["arm64"], "cpus must be empty for iOS templates"),
    ]:
        ctx, errors = _templates(platform = platform, cpus = cpus, tree = [])
        env.expect.where(platform = platform, cpus = cpus).that_collection(errors).has_size(1)
        if errors:
            env.expect.where(platform = platform, cpus = cpus).that_str(errors[0]).contains(message)
        env.expect.where(platform = platform, cpus = cpus).that_collection(ctx.calls).contains_exactly([])

def _test_missing_macos_release_template_fails(env):
    ctx, errors = _templates(platform = "macos", cpus = ["arm64"], tree = ["templates/macos.zip"] + _UNIVERSAL)
    env.expect.that_collection(errors).contains_exactly([
        "Godot template archive does not contain " +
        "macos/macos_template.app/Contents/MacOS/godot_macos_release.arm64; " +
        "set cpus to match the archive layout",
    ])
    env.expect.that_collection(mocks.calls(ctx, "template")).contains_exactly([])

def _test_ios_zip_without_xcframework_layout_fails(env):
    ctx, errors = _templates(platform = "ios", tree = ["templates/ios.zip", "ios/libgodot.ios.release.xcframework/Info.plist"])
    env.expect.that_collection(errors).contains_exactly([
        "Godot templates ios.zip is missing ios/libgodot.ios.debug.xcframework/Info.plist; " +
        "expected Godot's ios.zip layout",
    ])
    env.expect.that_collection(mocks.calls(ctx, "template")).contains_exactly([])

def export_templates_archive_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_each_platform_extracts_only_its_members,
            _test_linux_exposes_cpu_variants,
            _test_universal_macos_exposes_macos_variants,
            _test_split_macos_exposes_cpu_variants,
            _test_missing_debug_template_omits_debug,
            _test_archive_without_a_linux_cpu_fails,
            _test_archive_without_the_platform_zip_fails,
            _test_ios_zip_exposes_ios_variants,
            _test_ios_zip_without_dependencies_imports_the_engine_alone,
            _test_invalid_cpus_fail,
            _test_missing_macos_release_template_fails,
            _test_ios_zip_without_xcframework_layout_fails,
        ],
    )
