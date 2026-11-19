apple_static_xcframework_import(
    visibility = ["//visibility:private"],
    name = "ios_moltenvk",
    sdk_dylibs = ["c++"],
    sdk_frameworks = [
        "Metal",
        "QuartzCore",
        "Foundation",
        "IOSurface",
    ],
    xcframework_imports = glob(["ios/MoltenVK.xcframework/**"]),
)
