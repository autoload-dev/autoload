"""Link Godot's native iOS entry point with rules_apple's application pipeline."""

load("@rules_apple//apple:ios.bzl", "ios_application")
load(
    "@rules_apple//apple:providers.bzl",
    "AppleBundleInfo",
    "AppleBundleVersionInfo",
    "AppleCodesigningDossierInfo",
    "AppleDebugOutputsInfo",
    "AppleDsymBundleInfo",
    "AppleExecutableBinaryInfo",
    "IosApplicationBundleInfo",
)
load("@rules_cc//cc:objc_library.bzl", "objc_library")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load("//godot:providers.bzl", "GodotPackInfo")
load(
    "//godot/platforms/private:shell.bzl",
    "ENGINE_CHECK_ATTRS",
    "SHELL_ATTRS",
    "check_engine",
    "privacy_manifest",
    "release_values",
    "shell_file",
)
load("//godot/private:macros.bzl", "common_kwargs", "filegroup_kwargs")
load("//godot/private:minimum_os.bzl", "check_minimum_os")
load("//godot/private:providers.bzl", "GodotRuntimeInfo")
load("//godot/private:release.bzl", "RELEASE_ATTRS")
load("//godot/private:shell_assets.bzl", "asset_catalog")
load("//godot/private:versions.bzl", "IOS_MINIMUM_OS")
load("//godot/private/config:native.bzl", "APPLICATION_OPTIONS")
load("//godot/private/config:settings.bzl", "ENVIRONMENT", "PLATFORM_ATTRS", "target_platform")
load("//godot/private/engine:profiles.bzl", "engine_profile")
load(":ios_runtime_bridge.bzl", "runtime_bridge_ios")
load(":launch.bzl", "LAUNCH_ATTRS", "launcher")

visibility(["//godot", "//godot/platforms", "//godot/platforms/private/tests"])

# The Info.plist keys rules_godot or rules_apple own, with their owners; an application's
# own Info.plist fragments must not set them.
_OWNED_PLIST_KEYS = {
    "CFBundleIdentifier": "godot_app.application_id",
    "CFBundleExecutable": "the godot_app target name",
    "CFBundlePackageType": "the iOS application backend",
    "CFBundleSupportedPlatforms": "the export platform selected with --platforms",
    "MinimumOSVersion": "godot_app.ios_minimum_os_version",
    "UIDeviceFamily": "godot_app.ios_families",
    "CFBundleShortVersionString": "the pack's application/short_version export option or --@autoload_rules_godot//godot:app_version",
    "CFBundleVersion": "the pack's application/version export option or --@autoload_rules_godot//godot:build_number",
    "UILaunchStoryboardName": "godot_app.ios_launch_storyboard",
    "CFBundleIcons": "godot_app.ios_app_icons",
    "CFBundleIcons~ipad": "godot_app.ios_app_icons",
    "CFBundleIconName": "godot_app.ios_app_icons",
}

def _check_platform_deps(platform_deps):
    # ios_application accepts arbitrary deps, so a foreign library can otherwise
    # disappear silently. Keep real platform libraries on the application for aspects.
    for dependency in platform_deps:
        if CcInfo not in dependency:
            fail("iOS platform_deps input %s must provide CcInfo; use platform_resources for bundle resources" % dependency.label)

def _bundle_keys(attr, pack):
    """The Info.plist keys the application sets itself, which _OWNED_PLIST_KEYS lists."""
    return {
        "CFBundleIdentifier": attr.bundle_id,
        "CFBundleExecutable": attr.executable_name,
        "CFBundlePackageType": "APPL",
        "MinimumOSVersion": attr.minimum_os_version,
        "UIDeviceFamily": [number for family, number in [("iphone", 1), ("ipad", 2)] if family in attr.families],
        "CFBundleSupportedPlatforms": ["iPhoneSimulator" if pack.environment == "simulator" else "iPhoneOS"],
    }

