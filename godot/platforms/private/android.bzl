"""Godot Android applications built by rules_android, without a nested Gradle build."""

load("@rules_android//rules:rules.bzl", "aar_import", "android_application", "android_binary", "android_library")
load("//godot/private:macros.bzl", "common_kwargs", "filegroup_kwargs")
load("//godot/private/engine:profiles.bzl", "ANDROID_SHELL_DEPS")
load(":android_bootstrap.bzl", "godot_android_bootstrap")
load(":android_jni_libraries.bzl", "godot_android_engine_aar", "godot_android_jni_libraries")
load(":android_outputs.bzl", "godot_android_apk", "godot_android_app_bundle", "godot_android_debug_symbols", "godot_android_debug_symbols_zip")
load(":android_platform_libraries.bzl", "godot_android_manifest_order", "godot_android_platform_libraries")
load(":android_runtime_bridge.bzl", _runtime_bridge_android = "runtime_bridge_android")

visibility(["//godot", "//godot/engine", "//godot/platforms", "//godot/platforms/private/tests"])

# The Java/Android dependencies of Godot's Android shell library; rules_godot contributes
# them to the shared maven repository.
_SHELL_DEPS = [Label(dep) for dep in ANDROID_SHELL_DEPS]

# The Maven dependencies of Godot's template activity: it uses EdgeToEdge, which
# androidx.fragment brings into every graph of the shell library's dependencies.
_ACTIVITY_DEPS = [
    Label("@maven//:androidx_activity_activity"),
    Label("@maven//:androidx_core_core_splashscreen"),
]

_PRIVATE = ["//visibility:private"]

def godot_android_runtime(name, shell, engine_library = None, **kwargs):
    """
    Join Godot's Android shell library with an engine library into one aar_import runtime.

    `shell` is an Android shell AAR file, such as the one of an official release or the
    AAR of a source-built shell library. Without `engine_library`, the shell's own JNI
    libraries are used. With it, the shell AAR is repacked in the configuration of each
    platform slice, as the engine AAR, with that platform slice's engine library as
    `jni/<abi>/libgodot_android.so`; the ABI follows the CPU of the platform slice, so
    one target per variant serves every CPU, and `engine_library` may be a select()
    over the CPU. Delivery copies are stripped as Bazel's `--strip` asks; the
    `<name>.debug_symbols` of applications with this runtime contain them unstripped.
    The ruleset supplies the shell library's Maven dependencies. Use the result as the
    payload of a godot_runtime_component for an Android slot. This macro returns no
    value.

    Example:
    ```starlark
    godot_android_runtime(
        name = "android_release",
        shell = "@godot_android_shell//:release.aar",
        engine_library = "@godot_android_arm64_release//:libgodot_android.so",
    )
    ```

    ### Default outputs
    - files (many): build imported AAR metadata and engine libraries; no run behavior

    Args:
        name: Public aar_import target name.
        shell: Godot's Android shell .aar file.
        engine_library: Optional engine library .so target of the current platform slice.
        **kwargs: Remaining aar_import attributes, such as tags and visibility.
    """
    aar = shell
    if engine_library:
        godot_android_engine_aar(
            name = name + ".engine_aar",
            aar = shell,
            engine_library = engine_library,
            visibility = _PRIVATE,
            **common_kwargs(kwargs)
        )
        aar = ":" + name + ".engine_aar"
    aar_import(name = name, aar = aar, deps = _SHELL_DEPS, **kwargs)

