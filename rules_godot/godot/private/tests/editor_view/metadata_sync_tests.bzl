"""The writer and test godot_metadata_sync declares, and what each passes to its runner."""

load("@rules_testing//lib:analysis_test.bzl", "analysis_test")
load("@rules_testing//lib:test_suite.bzl", "test_suite")
load("@rules_testing//lib:truth.bzl", "subjects")
load("//godot:defs.bzl", "godot_metadata_sync")
load("//godot/private:view.bzl", "GodotViewInfo")
load("//godot/private/tests:manifests.bzl", "manifest_content")

visibility("private")

_FIXTURE = "//godot/private/tests/editor_view/fixtures/project_edited_in_the_view"
_KINDS = ["node_ids", "resource_uids"]

def _sync(name, **kwargs):
    godot_metadata_sync(
        name = name + "_sync",
        project = _FIXTURE,
        tags = ["manual"],
        deps = [_FIXTURE + ":main"],
        **kwargs
    )
    return {"test": name + "_sync.test", "view": name + "_sync.view", "writer": name + "_sync"}

def _manifest(target):
    return manifest_content(target, ".run.json")

# <name> writes the metadata and <name>.test checks it; both name the writer, which the
# test's report tells the user to run.
def _test_sync_declares_writer_and_test(name):
    analysis_test(name = name, targets = _sync(name), impl = _sync_declares_writer_and_test)

def _sync_declares_writer_and_test(env, targets):
    metadata = targets.view[GodotViewInfo].metadata
    for subject, target, test in [("writer", targets.writer, False), ("test", targets.test, True)]:
        manifest = _manifest(target)
        env.expect.where(target = subject, field = "test").that_bool(manifest["test"]).equals(test)
        env.expect.where(target = subject, field = "writer").that_str(manifest["writer"]).equals(
            str(targets.writer.label),
        )
        env.expect.where(target = subject, field = "metadata").that_str(manifest["metadata"]).equals(
            metadata.short_path,
        )
        env.expect.where(target = subject).that_collection(
            target[DefaultInfo].default_runfiles.files.to_list(),
            expr = "runfiles",
        ).contains(metadata)

def _test_size_and_timeout_reach_the_test(name):
    analysis_test(
        name = name,
        targets = _sync(name, size = "small", timeout = "short"),
        impl = _size_and_timeout_reach_the_test,
    )

def _size_and_timeout_reach_the_test(env, targets):
    test = env.expect.that_target(targets.test)
    test.attr("size", factory = subjects.str).equals("small")
    test.attr("timeout", factory = subjects.str).equals("short")

# With a metadata flag at require, the test fails while a file lacks that kind.
def _test_required_metadata_reaches_the_test(name):
    analysis_test(
        name = name,
        targets = _sync(name),
        impl = _required_metadata_reaches_the_test,
        config_settings = {str(Label("//godot/metadata:" + kind)): "require" for kind in _KINDS},
    )

def _required_metadata_reaches_the_test(env, targets):
    env.expect.that_collection(_manifest(targets.test)["required"], expr = "required").contains_exactly(
        _KINDS,
    ).in_order()

def metadata_sync_test_suite(name):
    test_suite(
        name = name,
        tests = [
            _test_required_metadata_reaches_the_test,
            _test_size_and_timeout_reach_the_test,
            _test_sync_declares_writer_and_test,
        ],
    )