def _overrides_privacy_manifest(resources):
    """
    Whether the application's resources have a privacy manifest that replaces the shell's.

    It must lie at the root of the resources; rules_apple keeps one inside a resource
    bundle, localization or framework there.
    """
    return any([
        file.basename == "PrivacyInfo.xcprivacy" and not any([
            part.endswith((".bundle", ".lproj", ".framework"))
            for part in file.short_path.split("/")[:-1]
        ])
        for file in resources
    ])

def _ios_shell_impl(ctx):
    _check_platform_deps(ctx.attr.platform_deps)
    pack = ctx.attr.pack[GodotPackInfo]
    profile = engine_profile(pack.version)
    pack_file = ctx.actions.declare_file(
        ctx.label.name + "/" + ctx.attr.executable_name + ".pck",
    )
    plist = ctx.actions.declare_file(ctx.label.name + "/Godot.plist")
    strings = ctx.actions.declare_file(ctx.label.name + "/InfoPlist.xcstrings")

    # Godot automatically finds <executable>.pck beside the native executable.
    # This also works when 4.8+ templates disable CLI path overrides by default.
    ctx.actions.symlink(output = pack_file, target_file = pack.pack_file)

    # The launch screen's color, beside the pack's splash image.
    catalog = asset_catalog(ctx, ctx.label.name + "/LaunchScreen.xcassets")
    color = ctx.actions.declare_file(
        ctx.label.name +
        "/LaunchScreen.xcassets/LaunchScreenBackground.colorset/Contents.json",
    )
    args = ctx.actions.args()
    args.add("--localizations", strings)
    args.add("--launch-color", color)
    shell_file(
        ctx,
        "ios-plist",
        plist,
        pack,
        {
            "profile": profile["ios"],
            "fallback_name": ctx.attr.app_name,
            "bundle_keys": _bundle_keys(ctx.attr, pack),
            "owned_plist_keys": _OWNED_PLIST_KEYS,
            # The application's own launch storyboard replaces the launch screen.
            "launch_storyboard": bool(ctx.file.launch_storyboard),
        } | release_values(ctx, pack),
        outputs = [strings, color],
        args = args,
        infoplists = pack.project.infoplists,
        overrides = ctx.files.infoplist_overrides,
    )

    resources = [pack_file, strings]
    if not _overrides_privacy_manifest(ctx.files.resource_overrides):
        privacy = ctx.actions.declare_file(ctx.label.name + "/PrivacyInfo.xcprivacy")
        privacy_manifest(ctx, pack, profile, "ios", privacy)
        resources.append(privacy)
    if not ctx.file.launch_storyboard:
        resources += [catalog, color] + pack.splash
    return [
        DefaultInfo(files = depset(resources)),
        OutputGroupInfo(
            plist = depset([plist]),
            app_icons = depset(ctx.files.app_icon_overrides or pack.icons),
        ),
    ]

_ios_shell = rule(
    implementation = _ios_shell_impl,
    attrs = {
        "platform_deps": attr.label_list(),
        "bundle_id": attr.string(mandatory = True),
        "minimum_os_version": attr.string(mandatory = True),
        "families": attr.string_list(mandatory = True),
        "pack": attr.label(
            doc = "PCK target providing GodotPackInfo.",
            mandatory = True,
            providers = [GodotPackInfo],
        ),
        "app_name": attr.string(
            doc = "CFBundleDisplayName when the project's config/name sets none.",
            mandatory = True,
        ),
        "executable_name": attr.string(
            doc = "Executable basename, which also names the .pck file beside it.",
            mandatory = True,
        ),
        "infoplist_overrides": attr.label_list(
            doc = "The application's Info.plist fragments, whose keys the shell leaves out.",
            allow_files = [".plist"],
        ),
        "app_icon_overrides": attr.label_list(
            doc = "The application's app icons, which replace the shell's.",
            allow_files = True,
        ),
        "launch_storyboard": attr.label(
            doc = "The application's launch storyboard, which replaces the shell's launch screen.",
            allow_single_file = [".storyboard", ".xib"],
        ),
        "resource_overrides": attr.label_list(
            doc = "The application's bundle resources; a PrivacyInfo.xcprivacy replaces the shell's.",
            allow_files = True,
        ),
    } | SHELL_ATTRS | RELEASE_ATTRS,
)

