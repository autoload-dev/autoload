apple_static_xcframework_import(
    visibility = ["//visibility:private"],
    name = "ios_camera_{VARIANT}",
    sdk_frameworks = [
        "AVFoundation",
        "CoreMedia",
        "CoreVideo",
        "Foundation",
    ],
    xcframework_imports = glob(["{XCFRAMEWORK}/**"]),
)
