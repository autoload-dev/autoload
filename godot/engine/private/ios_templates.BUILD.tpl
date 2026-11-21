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

{ENGINES}