def _static_libraries(runtime):
    """The static libraries a runtime target links."""
    if CcInfo not in runtime:
        return []
    return [
        archive
        for linker_input in runtime[CcInfo].linking_context.linker_inputs.to_list()
        for library in linker_input.libraries
        for archive in [library.static_library or library.pic_static_library]
        if archive
    ]

def _ios_extension_libraries_impl(ctx):
    pack = ctx.attr.deps[0][GodotPackInfo]
    project = pack.project
    check_minimum_os(
        ctx.attr.minimum_os_version,
        "ios_minimum_os_version",
        "ios",
        ctx.attr.runtime[GodotRuntimeInfo] if GodotRuntimeInfo in ctx.attr.runtime else None,
        project.runtime_extensions,
    )
    flags = []
    extension_cc_infos = []
    platform = target_platform(ctx)
    if platform.operating_system != "ios" or not platform.cpu:
        fail("iOS extensions require an iOS target platform with a CPU of the CPU table")

    # The pack's project holds the extensions of each of its platform slices; this
    # platform slice links those configured for it.
    for extension in project.runtime_extensions:
        library = extension.library
        if (library.operating_system, library.cpu, library.environment) != (platform.operating_system, platform.cpu, platform.environment):
            continue

        # Godot loads a framework at run time; the extension hands it to rules_apple,
        # which embeds and signs it.
        if library.link_kind != "static":
            continue
        flags.extend(["-Wl,-u,_" + extension.entry_symbol, "-Wl,-exported_symbol,_" + extension.entry_symbol])
        extension_cc_infos.append(library.cc_info)

    # The Godot libraries name the engine's version. Every library needs objects of
    # the platform slice, which the metadata of an XCFramework does not guarantee.
    libraries = _static_libraries(ctx.attr.runtime)
    validation = check_engine(
        ctx,
        {
            "--library": depset([library for library in libraries if "godot" in library.basename]),
            "--ios-library": depset(libraries),
        },
        engine = ctx.attr.runtime,
        values = {"--ios-platform-slice": platform.cpu + ":ios_" + platform.environment},
    )
    linker_input = cc_common.create_linker_input(
        owner = ctx.label,
        user_link_flags = depset(flags),
    )

    # ios_application links the CcInfo of its direct deps; rules_apple's
    # resource, framework and Swift aspects reach the libraries through deps.
    return [
        cc_common.merge_cc_infos(cc_infos = [CcInfo(
            linking_context = cc_common.create_linking_context(
                linker_inputs = depset([linker_input]),
            ),
        )] + extension_cc_infos + [
            target[CcInfo]
            for target in project.platform_libraries
            if CcInfo in target
        ]),
        OutputGroupInfo(_validation = depset(validation)),
    ]

_ios_extension_libraries = rule(
    implementation = _ios_extension_libraries_impl,
    attrs = {
        "deps": attr.label_list(
            doc = """
            The application's pack. Named deps so rules_apple's aspects follow it to
            the platform libraries of the pack's project.
            """,
            mandatory = True,
            providers = [GodotPackInfo],
        ),
        "minimum_os_version": attr.string(
            doc = "The application's minimum iOS version; checked against the runtime's deployment target and the extensions' requirements.",
            mandatory = True,
        ),
        "runtime": attr.label(
            doc = "The runtime: the engine library, whose archive names its version.",
            mandatory = True,
        ),
    } | PLATFORM_ATTRS | ENGINE_CHECK_ATTRS,
)

