"""
What godot_android_runtime imports, with and without an engine library.

Without an engine library the runtime imports the shell AAR itself. With one, it imports the
engine AAR, which repacks the shell AAR with the engine library under the Android ABI of the
platform slice's CPU.
"""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:truth.bzl", "matching")
load("@rules_testing//lib:util.bzl", "TestingAspectInfo")
load("//godot/platforms/private:android.bzl", "godot_android_runtime")
load(":android_settings.bzl", "ANDROID_SDK", "OWN_TOOLCHAINS")

def _platform(name):
    return {"//command_line_option:platforms": str(Label("//godot/platforms:" + name))} | OWN_TOOLCHAINS

def _file(name, basename):
    native.genrule(
        name = name,
        outs = [name + "/" + basename],
        cmd = "echo 'Analysis-only stand-in' > $@",
        tags = ["manual"],
    )
    return ":" + name

def _runtime(name, **kwargs):
    godot_android_runtime(
        name = name,
        shell = _file(name + "_shell", "shell.aar"),
        tags = ["manual"],
        **kwargs
    )

def _imported_aar(target):
    return target[TestingAspectInfo].attrs.aar

def _test_shell_only_runtime_imports_shell_aar(name):
    _runtime(name + "_runtime")
    analysis_test(
        name = name,
        target = name + "_runtime",
        impl = _shell_only_runtime_imports_shell_aar,
        attrs = {"shell": attr.string()},
        config_settings = _platform("android_arm64"),
        attr_values = ANDROID_SDK | {"shell": str(native.package_relative_label(name + "_runtime_shell"))},
    )

def _shell_only_runtime_imports_shell_aar(env, target):
    env.expect.that_str(str(_imported_aar(target).label)).equals(env.ctx.attr.shell)

def _test_engine_library_runtime_imports_repacked_aar(name):
    _runtime(name + "_runtime", engine_library = _file(name + "_engine", "libgodot_android.so"))
    analysis_test(
        name = name,
        target = name + "_runtime",
        impl = _engine_library_runtime_imports_repacked_aar,
        attrs = {"engine_aar": attr.string(), "shell": attr.string()},
        config_settings = _platform("android_arm64"),
        attr_values = ANDROID_SDK | {
            "engine_aar": str(native.package_relative_label(name + "_runtime.engine_aar")),
            "shell": str(native.package_relative_label(name + "_runtime_shell")),
        },
    )

def _engine_library_runtime_imports_repacked_aar(env, target):
    engine_aar = _imported_aar(target)
    env.expect.that_str(str(engine_aar.label)).equals(env.ctx.attr.engine_aar)
    env.expect.that_collection(
        [file.basename for file in engine_aar[DefaultInfo].files.to_list()],
    ).contains_exactly([Label(env.ctx.attr.engine_aar).name + ".aar"])

def _engine_aar_test(name, platform, abi):
    _runtime(name + "_runtime", engine_library = _file(name + "_engine", "libgodot_android.so"))
    analysis_test(
        name = name,
        target = name + "_runtime.engine_aar",
        impl = _engine_aar_places_library_under_slice_abi,
        attrs = {"abi": attr.string(), "shell": attr.string()},
        config_settings = _platform(platform),
        attr_values = ANDROID_SDK | {"abi": abi, "shell": name + "_runtime_shell/shell.aar"},
    )

def _engine_aar_places_library_under_slice_abi(env, target):
    actions = target[TestingAspectInfo].actions
    manifests = [
        json.decode(action.content)
        for action in actions
        if action.mnemonic == "FileWrite" and action.outputs.to_list()[0].basename.endswith(".jni.json")
    ]
    env.expect.that_collection(manifests, expr = "JNI manifests").has_size(1)
    for manifest in manifests:
        env.expect.that_collection(
            [(entry["abi"], entry["name"]) for entry in manifest],
        ).contains_exactly([(env.ctx.attr.abi, "libgodot_android.so")])
    packaging = [action for action in actions if action.mnemonic == "GodotAndroidJniLibraries"]
    env.expect.that_collection(packaging, expr = "packaging actions").has_size(1)
    for action in packaging:
        env.expect.that_collection(
            [file.short_path for file in action.inputs.to_list()],
            expr = "packaging inputs",
        ).contains_predicate(matching.str_endswith(env.ctx.attr.shell))

def _test_engine_aar_places_library_under_slice_abi(name):
    _engine_aar_test(name + "_arm64", "android_arm64", "arm64-v8a")
    _engine_aar_test(name + "_x86_64", "android_x86_64", "x86_64")
    native.test_suite(name = name, tests = [name + "_arm64", name + "_x86_64"])

def android_runtime_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_shell_only_runtime_imports_shell_aar,
            _test_engine_library_runtime_imports_repacked_aar,
            _test_engine_aar_places_library_under_slice_abi,
        ],
    )
