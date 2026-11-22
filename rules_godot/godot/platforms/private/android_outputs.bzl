"""The public targets of Godot Android applications: the APK or bundle and its debug symbols."""

load(
    "@rules_android//providers:providers.bzl",
    "AndroidBinaryNativeLibsInfo",
    "AndroidBundleInfo",
    "AndroidFeatureFlagSet",
    "AndroidIdeInfo",
    "AndroidIdlInfo",
    "AndroidOptimizationInfo",
    "AndroidPreDexJarInfo",
    "ApkInfo",
    "DataBindingV2Info",
)
load("@rules_android//rules:android_split_transition.bzl", "android_split_transition")
load("@rules_java//java/common:java_info.bzl", "JavaInfo")
load("//godot/platforms/private:launch.bzl", "LAUNCH_ATTRS", "launcher")
load("//godot/private:context.bzl", "TRANSITION_ATTRS")
load("//godot/private:symbols.bzl", "SYMBOLS_ZIP_ATTRS", "symbols_zip")
load("//godot/private/config:settings.bzl", "MERGE_ANDROID_MANIFEST_PERMISSIONS")
load(
    ":android_runtime_bridge.bzl",
    _AndroidSymbolsInfo = "AndroidSymbolsInfo",
    _engine_symbols = "engine_symbols",
)

visibility("private")

# The application, its bundle and its debug symbols merge the uses-permission entries of
# their libraries' manifests: rules_android's merger keeps them only with this option, then
# applies their tools: markers as the Android Gradle plugin's merger does. The public
# targets set it on their edge, so their outputs stay in the default output directory;
# the application's edge to its pack resets it.
def _merge_permissions_impl(_settings, _attr):
    return {MERGE_ANDROID_MANIFEST_PERMISSIONS: True}

_merge_permissions = transition(
    implementation = _merge_permissions_impl,
    inputs = [],
    outputs = [MERGE_ANDROID_MANIFEST_PERMISSIONS],
)

def _linked(ctx, source, basename):
    """Link a rules_android output under the application's own name."""
    output = ctx.actions.declare_file(ctx.label.name + "/" + basename)
    ctx.actions.symlink(output = output, target_file = source)
    return output

_ANDROID_TOOLCHAIN = "@rules_android//toolchains/android:toolchain_type"

def _android_launcher(ctx, manifest):
    """The launcher of bazel run: install on a device or emulator, launch, stream the log."""
    executable = ctx.actions.declare_file(ctx.label.name + ".run")
    manifest = {
        "platform": "android",
        "application_id": ctx.expand_make_variables("application_id", ctx.attr.application_id, {}),
        # Debuggable builds carry the plugin that passes Godot arguments; see
        # godot/platforms/private/android/LaunchArgumentsPlugin.java.
        "launch_arguments": ctx.var["COMPILATION_MODE"] != "opt",
    } | manifest
    return executable, launcher(ctx, executable, manifest)

_LAUNCHER_ATTRS = {
    "application_id": attr.string(
        doc = "The application ID the launcher installs and starts; make variables expand.",
        mandatory = True,
    ),
} | LAUNCH_ATTRS

def _android_app_bundle_impl(ctx):
    source = ctx.attr.app[0][AndroidBundleInfo].unsigned_aab
    output = _linked(ctx, source, ctx.label.name.rsplit("/", 1)[-1] + "_unsigned.aab")

    # bazel run installs the universal APK bundletool derives from the bundle, signed
    # with the debug key that signs APKs.
    bundletool = ctx.toolchains[_ANDROID_TOOLCHAIN].bundletool.files_to_run.executable
    keystore = ctx.attr.app[0][ApkInfo].signing_keys[-1]
    executable, runfiles = _android_launcher(
        ctx,
        {
            "bundle": output,
            "bundletool": bundletool,
            "keystore": keystore,
        },
    )

    # rules_android's base APK remains an implementation input, not a public output.
    return [
        DefaultInfo(files = depset([output]), executable = executable, runfiles = runfiles),
        AndroidBundleInfo(unsigned_aab = output),
    ]

godot_android_app_bundle = rule(
    implementation = _android_app_bundle_impl,
    executable = True,
    attrs = {"app": attr.label(mandatory = True, providers = [AndroidBundleInfo, ApkInfo], cfg = _merge_permissions)} | _LAUNCHER_ATTRS | TRANSITION_ATTRS,
    toolchains = [_ANDROID_TOOLCHAIN],
)

