"""
A build-output test of an application built with the prebuilt or a source-built beta
engine: the beta inspectors read the application and the engine inputs it selected.
"""

load("@platforms//host:constraints.bzl", "HOST_CONSTRAINTS")
load("@rules_cc//cc:find_cc_toolchain.bzl", "CC_TOOLCHAIN_TYPE", "use_cc_toolchain")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("//godot:providers.bzl", "GodotPackInfo")

visibility("private")

_BetaInputsInfo = provider(
    doc = "Files selected by the configured beta application graph.",
    fields = {"files": "depset of inspected files"},
)

# The runtime bridges resolve the engine through this toolchain type.
_RUNTIME = Label("//godot:runtime_toolchain_type")

# The edges the aspect follows. target leads from configured_outputs to the application
# built under its configuration; application is the rules_apple application the iOS app
# forwards in the bundle format its build's purpose selects, and runtime and
# engine_library lead from a runtime component to its payload and engine.
_EDGES = [
    "target",
    "deps",
    "data",
    "pack",
    "app",
    "application",
    "engine_libraries",
    "engine_library",
    "aar",
    "runtime",
    "resources",
    "infoplists",
    "srcs",
]

def _static_archives(target):
    return [
        library.static_library or library.pic_static_library
        for linker in target[CcInfo].linking_context.linker_inputs.to_list()
        for library in linker.libraries
        if library.static_library or library.pic_static_library
    ]

def _engine_files(target, ctx):
    """Return the engine's archives, AAR or library, when the target is one of them."""
    files = []
    if CcInfo in target and target.label.name in ["engine_library", "release", "ios_release"]:
        files += _static_archives(target)
    if ctx.rule.kind == "godot_android_engine_aar" or target.label.name in ["godot", "libgodot_android.so"]:
        files += target[DefaultInfo].files.to_list()
    return files

def _targets(value):
    if type(value) == "dict":
        return value.keys()
    if type(value) == "list":
        return value
    return [value]

def _dependency_inputs(ctx):
    """Return the inputs that the target's dependencies on _EDGES and its runtime select."""
    transitive = [
        dependency[_BetaInputsInfo].files
        for name in _EDGES
        for dependency in _targets(getattr(ctx.rule.attr, name, None))
        if type(dependency) == "Target" and _BetaInputsInfo in dependency
    ]
    runtime = ctx.rule.toolchains[_RUNTIME] if _RUNTIME in ctx.rule.toolchains else None
    if runtime and _BetaInputsInfo in runtime:
        transitive.append(runtime[_BetaInputsInfo].files)
    return transitive

def _inputs_impl(target, ctx):
    # Follow the actual Apple/Android transitions rather than resolving a second engine or
    # pack configuration. These identities are private target names of the engine
    # repositories, including the source generator's compile archives; the engine AAR is
    # known by its rule, since godot_android_runtime names it after the runtime.
    files = []
    if GodotPackInfo in target:
        files.append(target[GodotPackInfo].pack_file)
    if OutputGroupInfo in target and hasattr(target[OutputGroupInfo], "plist"):
        files += target[OutputGroupInfo].plist.to_list()
    transitive = []
    if ctx.rule:
        files += _engine_files(target, ctx)
        transitive = _dependency_inputs(ctx)
    return [_BetaInputsInfo(files = depset(files, transitive = transitive))]

_inputs = aspect(
    implementation = _inputs_impl,
    attr_aspects = _EDGES,
    toolchains_aspects = [str(_RUNTIME)],
)

def _cc_toolchain_files_impl(ctx):
    toolchain = ctx.exec_groups["host"].toolchains[CC_TOOLCHAIN_TYPE]
    if not toolchain:
        fail("Inspecting an Android application needs this host's NDK C++ toolchain.")
    return [DefaultInfo(files = toolchain.cc.all_files)]

cc_toolchain_files = rule(
    doc = """
    The files of the C++ toolchain of the target platform for this host, such as the NDK's
    llvm-readelf; build it under the Android configuration with configured_outputs.
    """,
    implementation = _cc_toolchain_files_impl,
    # The test runs the toolchain's host tools, so the toolchain resolves for this host.
    exec_groups = {"host": exec_group(
        exec_compatible_with = HOST_CONSTRAINTS,
        toolchains = use_cc_toolchain(mandatory = False),
    )},
)

def _runfile(ctx, file):
    path = file.short_path
    return path[3:] if path.startswith("../") else ctx.workspace_name + "/" + path

def _one(files, suffix):
    matches = [file for file in files if file.path.endswith(suffix)]
    if len(matches) != 1:
        fail("Expected one %s, got %s" % (suffix, [f.path for f in matches]))
    return matches[0]