def godot_android_application(
        name,
        pack,
        application_id,
        runtime = None,
        deps = [],
        manifest_values = {},
        manifest = None,
        bundle = False,
        visibility = None,
        **kwargs):
    """
    Build an APK or an Android App Bundle using rules_android.

    The runtime is the Android runtime component the runtime toolchain resolves for
    each platform slice of the Android split and the variant; its version is not
    compared with the editor that exported the pack.
    deps accepts platform libraries: Android libraries and cc_library targets.
    All other keyword arguments are passed to android_binary, including signing and
    resource_files.

    The manifest, activity, launcher icons and splash screen are those Godot's
    Android export writes. Godot reports what it decides for the pack's export:
    the export options with their defaults, such as `package/app_category`,
    `screen/immersive_mode`, `permissions/vibrate` or `version/code`, and the
    project settings with the export's feature overrides, such as
    `application/config/name` and `display/window/handheld/orientation`; the
    engine profile of the pack's Godot version holds the rest of the exporter's
    rules. Without `version/code` and `version/name` in the pack's
    export_options, the build settings `--@autoload_rules_godot//godot:build_number` and
    `--@autoload_rules_godot//godot:app_version` set them, so a release pipeline needs no
    BUILD changes; Godot's defaults and the project's `application/config/version`
    come next. Godot renders the launcher icons from the `launcher_icons/*`
    options or the project's `application/config/icon`; they replace the Android
    shell library's default icons.

    The application shows Android's internally supplied splash screen as
    Godot's export does: the `splash_screen/*` options set its icon, branding
    image and background color.

    Android libraries that the pack's project brings through deps of its
    resources and extensions, such as an add-on's aar_import or Maven
    artifacts, become dependencies of the application: their code, resources
    and manifest entries are packaged, including their uses-permission
    entries, which the manifest merger merges with their tools: markers as in a
    Gradle build.

    Extension libraries follow the pack's variant: with
    `--@autoload_rules_godot//godot:variant=debug`, those tagged debug; the runtime toolchain
    selects the debug runtime component.

    Creates the named android_binary APK target and private bootstrap and extension
    library targets. The public target forwards android_binary providers and
    signing behavior; this macro returns no Starlark value. Building requires
    the Android SDK/NDK and Java toolchains used by rules_android.

    With bundle = True, the named target is instead rules_android's
    android_application: it builds the unsigned bundle `<name>_unsigned.aab`
    for store upload and provides AndroidBundleInfo. The internal base APK is not
    exposed through ApkInfo or default outputs. Packs, imports and native libraries
    are the same targets as for an APK. Sign the bundle outside Bazel before upload,
    for example with jarsigner in the release pipeline.

    `<name>.debug_symbols` builds `<name>_debug_symbols.zip`: the unstripped
    extension libraries and, with a source-built engine library in its
    godot_android_runtime, `libgodot_android.so`, as `<abi>/<name>.so` entries for
    every packaged ABI, the layout Play Console and crash reporters take. The
    application packages these libraries stripped as Bazel's `--strip` asks: always,
    or by default in fastbuild only.

    Example:
        godot_android_application(
            name = "app",
            pack = ":pack",
            application_id = "org.example.game",
        )

    See [Android prerequisites](../../platforms.md#android).

    Args:
        name: APK target name; also the label when neither the export option
            package/name nor the project's config/name sets one.
        pack: Godot PCK target with its project extension providers.
        runtime: Optional fixed Android runtime that replaces the resolved runtime
            component; ruleset fixtures use it to isolate packaging.
        application_id: Android application identifier.
        deps: Additional platform libraries of the application itself; the project's
            platform libraries come through the pack.
        manifest: Optional application manifest, which becomes the main manifest; the
            shell manifest merges below it, as `godot_app.android_manifest` documents.
        manifest_values: Values for the placeholders of the application's and its
            platform libraries' manifests, as `godot_app.android_manifest_values`
            documents; keys the merger treats as overrides fail analysis naming their
            owner. The applicationId override is added here.
        bundle: Build an unsigned Android App Bundle instead of an APK; it keeps the
            PCK uncompressed in the APKs Google Play generates from the bundle.
        visibility: Visibility of the APK or bundle target.
        **kwargs: Remaining android_binary attributes, including signing options.
    """
    common = common_kwargs(kwargs)
    runtime = _application_runtime(name, runtime, common)
    libraries = _application_libraries(name, pack, runtime, deps, common)
    resource_files = kwargs.pop("resource_files", [])
    bootstrap = _application_bootstrap(
        name,
        pack,
        deps,
        manifest = manifest,
        manifest_values = manifest_values,
        resource_files = resource_files,
        common = common,
    )
    _application_debug_symbols(name, libraries.jni_libraries, runtime, visibility, common)
    native_app = name + ".native_apk"
    if bundle:
        # A bundle config makes android_application build an .aab from an
        # android_binary base module named <name>_base.
        native_app = name + ".native_bundle"
        kwargs["bundle_config_file"] = Label("//godot/platforms:android_bundle_config.pb.json")
    (android_application if bundle else android_binary)(
        name = native_app,
        srcs = [bootstrap.java],
        manifest = bootstrap.manifest,
        # The merger treats applicationId as its package override; the application's
        # values fill the placeholders of every merged manifest.
        manifest_values = {"applicationId": application_id} | manifest_values,
        custom_package = "com.godot.game",
        assets = [bootstrap.assets],
        assets_dir = bootstrap.assets_dir,
        # The pack's launcher icons replace the Android shell library's defaults.
        resource_files = [bootstrap.resources] + resource_files,
        deps = libraries.deps + _ACTIVITY_DEPS + bootstrap.shell_library + deps,
        # Native libraries stay uncompressed so the device need not extract
        # them, as android:extractNativeLibs="false" in Godot's export requires.
        nocompress_extensions = ["pck", "so"],
        visibility = _PRIVATE,
        **kwargs
    )
    (godot_android_app_bundle if bundle else godot_android_apk)(
        name = name,
        app = ":" + native_app,
        application_id = application_id,
        toolchains = kwargs.get("toolchains", []),
        visibility = visibility,
        **common
    )

