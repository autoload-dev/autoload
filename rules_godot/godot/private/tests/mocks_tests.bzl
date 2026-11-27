"""The context mocks record what the code under test asks for."""

load("@rules_testing//lib:test_suite.bzl", "test_suite")
load(":mocks.bzl", "mocks")

visibility("private")

def _test_repository_ctx_records_side_effects(env):
    ctx = mocks.repository_ctx(
        attr = {"patches": []},
        files = {"version.py": "major = 4\n"},
        which = {"patch": "/usr/bin/patch"},
        execute = {"/usr/bin/patch -p1": {"return_code": 1, "stderr": "rejected"}},
    )
    ctx.file("BUILD.bazel", "", executable = False)
    ctx.watch("a.patch")
    result = ctx.execute(["/usr/bin/patch", "-p1", "-i", "a.patch"])
    other = ctx.execute(["true"])

    env.expect.that_str(ctx.read("version.py")).equals("major = 4\n")
    env.expect.that_str(ctx.which("patch")).equals("/usr/bin/patch")
    env.expect.that_bool(ctx.which("scons") == None).equals(True)
    env.expect.that_int(result.return_code).equals(1)
    env.expect.that_str(result.stderr).equals("rejected")
    env.expect.that_int(other.return_code).equals(0)
    env.expect.that_collection([call.method for call in ctx.calls]).contains_exactly(
        ["file", "watch", "execute", "execute"],
    ).in_order()
    env.expect.that_collection(mocks.calls(ctx, "execute")[0].args).contains_exactly(
        ["/usr/bin/patch", "-p1", "-i", "a.patch"],
    ).in_order()

def _test_extract_records_the_archive(env):
    ctx = mocks.repository_ctx()
    ctx.extract("source.tar.gz", stripPrefix = "godot-4.7.2-stable")
    ctx.extract("templates/ios.zip", output = "ios")
    ctx.extract("export_templates.tpz", rename_files = {"a": "kept/a"}, strip_prefix = "kept")
    extracts = mocks.calls(ctx, "extract")
    env.expect.that_collection([call.archive for call in extracts]).contains_exactly(
        ["source.tar.gz", "templates/ios.zip", "export_templates.tpz"],
    ).in_order()
    env.expect.that_str(extracts[0].stripPrefix).equals("godot-4.7.2-stable")
    env.expect.that_str(extracts[1].output).equals("ios")

    # Other arguments are recorded as given.
    env.expect.that_dict(extracts[2].rename_files).contains_exactly({"a": "kept/a"})
    env.expect.that_str(extracts[2].strip_prefix).equals("kept")

def _test_path_struct_names_its_parts(env):
    path = mocks.path("ndk/lib/clang", children = ["18"])
    env.expect.that_bool(path.exists).equals(True)
    env.expect.that_str(path.basename).equals("clang")
    env.expect.that_str(path.dirname).equals("ndk/lib")
    env.expect.that_collection([child.path for child in path.readdir()]).contains_exactly(
        ["ndk/lib/clang/18"],
    )
    env.expect.that_bool(mocks.path("absent", exists = False).exists).equals(False)

def _test_tree_paths_follow_the_tree(env):
    ctx = mocks.repository_ctx(
        tree = ["lib/clang/18/include/stddef.h", "lib/clang/18/lib", "bin/clang"],
        files = {"source.properties": "Pkg.Revision = 29\n"},
    )
    env.expect.that_bool(ctx.path("bin/clang").exists).equals(True)
    env.expect.that_bool(ctx.path("lib/clang").exists).equals(True)
    env.expect.that_bool(ctx.path("source.properties").exists).equals(True)
    env.expect.that_bool(ctx.path("bin/lld").exists).equals(False)
    children = ctx.path("lib/clang").readdir()
    env.expect.that_collection([child.basename for child in children]).contains_exactly(["18"])
    env.expect.that_collection([child.basename for child in children[0].readdir()]).contains_exactly(
        ["include", "lib"],
    ).in_order()
    env.expect.that_str(ctx.read(ctx.path("source.properties"))).equals("Pkg.Revision = 29\n")
    env.expect.that_str(mocks.repository_ctx().path("bin/clang")).equals("bin/clang")

def _test_getenv_records_the_variable(env):
    ctx = mocks.repository_ctx(environ = {"ANDROID_HOME": "/sdk"})
    env.expect.that_str(ctx.getenv("ANDROID_HOME")).equals("/sdk")
    env.expect.that_bool(ctx.getenv("SDKROOT") == None).equals(True)
    env.expect.that_collection([call.variable for call in mocks.calls(ctx, "getenv")]).contains_exactly(
        ["ANDROID_HOME", "SDKROOT"],
    ).in_order()
    env.expect.that_bool(ctx.repo_metadata(reproducible = True).reproducible).equals(True)

def _test_module_ctx_lists_modules_and_tags(env):
    root = mocks.module("root", is_root = True, prebuilt = [mocks.tag(name = "godot")])
    dependency = mocks.module("dependency", prebuilt = [])
    ctx = mocks.module_ctx([root, dependency], os_name = "mac os x")

    env.expect.that_collection([module.name for module in ctx.modules]).contains_exactly(
        ["root", "dependency"],
    ).in_order()
    env.expect.that_str(ctx.modules[0].tags.prebuilt[0].name).equals("godot")
    env.expect.that_bool(ctx.modules[1].is_root).equals(False)
    env.expect.that_str(ctx.os.name).equals("mac os x")

def _test_errors_collects_fail_messages(env):
    errors, fail_ = mocks.errors()
    fail_("first", 1)
    fail_("second")
    env.expect.that_collection(errors).contains_exactly(["first 1", "second"]).in_order()

def mocks_test_suite(name):
    test_suite(
        name = name,
        basic_tests = [
            _test_repository_ctx_records_side_effects,
            _test_extract_records_the_archive,
            _test_path_struct_names_its_parts,
            _test_tree_paths_follow_the_tree,
            _test_getenv_records_the_variable,
            _test_module_ctx_lists_modules_and_tags,
            _test_errors_collects_fail_messages,
        ],
    )
