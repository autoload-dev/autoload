"""The JNI libraries of Godot Android applications and the engine AAR of their runtime."""

load("@rules_android//providers:providers.bzl", "AndroidNativeLibsInfo", "StarlarkAndroidResourcesInfo")
load("@rules_cc//cc:find_cc_toolchain.bzl", "use_cc_toolchain")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("//godot:providers.bzl", "GodotPackInfo")
load("//godot/engine/private:generator.bzl", "GodotEngineVersionInfo")
load("//godot/platforms/private:shell.bzl", "ENGINE_CHECK_ATTRS", "check_engine", "pack_facts")
load("//godot/private:symbols.bzl", "STRIP_ATTRS", "keep_debug_info", "packaged")
load("//godot/private/config:settings.bzl", "CPU_TABLE", "PLATFORM_ATTRS", "target_platform")
load(
    ":android_runtime_bridge.bzl",
    "ANDROID_PAYLOAD_ASPECTS",
    "AndroidShellClassesInfo",
    _AndroidSymbolsInfo = "AndroidSymbolsInfo",
)

visibility("private")

def _delivery_entries(ctx, libraries):
    """
    The libraries by their path in the delivery, each path once.

    A library that comes twice is delivered once. Two Files at one path fail.
    """
    entries = {}
    for library in libraries:
        path = library["abi"] + "/" + library.get("name", library["file"].basename)
        delivered = entries.setdefault(path, library)
        if delivered["file"] != library["file"]:
            fail((
                "%s: duplicate Android library: %s from %s conflicts with %s from %s; " +
                "provide distinct delivery names or reuse the same native File"
            ) % (
                library.get("origin", str(ctx.label)),
                path,
                library["file"].path,
                delivered["file"].path,
                delivered.get("origin", str(ctx.label)),
            ))
    return entries

def _strip_libraries(ctx, libraries):
    """Return unique stripped delivery entries and their original debug-symbol inputs."""
    entries = _delivery_entries(ctx, libraries)
    symbols = {path: entry["file"] for path, entry in entries.items()}
    files = packaged(ctx, {
        ctx.label.name + "_stripped/" + path: file
        for path, file in symbols.items()
    })
    return struct(
        symbols = _AndroidSymbolsInfo(files = symbols),
        libraries = [
            entry | {"file": file}
            for entry, file in zip(entries.values(), files.values())
        ],
    )

def _single_library(target):
    candidates = [
        file
        for file in target[DefaultInfo].files.to_list()
        if file.extension == "so"
    ]
    if len(candidates) != 1:
        fail("engine library target %s must expose exactly one .so file" % target.label)
    return candidates[0]

def _android_zip(ctx, libraries, output, aar = None):
    manifest = ctx.actions.declare_file(ctx.label.name + ".jni.json")
    args = ctx.actions.args()
    args.add("--manifest", manifest)
    args.add("--output", output)
    inputs = [manifest]
    for entry in libraries:
        inputs += [entry["file"]] + entry.get("inputs", [])

    # Keep File objects in the action inputs, serialize only paths for the tool.
    ctx.actions.write(
        manifest,
        json.encode([
            {"source": entry["file"].path} | {
                key: value
                for key, value in entry.items()
                if key not in ("file", "inputs", "origin")
            }
            for entry in libraries
        ]),
    )
    if aar:
        args.add("--aar", aar)
        inputs.append(aar)
    ctx.actions.run(
        executable = ctx.executable._android_packager,
        inputs = inputs,
        outputs = [output],
        arguments = [args],
        mnemonic = "GodotAndroidJniLibraries",
        progress_message = "Bundling %{label}",
    )

# Android ABI of the platform slice's CPU, for an engine library selected per platform
# slice.
def _platform_slice_abi(ctx):
    cpu = target_platform(ctx).cpu
    if not cpu:
        fail("%s: the target platform has no CPU of the CPU table" % ctx.label)
    return CPU_TABLE[cpu].android_abi

def _engine_library(target, abi):
    library = {
        "file": _single_library(target),
        "abi": abi,
        "name": "libgodot_android.so",
    }
    if GodotEngineVersionInfo not in target:
        return library

    # The AAR manifest names the version of a source-built engine, not the
    # prebuilt one the AAR came with.
    engine_version = target[GodotEngineVersionInfo]
    return library | {
        "version": engine_version.version,
        "build": engine_version.build.path,
        "hash": engine_version.hash.path,
        "inputs": [engine_version.build, engine_version.hash],
    }

