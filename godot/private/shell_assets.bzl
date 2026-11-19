"""
The shell assets of a pack: what Godot decides for its export and the images it renders.

The shell action exports the pack's project once more with a probe plugin and
throws that export away. Godot reports its facts, the export options with their
defaults, the project settings with the export's feature overrides and the
values of the version options, and renders the application's icons and splash
images as its exporter for the operating system does. Application rules write their
shell files from these facts.
"""

load(":export_options.bzl", "string_option")

visibility("//godot/...")

_PROJECT_ICON = "setting:application/config/icon"
_LANCZOS = 4

def _option(name):
    return "option:" + name

def _file(file):
    return "file:" + file.path

def asset_catalog(ctx, path, fields = {}):
    """
    Declare and write the Contents.json of an Xcode asset catalog directory.

    Args:
        ctx: Rule context.
        path: The catalog directory, relative to the rule's package.
        fields: Further fields of the Contents.json, such as images.

    Returns:
        The Contents.json File.
    """
    contents = ctx.actions.declare_file(path + "/Contents.json")
    ctx.actions.write(contents, json.encode_indent(
        fields | {"info": {"author": "xcode", "version": 1}},
        indent = "  ",
    ) + "\n")
    return contents

def _android(ctx, profile):
    res = ctx.actions.declare_directory(ctx.label.name + ".android_res")
    splash = ctx.actions.declare_directory(ctx.label.name + ".android_splash")
    main = [_option("launcher_icons/main_192x192"), _PROJECT_ICON]
    foreground = [_option("launcher_icons/adaptive_foreground_432x432")] + main
    layers = [
        ("icon_foreground", foreground),
        ("icon_background", [_option("launcher_icons/adaptive_background_432x432")]),
        ("icon_monochrome", [_option("launcher_icons/adaptive_monochrome_432x432")]),
    ]
    images = []
    for directory, size, layer_size in profile["android"]["icon_densities"]:
        for name, sources, pixels in [("icon", main, size)] + [
            (name, sources, layer_size)
            for name, sources in layers
        ]:
            path = "%s/%s.webp" % (directory, name)
            images.append({
                "name": path,
                "output": res.path + "/" + path,
                "sources": sources,
                "size": pixels,
                "interpolation": _LANCZOS,
            })

    # Godot saves the splash images as they load; a vector drawable stays one.
    images.append({
        "name": "drawable/splash_icon.webp",
        "output": splash.path + "/drawable/splash_icon.webp",
        "sources": [_option("splash_screen/icon")] + foreground,
        "copy": {
            "extension": ".xml",
            "output": splash.path + "/drawable/splash_icon_vector.xml",
        },
    })
    images.append({
        "name": "drawable/splash_branding_image.webp",
        "output": splash.path + "/drawable/splash_branding_image.webp",
        "sources": [_option("splash_screen/branding_image")],
    })
    spec = {
        "directories": [res.path, splash.path],
        "images": images,
        "adaptive_icon": {
            "output": res.path + "/mipmap-anydpi-v26/icon.xml",
            "foreground": "mipmap/icon_foreground.webp",
            "monochrome": "mipmap/icon_monochrome.webp",
        },
    }
    return struct(spec = spec, outputs = [res, splash], icons = [res], splash = [splash])

