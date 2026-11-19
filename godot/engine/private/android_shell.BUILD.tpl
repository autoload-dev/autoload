load({KOTLIN_ANDROID}, "kt_android_library")
load({KOTLIN_CORE}, "kt_javac_options", "kt_kotlinc_options")

package(default_visibility = ["//visibility:public"])

# Godot's Java/Kotlin language level, per target: no Kotlin toolchain is registered.
kt_javac_options(
    name = "java_level",
    release = {JAVA_LEVEL},
    visibility = ["//visibility:private"],
)

kt_kotlinc_options(
    name = "kotlin_level",
    jvm_target = {JAVA_LEVEL},
    visibility = ["//visibility:private"],
)

[kt_android_library(
    name = variant,
    srcs = glob([
        {LIBRARY} + "/src/main/java/**/*.java",
        {LIBRARY} + "/src/main/java/**/*.kt",
    ]) + ["_build_config/%s/%s/BuildConfig.java" % (variant, {PACKAGE_PATH})],
    custom_package = {PACKAGE},
    javac_opts = ":java_level",
    kotlinc_opts = ":kotlin_level",
    manifest = "AndroidManifest.xml",
    resource_files = glob([{LIBRARY} + "/src/main/res/**"]),
    deps = {DEPS},
) for variant in [
    "debug",
    "release",
]]
