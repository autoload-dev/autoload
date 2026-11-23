apple_static_xcframework_import(
    visibility = ["//visibility:private"],
    name = "ios_accesskit",
    sdk_dylibs = [
        "c++",
        "iconv",
    ],
    sdk_frameworks = [
        "Foundation",
        "UIKit",
        "CoreGraphics",
    ],
    xcframework_imports = glob(["{XCFRAMEWORK}/**"]),
)
