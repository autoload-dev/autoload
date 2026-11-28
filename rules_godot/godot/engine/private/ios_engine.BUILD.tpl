apple_static_xcframework_import(
    name = {NAME},
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
    # The targets that carry the package metadata of the libraries Godot bundles; they add
    # no files.
    data = [{BUNDLED_PACKAGES}],
    xcframework_imports = glob(["{XCFRAMEWORK}/**"]),
    deps = {DEPS},
    alwayslink = False,
)