def _application_runtime(name, runtime, common):
    """The fixed runtime, or one that resolves the runtime component per platform slice."""
    if runtime:
        return runtime

    # Resolve the runtime component inside each platform slice of the Android split.
    _runtime_bridge_android(name = name + ".godot_runtime", visibility = _PRIVATE, **common)
    return ":" + name + ".godot_runtime"

def _application_libraries(name, pack, runtime, deps, common):
    """
    Declare the application's JNI libraries, platform libraries and manifest order.

    Args:
        name: The application's target name.
        pack: The application's pack.
        runtime: The application's Android runtime.
        deps: The application's own platform libraries.
        common: Common attributes of every declared target.

    Returns:
        A struct with the JNI libraries' label and `deps`, the first android_binary deps:
        the manifest order, which ranks the libraries' manifests as in a Gradle build,
        then the runtime and the native libraries; the other deps keep their order for
        classes and resources.
    """
    godot_android_jni_libraries(
        name = name + ".godot_jni_libraries",
        pack = pack,
        runtime = runtime,
        visibility = _PRIVATE,
        **common
    )
    godot_android_platform_libraries(
        name = name + ".godot_platform_libraries",
        deps = [pack],
        visibility = _PRIVATE,
        **common
    )
    godot_android_manifest_order(
        name = name + ".godot_manifest_order",
        leading = _ACTIVITY_DEPS + [runtime],
        pack = pack,
        application_deps = deps,
        visibility = _PRIVATE,
        **common
    )
    jni = ":" + name + ".godot_jni_libraries"
    return struct(
        jni_libraries = jni,
        deps = [
            ":" + name + ".godot_manifest_order",
            runtime,
            jni,
            ":" + name + ".godot_platform_libraries",
        ],
    )

def _application_bootstrap(name, pack, deps, manifest, manifest_values, resource_files, common):
    """
    Declare the bootstrap, its output groups and, with an own manifest, the shell library.

    Args:
        name: The application's target name.
        pack: The application's pack.
        deps: The application's own platform libraries.
        manifest: The application's own manifest, or None.
        manifest_values: The application's manifest placeholder values.
        resource_files: The application's resource files.
        common: Common attributes of every declared target.

    Returns:
        A struct with the labels the android_binary takes: the bootstrap as `assets`
        with its `assets_dir`, its `java`, `manifest` and `resources` output groups, and
        the `shell_library` deps, empty without an own manifest.
    """
    godot_android_bootstrap(
        name = name + ".godot_bootstrap",
        pack = pack,
        maven_deps = _SHELL_DEPS + _ACTIVITY_DEPS + deps,
        app_name = name.rsplit("/", 1)[-1],
        manifest_values = manifest_values,
        manifest_override = manifest,
        resource_overrides = resource_files,
        visibility = _PRIVATE,
        **common
    )
    bootstrap = ":" + name + ".godot_bootstrap"
    for group in ["java", "manifest", "resources"] + (["shell_manifest"] if manifest else []):
        native.filegroup(
            name = name + ".godot_bootstrap." + group,
            srcs = [bootstrap],
            output_group = group,
            visibility = _PRIVATE,
            **filegroup_kwargs(common)
        )
    shell_library = []
    if manifest:
        # A manifest-only library: its manifest merges below the application's own.
        android_library(
            name = name + ".godot_bootstrap.shell_library",
            manifest = bootstrap + ".shell_manifest",
            exports_manifest = 1,
            custom_package = "com.godot.game.shell",
            visibility = _PRIVATE,
            **common
        )
        shell_library = [bootstrap + ".shell_library"]
    return struct(
        assets = bootstrap,
        assets_dir = name + ".godot_bootstrap/assets",
        java = bootstrap + ".java",
        manifest = bootstrap + ".manifest",
        resources = bootstrap + ".resources",
        shell_library = shell_library,
    )

def _application_debug_symbols(name, jni_libraries, runtime, visibility, common):
    """Declare the public `<name>.debug_symbols` and the zip it links."""
    godot_android_debug_symbols_zip(
        name = name + ".debug_symbols_zip",
        jni_libraries = jni_libraries,
        runtime = runtime,
        output_name = name.rsplit("/", 1)[-1] + "_debug_symbols.zip",
        visibility = _PRIVATE,
        **common
    )
    godot_android_debug_symbols(
        name = name + ".debug_symbols",
        symbols = ":" + name + ".debug_symbols_zip",
        visibility = visibility,
        **common
    )