def _engine_aar_impl(ctx):
    engine_libraries = dict(ctx.attr.engine_libraries)
    if ctx.attr.engine_library:
        engine_libraries[ctx.attr.engine_library[0]] = _platform_slice_abi(ctx)
    libraries = [_engine_library(target, abi) for target, abi in engine_libraries.items()]
    stripped = _strip_libraries(ctx, libraries)
    libraries = stripped.libraries
    symbols = stripped.symbols
    output = ctx.actions.declare_file(ctx.label.name + ".aar")
    _android_zip(ctx, libraries, output, ctx.file.aar)
    result = [DefaultInfo(files = depset([output])), symbols]

    # The source-built engine library of the platform slice names the runtime's producer
    # for component provenance.
    if ctx.attr.engine_library and GodotEngineVersionInfo in ctx.attr.engine_library[0]:
        result.append(ctx.attr.engine_library[0][GodotEngineVersionInfo])
    if ctx.attr.shell_classes:
        result.append(AndroidShellClassesInfo(target = ctx.attr.shell_classes))
    return result

godot_android_engine_aar = rule(
    implementation = _engine_aar_impl,
    attrs = {
        "aar": attr.label(
            doc = "Godot's Android shell .aar file whose JNI engine library may be replaced.",
            mandatory = True,
            allow_single_file = [".aar"],
        ),
        "engine_libraries": attr.label_keyed_string_dict(
            doc = """
            Engine library .so targets mapped to Android ABI names such as arm64-v8a;
            they link without Bazel's --strip.
            """,
            allow_files = [".so"],
            cfg = keep_debug_info,
        ),
        "engine_library": attr.label(
            doc = """
            Engine library .so of the current platform slice, delivered under the ABI of
            the platform slice's CPU.
            """,
            allow_files = [".so"],
            cfg = keep_debug_info,
        ),
        "shell_classes": attr.label(
            doc = """
            aar_import of the unmodified shell AAR, whose classes Android plugins compile
            against without waiting for the engine library.
            """,
            aspects = ANDROID_PAYLOAD_ASPECTS,
        ),
    } | PLATFORM_ATTRS | {
        "_android_packager": attr.label(
            default = Label("//tools/platforms:package_android"),
            cfg = "exec",
            executable = True,
        ),
    } | STRIP_ATTRS,
    toolchains = use_cc_toolchain(mandatory = False),
    fragments = ["cpp"],
)

def _provided(target, provider, field):
    """Return a depset field of a target's provider, empty without the provider."""
    return getattr(target[provider], field) if provider in target else depset()

def _extension_libraries(extension, abi):
    """The extension's library and its runtime dependencies, delivered under abi."""
    library = extension.library
    origin = "res://%s: %s (ABI %s)" % (extension.descriptor_path, library.tags, abi)
    return [{"file": library.file, "abi": abi, "origin": origin}] + [
        {"file": file, "abi": abi, "origin": origin + " runtime dependency " + path}
        for path, file in library.runtime_dependencies.items()
    ]

def _jni_libraries_impl(ctx):
    libraries = []
    pack = ctx.attr.pack[GodotPackInfo]
    target_cpu = target_platform(ctx).cpu
    abi = _platform_slice_abi(ctx)

    # The pack's project holds the extensions of each of its platform slices; this ABI
    # delivers those configured for its CPU, with their runtime dependencies.
    for extension in pack.project.runtime_extensions:
        library = extension.library
        if library.operating_system == "android" and library.cpu == target_cpu:
            libraries += _extension_libraries(extension, abi)
    stripped = _strip_libraries(ctx, libraries)
    libraries = stripped.libraries
    symbols = stripped.symbols
    output = ctx.actions.declare_file(ctx.label.name + ".zip")

    engine_check = check_engine(ctx, {
        "--android-manifest": _provided(
            ctx.attr.runtime,
            StarlarkAndroidResourcesInfo,
            "transitive_manifests",
        ),
        "--android-native-libs": _provided(
            ctx.attr.runtime,
            AndroidNativeLibsInfo,
            "native_libs",
        ),
    } | pack_facts(pack), engine = ctx.attr.runtime, values = {"--android-abi": abi}, pack = pack)
    _android_zip(ctx, libraries, output)
    return [
        DefaultInfo(files = depset([output])),
        OutputGroupInfo(_validation = depset(engine_check)),
        CcInfo(),
        AndroidNativeLibsInfo(native_libs = depset([output])),
        symbols,
    ]

godot_android_jni_libraries = rule(
    implementation = _jni_libraries_impl,
    attrs = {
        "pack": attr.label(
            doc = "PCK target providing GodotPackInfo.",
            mandatory = True,
            providers = [GodotPackInfo],
        ),
        "runtime": attr.label(
            doc = "The Android runtime, whose manifest and engine library name its version.",
            mandatory = True,
        ),
    } | PLATFORM_ATTRS | {
        "_android_packager": attr.label(
            default = Label("//tools/platforms:package_android"),
            cfg = "exec",
            executable = True,
        ),
    } | ENGINE_CHECK_ATTRS | STRIP_ATTRS,
    toolchains = use_cc_toolchain(mandatory = False),
    fragments = ["cpp"],
)
