"""The shell assets a pack declares for its operating system's exporter."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("//godot/private:shell_assets.bzl", "pack_shell_assets")
load("//godot/private/engine:profiles.bzl", "engine_profile")
load(":mocks.bzl", "mocks")

visibility("private")

def _shell_assets(preset_platform, options):
    written = {}
    ctx = struct(
        label = struct(name = "app"),
        actions = struct(
            declare_file = lambda path: mocks.file("bin/" + path, is_source = False),
            declare_directory = lambda path: mocks.file("bin/" + path, is_source = False),
            write = lambda file, content: written.update({file.path: content}),
        ),
    )
    assets = struct(icon = mocks.file("icon.svg"), splash = mocks.file("splash.png"))
    shell = pack_shell_assets(ctx, preset_platform, engine_profile("4.7.2"), options, assets)
    return shell, written

_ICON_SET = "bin/app.ios/Assets.xcassets/AppIcon.appiconset/"

def _icon_set_entries(written):
    return json.decode(written[_ICON_SET + "Contents.json"])["images"]

def _test_ios_icons_cover_every_size_in_the_default_appearance(env):
    shell, written = _shell_assets("iOS", {})
    icons = engine_profile("4.7.2")["ios"]["icons"]
    env.expect.that_collection([image["name"] for image in shell.spec["images"]]).contains_exactly(
        [name + ".png" for _, name, _, _, _ in icons] + ["splash@2x.png", "splash@3x.png"],
    ).in_order()
    entries = _icon_set_entries(written)
    env.expect.that_dict(entries[0]).contains_exactly(
        {"filename": "Icon-58.png", "idiom": "universal", "platform": "ios", "scale": "2x", "size": "29x29"},
    )

    # The App Store icon's entry leaves out its scale, 1x. The icon must be opaque.
    env.expect.that_dict(entries[-1]).contains_exactly(
        {"filename": "Icon-1024.png", "idiom": "universal", "platform": "ios", "size": "1024x1024"},
    )
    images = {image["name"]: image for image in shell.spec["images"]}
    env.expect.that_bool(images["Icon-1024.png"]["opaque"]).equals(True)
    env.expect.that_bool(images["Icon-58.png"]["opaque"]).equals(False)
    env.expect.that_collection(images["Icon-58.png"]["sources"]).contains_exactly([
        "option:icons/settings_58x58",
        "option:icons/icon_1024x1024",
        "setting:application/config/icon",
        "file:icon.svg",
    ]).in_order()

def _test_ios_dark_icons_follow_the_options_that_set_them(env):
    shell, written = _shell_assets("iOS", {
        "icons/icon_1024x1024_dark": '"res://dark.png"',
        "icons/settings_58x58_tinted": '"res://tinted.png"',
    })
    icons = engine_profile("4.7.2")["ios"]["icons"]
    names = [image["name"] for image in shell.spec["images"]]

    # The dark base icon fills every size; only one size has its own tinted icon.
    env.expect.that_collection(names).contains_exactly(
        [name + ".png" for _, name, _, _, _ in icons] +
        [name + "_dark.png" for _, name, _, _, _ in icons] +
        ["Icon-58_tinted.png", "splash@2x.png", "splash@3x.png"],
    ).in_order()
    images = {image["name"]: image for image in shell.spec["images"]}

    # Dark and tinted icons fall back only to other options. They never use the project's
    # icon or Godot's default icon.
    env.expect.that_collection(images["Icon-58_tinted.png"]["sources"]).contains_exactly([
        "option:icons/settings_58x58_tinted",
        "option:icons/icon_1024x1024_tinted",
    ]).in_order()
    tinted = [entry for entry in _icon_set_entries(written) if entry["filename"] == "Icon-58_tinted.png"]
    env.expect.that_collection(tinted).contains_exactly([{
        "appearances": [{"appearance": "luminosity", "value": "tinted"}],
        "filename": "Icon-58_tinted.png",
        "idiom": "universal",
        "platform": "ios",
        "scale": "2x",
        "size": "29x29",
    }])

def _test_ios_splash_prefers_the_storyboard_image_of_its_scale(env):
    shell, written = _shell_assets("iOS", {})
    images = {image["name"]: image for image in shell.spec["images"]}
    env.expect.that_collection(images["splash@3x.png"]["sources"]).contains_exactly([
        ["option:storyboard/custom_image@3x", "option:storyboard/custom_image@2x"],
        "setting:application/boot_splash/image",
        "file:splash.png",
    ]).in_order()
    image_set = json.decode(written["bin/app.ios/Launch.xcassets/SplashImage.imageset/Contents.json"])
    env.expect.that_collection(image_set["images"]).contains_exactly([
        {"filename": "splash@2x.png", "idiom": "universal", "scale": "2x"},
        {"filename": "splash@3x.png", "idiom": "universal", "scale": "3x"},
    ]).in_order()
    env.expect.that_collection([file.basename for file in shell.splash]).contains_exactly(
        ["Contents.json", "Contents.json", "splash@2x.png", "splash@3x.png"],
    ).in_order()

def shell_assets_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_ios_icons_cover_every_size_in_the_default_appearance,
            _test_ios_dark_icons_follow_the_options_that_set_them,
            _test_ios_splash_prefers_the_storyboard_image_of_its_scale,
        ],
    )