def ios_application_inputs(name, pack, runtime, minimum_os_version, shell, common):
    """
    Declare the inputs shared by a bundle and the unsigned device-link regression.

    Args:
        name: Prefix of the private input targets.
        pack: Configured start pack.
        runtime: The runtime to link, an engine library target.
        minimum_os_version: Minimum iOS version, for the shell and the extension check.
        shell: The application's other _ios_shell attributes, by name.
        common: Conventional target attributes.

    Returns:
        The shell target name and the dependencies to link.
    """
    data = name.replace("/", "_") + ".godot_shell"
    _ios_shell(
        name = data,
        pack = pack,
        minimum_os_version = minimum_os_version,
        visibility = ["//visibility:private"],
        **(common | shell)
    )
    for group in ["plist", "app_icons"]:
        native.filegroup(
            name = "%s.%s" % (data, group),
            srcs = [":" + data],
            output_group = group,
            visibility = ["//visibility:private"],
            **filegroup_kwargs(common)
        )
    objc_library(
        name = data + ".entry_support",
        srcs = [Label("//godot/platforms:ios_entry_support.mm")],
        sdk_frameworks = ["UIKit"],
        visibility = ["//visibility:private"],
        **common
    )
    _ios_extension_libraries(
        name = data + ".extension_libraries",
        deps = [pack],
        minimum_os_version = minimum_os_version,
        runtime = runtime,
        visibility = ["//visibility:private"],
        **common
    )

    return struct(
        data = data,
        deps = [runtime, ":" + data + ".entry_support", ":" + data + ".extension_libraries"],
    )

_TREE_OUTPUTS = str(Label("@rules_apple//apple/build_settings:use_tree_artifacts_outputs"))
_COMPILATION_MODE = "//command_line_option:compilation_mode"
_NATIVE_OPTIONS = APPLICATION_OPTIONS["ios"]

def _application_settings_impl(settings, _attr):
    # Simulator apps and unoptimized builds are never distributed, so their
    # bundle stays a directory instead of an archive written on every change.
    # Transitions read the compilation mode as an enum value, not a string.
    development = settings[ENVIRONMENT] == "simulator" or str(settings[_COMPILATION_MODE]) != "opt"

    # The application's native options hold for its whole graph, so the rules_apple
    # split configures its native code as the pack's platform slices do.
    return {_TREE_OUTPUTS: settings[_TREE_OUTPUTS] or development} | _NATIVE_OPTIONS

_application_settings = transition(
    implementation = _application_settings_impl,
    inputs = [ENVIRONMENT, _COMPILATION_MODE, _TREE_OUTPUTS],
    outputs = [_TREE_OUTPUTS] + _NATIVE_OPTIONS.keys(),
)

_FORWARDED = [
    AppleBundleInfo,
    AppleBundleVersionInfo,
    AppleCodesigningDossierInfo,
    AppleDebugOutputsInfo,
    AppleDsymBundleInfo,
    AppleExecutableBinaryInfo,
    IosApplicationBundleInfo,
    InstrumentedFilesInfo,
    OutputGroupInfo,
]

def _ios_bundle_impl(ctx):
    application = ctx.attr.application
    default = application[DefaultInfo]

    # The bundle format has its own configuration; publish the bundle beside
    # this target, where the archive was before.
    archive = application[AppleBundleInfo].archive
    published_name = ctx.label.name + "." + archive.extension
    published = ctx.actions.declare_directory(published_name) if archive.is_directory else ctx.actions.declare_file(published_name)
    ctx.actions.symlink(output = published, target_file = archive)

    # bazel run installs with simctl or devicectl itself instead of rules_apple's
    # runner; tools/platforms/launch/launch_ios.py says why.
    executable = ctx.actions.declare_file(ctx.label.name + ".run")
    runfiles = launcher(ctx, executable, {"platform": "ios", "bundle": published})
    return [
        DefaultInfo(
            executable = executable,
            files = depset([published] + [file for file in default.files.to_list() if file != archive]),
            runfiles = runfiles,
        ),
    ] + [application[provider] for provider in _FORWARDED if provider in application]