def _ios(ctx, profile, options, assets):
    ios = profile["ios"]
    prefix = ctx.label.name + ".ios/"
    icon_set = prefix + "Assets.xcassets/AppIcon.appiconset/"
    images = []
    outputs = []
    entries = []
    for appearance in ["", "dark", "tinted"]:
        suffix = "_" + appearance if appearance else ""
        for option, name, size, scale, points in ios["icons"]:
            sources = [_option(option + suffix), _option(ios["base_icon"] + suffix)]
            if appearance and not (
                string_option(options, option + suffix) or
                string_option(options, ios["base_icon"] + suffix)
            ):
                # Dark and tinted icons exist only where the pack sets them.
                continue
            output = ctx.actions.declare_file(icon_set + name + suffix + ".png")
            outputs.append(output)
            images.append({
                "name": output.basename,
                "output": output.path,
                # Without an icon, Godot's default application icon.
                "sources": sources + ([] if appearance else [
                    _PROJECT_ICON,
                    _file(assets.icon),
                ]),
                "size": size,
                "interpolation": _option("application/icon_interpolation"),
                "opaque": option == ios["opaque_icon"],
                "required": True,
            })
            entry = {"idiom": "universal", "platform": "ios", "size": points}
            if appearance:
                entry["appearances"] = [{"appearance": "luminosity", "value": appearance}]
            if scale != "1x":
                entry["scale"] = scale
            entry["filename"] = output.basename
            entries.append(entry)
    icons = [
        asset_catalog(ctx, prefix + "Assets.xcassets"),
        asset_catalog(ctx, icon_set.removesuffix("/"), {"images": entries}),
    ] + outputs

    # The launch screen's image, Godot's boot splash unless the project or the
    # storyboard options set one.
    image_set = prefix + "Launch.xcassets/SplashImage.imageset"
    splash_images = []
    for scale, other in [("2x", "3x"), ("3x", "2x")]:
        output = ctx.actions.declare_file("%s/splash@%s.png" % (image_set, scale))
        splash_images.append(output)
        images.append({
            "name": output.basename,
            "output": output.path,
            "sources": [
                [
                    _option("storyboard/custom_image@" + scale),
                    _option("storyboard/custom_image@" + other),
                ],
                "setting:application/boot_splash/image",
                _file(assets.splash),
            ],
            "required": True,
        })
    splash = [
        asset_catalog(ctx, prefix + "Launch.xcassets"),
        asset_catalog(ctx, image_set, {"images": [
            {"filename": image.basename, "idiom": "universal", "scale": scale}
            for image, scale in zip(splash_images, ["2x", "3x"])
        ]}),
    ] + splash_images
    return struct(
        spec = {"images": images},
        outputs = outputs + splash_images,
        icons = icons,
        splash = splash,
    )

def _macos(ctx, profile, assets):
    icons = ctx.actions.declare_directory(ctx.label.name + ".macos")
    sources = [
        _option("application/icon"),
        "setting:application/config/macos_native_icon",
        _PROJECT_ICON,
        # Without an icon, Godot's default application icon.
        _file(assets.icon),
    ]

    # Godot assembles the rendered sizes into one .icns file, or copies the
    # .icns file the options name.
    spec = {
        "directories": [icons.path],
        "icns": icons.path + "/icon.icns",
        "images": [
            {
                "name": "icon_%d" % size,
                "sources": sources,
                "size": size,
                "interpolation": _option("application/icon_interpolation"),
            }
            for size in profile["macos"]["icon_sizes"]
        ],
    }
    return struct(spec = spec, outputs = [icons], icons = [icons], splash = [])

def pack_shell_assets(ctx, preset_platform, profile, options, assets):
    """
    Declare the shell assets of a pack's export for its operating system.

    Args:
        ctx: godot_pack rule context.
        preset_platform: Godot's export preset platform name of the pack's operating system.
        profile: The engine profile of the editor that exports the pack.
        options: The pack's export options as Godot literals.
        assets: struct of Godot's default application icon and boot splash Files.

    Returns:
        A struct of facts, the
        File of Godot's facts; spec, the shell action's description; outputs,
        the images the action writes; icons and splash, the Files for
        GodotPackInfo.
    """
    if preset_platform == "Android":
        images, section = _android(ctx, profile), profile["android"]
    elif preset_platform == "iOS":
        images, section = _ios(ctx, profile, options, assets), profile["ios"]
    elif preset_platform == "macOS":
        images, section = _macos(ctx, profile, assets), profile["macos"]
    else:
        images = struct(spec = {"images": [], "directories": []}, outputs = [], icons = [], splash = [])
        section = {"version_options": []}
    return struct(
        facts = ctx.actions.declare_file(ctx.label.name + ".facts.json"),
        spec = images.spec | {"versions": section["version_options"]},
        outputs = images.outputs,
        icons = images.icons,
        splash = images.splash,
    )