def _android_inputs(ctx, outputs, inputs):
    """Return the Android inspector's file arguments, with the other files and runfiles it needs."""
    apks = [
        file
        for file in outputs
        if file.extension == "apk" and not file.basename.endswith("_unsigned.apk")
    ]
    if len(apks) != 1:
        fail("Expected one signed APK, got %s" % [f.path for f in apks])
    aar = ctx.file.official_aar if ctx.attr.kind == "official" else _one(inputs, ".aar")
    pairs = [("--artifact", apks[0]), ("--engine-aar", aar)]
    if ctx.attr.kind == "source":
        pairs.append(("--source-library", _one(inputs, "/libgodot_android.so")))
    toolchain = ctx.attr.cc_toolchain_files[DefaultInfo].files.to_list()
    pairs.append(("--readelf", _one(toolchain, "/bin/llvm-readelf")))
    runfiles = ctx.runfiles()
    for flag, tool in [("--aapt", ctx.attr.aapt), ("--apksigner", ctx.attr.apksigner)]:
        pairs.append((flag, tool[DefaultInfo].files_to_run.executable))
        runfiles = runfiles.merge(tool[DefaultInfo].default_runfiles)
    return struct(
        arguments = [],
        pairs = pairs,
        # Keep the NDK host tools' adjacent runtime libraries available too.
        files = [f for f in toolchain if f.extension in ["dylib", "so"]],
        runfiles = runfiles,
    )

def _compile_archives(inputs):
    libraries = [
        f
        for f in inputs
        if f.basename.startswith("lib_objects_") and not ".pic." in f.basename
    ]
    if not libraries:
        fail("No source-built engine compile archives found in the application graph")
    return libraries

def _ios_inputs(ctx, outputs, inputs):
    """Return the iOS inspector's arguments: the official device link's files or the source-built app."""
    if ctx.attr.kind == "official":
        environment = "device"
        pairs = [
            ("--binary", _one(outputs, "_lipobin")),
            ("--pack", _one(inputs, ".pck")),
            ("--plist", _one(inputs, "/Godot.plist")),
            ("--accesskit-library", _one(inputs, "/libaccesskit.a")),
        ]
        libraries = [_one(inputs, "/libgodot.a")]
    else:
        environment = "simulator"
        pairs = [("--artifact", _one(outputs, ".app"))]
        libraries = _compile_archives(inputs)
    return struct(
        arguments = ["--expected-environment " + environment],
        pairs = pairs + [("--engine-library", file) for file in libraries],
        files = [],
        runfiles = ctx.runfiles(),
    )

def _test_impl(ctx):
    app = ctx.attr.app
    outputs = app[DefaultInfo].files.to_list()
    inputs = app[_BetaInputsInfo].files.to_list()
    selected = (_android_inputs if ctx.attr.operating_system == "android" else _ios_inputs)(ctx, outputs, inputs)
    pairs = list(selected.pairs)
    if ctx.file.engine_manifest:
        pairs.append(("--engine-manifest", ctx.file.engine_manifest))
    files = selected.files + [file for _, file in pairs]
    arguments = ["--kind " + ctx.attr.kind] + selected.arguments
    arguments += ['%s "$runfiles/%s"' % (flag, _runfile(ctx, file)) for flag, file in pairs]
    inspector = ctx.attr.inspector[DefaultInfo]
    launcher = ctx.actions.declare_file(ctx.label.name)
    ctx.actions.expand_template(
        template = ctx.file._launcher,
        output = launcher,
        substitutions = {
            "{INSPECTOR}": _runfile(ctx, inspector.files_to_run.executable),
            "{ARGUMENTS}": " ".join(arguments),
        },
        is_executable = True,
    )
    return [DefaultInfo(
        executable = launcher,
        runfiles = selected.runfiles.merge(ctx.runfiles(files = files)).merge(inspector.default_runfiles),
    )]

beta_engine_test = rule(
    doc = "Inspect a beta engine application and the engine inputs it selected.",
    implementation = _test_impl,
    attrs = {
        "app": attr.label(
            doc = "The application, built under its configuration by configured_outputs.",
            mandatory = True,
            aspects = [_inputs],
        ),
        "kind": attr.string(mandatory = True, values = ["official", "source"]),
        "operating_system": attr.string(mandatory = True, values = ["android", "ios"]),
        "inspector": attr.label(mandatory = True, executable = True, cfg = config.exec("test")),
        "official_aar": attr.label(allow_single_file = True),
        "engine_manifest": attr.label(allow_single_file = True),
        "aapt": attr.label(executable = True, cfg = config.exec("test")),
        "apksigner": attr.label(executable = True, cfg = config.exec("test")),
        "cc_toolchain_files": attr.label(
            doc = "cc_toolchain_files under the Android configuration, for llvm-readelf.",
        ),
        "_launcher": attr.label(default = Label(":beta_engine_test.sh.tpl"), allow_single_file = True),
    },
    # The test runs cc_toolchain_files' host tools, so it runs on this host.
    exec_groups = {"test": exec_group(exec_compatible_with = HOST_CONSTRAINTS)},
    test = True,
)