# The providers of rules_android's APK that the public APK passes on unchanged.
_FORWARDED_APK_PROVIDERS = [
    AndroidBinaryNativeLibsInfo,
    AndroidFeatureFlagSet,
    AndroidIdeInfo,
    AndroidIdlInfo,
    AndroidOptimizationInfo,
    AndroidPreDexJarInfo,
    DataBindingV2Info,
    JavaInfo,
]

def _fields(instance):
    """The field names of a provider instance."""
    return [field for field in dir(instance) if field not in ["to_json", "to_proto"]]

def _relinked(value, links):
    """A File replaced by its public link if it has one; any other value unchanged."""
    return links.get(value, value) if type(value) == "File" else value

def _relinked_files(files, links):
    """Files with each replaced by its public link if it has one."""
    return depset([links.get(file, file) for file in files.to_list()])

def _relinked_output_groups(groups, links):
    """
    Output groups that name the public links instead of rules_android's APKs.

    Internal groups such as _validation and _source_jars are transitive and never name
    the APKs; they pass on without flattening.
    """
    return OutputGroupInfo(**{
        name: getattr(groups, name) if name.startswith("_") else _relinked_files(getattr(groups, name), links)
        for name in _fields(groups)
    })

def _android_apk_impl(ctx):
    app = ctx.attr.app[0]
    info = app[ApkInfo]
    links = {
        source: _linked(ctx, source, source.basename.replace(".native_apk", ""))
        for source in [info.signed_apk, info.unsigned_apk]
    }
    outputs = app[DefaultInfo]
    executable, runfiles = _android_launcher(ctx, {"apk": links[info.signed_apk]})
    result = [
        ApkInfo(**{field: _relinked(getattr(info, field), links) for field in _fields(info)}),
        DefaultInfo(
            files = _relinked_files(outputs.files, links),
            executable = executable,
            runfiles = runfiles.merge(outputs.default_runfiles).merge(ctx.runfiles(files = links.values())),
        ),
        coverage_common.instrumented_files_info(ctx, dependency_attributes = ["app"]),
    ]
    result.extend([app[provider] for provider in _FORWARDED_APK_PROVIDERS if provider in app])
    if OutputGroupInfo in app:
        result.append(_relinked_output_groups(app[OutputGroupInfo], links))
    return result

godot_android_apk = rule(
    implementation = _android_apk_impl,
    executable = True,
    attrs = {"app": attr.label(mandatory = True, providers = [ApkInfo], cfg = _merge_permissions)} | _LAUNCHER_ATTRS | TRANSITION_ATTRS,
)

def _android_debug_symbols_zip_impl(ctx):
    files = {}
    for target in ctx.attr.jni_libraries + ctx.attr.runtime:
        if _AndroidSymbolsInfo in target:
            # Every ABI's configuration may package the same engine library.
            for path, file in target[_AndroidSymbolsInfo].files.items():
                files.setdefault(path, file)
    output = ctx.actions.declare_file(ctx.label.name + "/" + ctx.attr.output_name)
    symbols_zip(ctx, files, output)
    return [DefaultInfo(files = depset([output]))]

def _android_debug_symbols_impl(ctx):
    output = ctx.actions.declare_file(ctx.label.name.removesuffix(".debug_symbols") + "_debug_symbols.zip")
    ctx.actions.symlink(output = output, target_file = ctx.file.symbols)
    return [DefaultInfo(files = depset([output]))]

godot_android_debug_symbols = rule(
    implementation = _android_debug_symbols_impl,
    attrs = {"symbols": attr.label(mandatory = True, allow_single_file = [".zip"], cfg = _merge_permissions)} | TRANSITION_ATTRS,
)

godot_android_debug_symbols_zip = rule(
    doc = """
    The unstripped native libraries of an Android application as <abi>/<name>.so
    entries, the layout of the Android Gradle plugin's native-debug-symbols.zip.
    """,
    implementation = _android_debug_symbols_zip_impl,
    attrs = {
        "jni_libraries": attr.label(
            doc = "The application's extension libraries and engine library, packaged as JNI libraries.",
            mandatory = True,
            cfg = android_split_transition,
            providers = [_AndroidSymbolsInfo],
        ),
        "runtime": attr.label(
            doc = "The application's Android runtime, whose engine AAR holds the engine library.",
            mandatory = True,
            cfg = android_split_transition,
            aspects = [_engine_symbols],
        ),
        "output_name": attr.string(mandatory = True),
    } | SYMBOLS_ZIP_ATTRS,
)