_ios_bundle = rule(
    doc = """
    Forward an ios_application whose bundle format follows the build's purpose.

    Simulator and non-`opt` builds produce the `.app` directory; optimized
    device builds produce the `.ipa` archive. The application's native code
    builds without Bazel's `--strip`.
    """,
    implementation = _ios_bundle_impl,
    cfg = _application_settings,
    executable = True,
    attrs = {
        "application": attr.label(mandatory = True, providers = [AppleBundleInfo]),
    } | LAUNCH_ATTRS,
)

def _bundle_targets(name, inputs, visibility, common, bundle_name, deps, resources, infoplists, application):
    """
    Declare an iOS application's ios_application, its public bundle and its debug symbols.

    Args:
        name: Name of the public bundle target.
        inputs: What ios_application_inputs returned for the application.
        visibility: Visibility of the public targets.
        common: Conventional target attributes.
        bundle_name: The application's bundle name, or None for the last segment of name.
        deps: The application's own platform libraries.
        resources: The application's own bundle resources.
        infoplists: The application's own Info.plist fragments.
        application: The other ios_application attributes, such as bundle_id,
            minimum_os_version and signing options.
    """
    data = inputs.data

    # rules_apple names its outputs after the last name segment, so the nested
    # application keeps that basename; name forwards it in its bundle format.
    base = name.rpartition("/")[2]
    target = name + ".bundle/" + base
    ios_application(
        name = target,
        bundle_name = bundle_name or base,
        deps = inputs.deps + deps,
        resources = [":" + data] + resources,
        infoplists = [":" + data + ".plist"] + infoplists,
        app_icons = [":" + data + ".app_icons"],
        visibility = ["//visibility:private"],
        **application
    )
    _ios_bundle(
        name = name,
        application = ":" + target,
        visibility = visibility,
        **common
    )
    native.filegroup(
        name = name + ".debug_symbols",
        srcs = [":" + name],
        output_group = "dsyms",
        visibility = visibility,
        **filegroup_kwargs(common)
    )

