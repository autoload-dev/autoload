
config_setting(
    name = "ios_simulator",
    visibility = ["//visibility:private"],
    constraint_values = [{SIMULATOR}],
)
{LIBRARIES}
_IOS_FRAMEWORKS = [
    "ARKit",
    "AVFoundation",
    "AudioToolbox",
    "CoreAudio",
    "CoreGraphics",
    "CoreHaptics",
    "CoreMedia",
    "CoreMotion",
    "CoreText",
    "CoreVideo",
    "Foundation",
    "GameController",
    "Metal",
    "OpenGLES",
    "QuartzCore",
    "Security",
    "SystemConfiguration",
    "UIKit",
    "UniformTypeIdentifiers",
]

apple_static_xcframework_import(
    name = "ios_debug",
    has_swift = True,
    sdk_dylibs = [
        "c++",
        "z",
        "iconv",
    ],
    sdk_frameworks = _IOS_FRAMEWORKS,
    weak_sdk_frameworks = select({
        ":ios_simulator": [],
        "//conditions:default": ["MetalFX"],
    }),
    xcframework_imports = glob(["ios/libgodot.ios.debug.xcframework/**"]),
    deps = {DEBUG_DEPS},
    alwayslink = False,
)

apple_static_xcframework_import(
    name = "ios_release",
    has_swift = True,
    sdk_dylibs = [
        "c++",
        "z",
        "iconv",
    ],
    sdk_frameworks = _IOS_FRAMEWORKS,
    weak_sdk_frameworks = select({
        ":ios_simulator": [],
        "//conditions:default": ["MetalFX"],
    }),
    xcframework_imports = glob(["ios/libgodot.ios.release.xcframework/**"]),
    deps = {RELEASE_DEPS},
    alwayslink = False,
)