def godot_ios_application(
        name,
        pack,
        bundle_id,
        runtime = None,
        minimum_os_version = IOS_MINIMUM_OS,
        families = ["iphone", "ipad"],
        deps = [],
        resources = [],
        infoplists = [],
        app_icons = [],
        launch_storyboard = None,
        visibility = None,
        **kwargs):
    """
    Build an iOS app using a static Godot XCFramework containing main().

    The runtime is the iOS runtime component the runtime toolchain resolves for each
    platform slice of the Apple split, with its iOS environment, and the variant, such
    as a static XCFramework import or a source recipe's `:engine_library`; its version is
    not compared with the editor that exported the pack. Godot's own main initializes
    its SwiftUI scene lifecycle. Pass provisioning_profile, entitlements, frameworks,
    plugins and signing arguments directly to rules_apple through kwargs.


    Creates the named ios_application target and private shell and link
    targets; it forwards rules_apple application providers and outputs. It
    returns no Starlark value. Xcode and an iOS toolchain are required on macOS;
    device builds additionally need the selected signing configuration. Static
    extensions in the pack's project are linked with their C++ dependencies.

    The generated Info.plist is the one Godot's iOS export writes. Its values
    come from where Godot's exporter reads them: the pack's export_options under
    Godot's names, such as `application/short_version`,
    `privacy/camera_usage_description`, `capabilities/access_wifi` or
    `application/additional_plist_content`, and the exported project's
    settings, such as `application/config/name` and
    `display/window/handheld/orientation`, with the feature overrides of the
    pack's operating system. Without the version options, the build settings
    `--@autoload_rules_godot//godot:app_version` and `--@autoload_rules_godot//godot:build_number`
    set them, so a release pipeline needs no BUILD changes; the project's
    `application/config/version` comes next.

    The application bundle also gets the privacy manifest PrivacyInfo.xcprivacy
    that Godot generates from the `privacy/*` options, and a launch screen
    (UILaunchScreen) with the splash image of `storyboard/custom_image@2x` and
    `@3x`, else the project's `application/boot_splash/image`, else Godot's
    boot splash, on the color of `storyboard/custom_bg_color` or the project's
    `application/boot_splash/bg_color`. Its app icons are those Godot renders
    for the pack from the `icons/*` options, the project's
    `application/config/icon` or Godot's default icon. A project with
    translations gets the localized display name and the `privacy/*_localized`
    usage descriptions as InfoPlist strings, as Godot's export does.

    Apple libraries that the pack's project brings through deps of its
    resources and extensions, such as an add-on's swift_library, objc_library
    or XCFramework import, are linked into the application together with their
    linker flags and SDK frameworks; their resources are bundled. Info.plist
    fragments of the resources' infoplists are merged.

    `<name>.debug_symbols` is the application's dSYM from rules_apple; the
    engine, static extensions and the application's code are linked into its
    one executable, so the dSYM covers all of them. Build with
    `--apple_generate_dsym`, without which it is empty. rules_apple strips the
    executable with `-c opt --objc_enable_binary_stripping`; Bazel's `--strip`
    applies neither to it nor to the application's other native code.

    Example:
        godot_ios_application(
            name = "app",
            pack = ":pack",
            bundle_id = "org.example.game",
        )

    See [signing and iOS setup](../../platforms.md#ios).

    Args:
        name: iOS application target name; also CFBundleDisplayName when
            neither bundle_name nor the project's config/name sets one.
        pack: Godot PCK target with its project extension providers.
        runtime: Optional fixed runtime target that replaces the resolved runtime
            component; ruleset fixtures use it to isolate packaging.
        bundle_id: Apple application bundle identifier.
        minimum_os_version: Minimum supported iOS version.
        families: Apple device families supported by the application.
        deps: Additional platform libraries the project does not bring.
        resources: Additional application bundle resources; a PrivacyInfo.xcprivacy
            among them replaces the generated privacy manifest.
        infoplists: The application's own Info.plist fragments; they set their keys
            instead of the generated Info.plist and the add-ons' fragments.
        app_icons: The application's own app icons, which replace those Godot renders.
        launch_storyboard: The application's own launch storyboard, which replaces the
            generated launch screen.
        visibility: Visibility of the application target.
        **kwargs: Remaining ios_application attributes, including signing options.
    """
    common = common_kwargs(kwargs)
    if not runtime:
        # Resolve the runtime component inside each platform slice of the Apple split.
        runtime = ":" + name + ".godot_runtime"
        runtime_bridge_ios(
            name = name + ".godot_runtime",
            visibility = ["//visibility:private"],
            **common
        )
    inputs = ios_application_inputs(
        name = name,
        pack = pack,
        runtime = runtime,
        minimum_os_version = minimum_os_version,
        shell = dict(
            bundle_id = bundle_id,
            families = families,
            app_name = kwargs.get("bundle_name") or name,
            executable_name = kwargs.get("executable_name") or kwargs.get("bundle_name") or name,
            platform_deps = deps,
            infoplist_overrides = infoplists,
            app_icon_overrides = app_icons,
            launch_storyboard = launch_storyboard,
            resource_overrides = resources,
        ),
        common = common,
    )
    _bundle_targets(
        name = name,
        inputs = inputs,
        visibility = visibility,
        common = common,
        bundle_name = kwargs.pop("bundle_name", None),
        deps = deps,
        resources = resources,
        infoplists = infoplists,
        application = dict(
            bundle_id = bundle_id,
            minimum_os_version = minimum_os_version,
            families = families,
            launch_storyboard = launch_storyboard,
        ) | kwargs,
    )
