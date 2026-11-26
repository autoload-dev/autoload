import argparse
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any
from unittest import mock

from tools.engine.configure import (
    pin_digest,
    pinned_graph,
    prepare_custom_modules,
    read_lock,
    stand_in_host,
)
from tools.engine.lock import merge, update
from tools.engine.pin import copy_tree, extract
from tools.engine.render import render_unpinned


class PinTest(unittest.TestCase):
    def test_an_unpinned_recipe_fails_each_engine_target_with_the_reason(self) -> None:
        # :pinned fails on every host, which the hub's :pinned collects.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for platform, targets in [
                ("linuxbsd", ["engine_library", "godot"]),
                ("android", ["engine_library", "libgodot_android.so", "godot"]),
                ("ios", ["engine_library"]),
            ]:
                args = argparse.Namespace(
                    platform=platform,
                    pin_bzl="@@autoload_rules_godot+//godot/engine/private:pin.bzl",
                    unpinned_message="recipe: the lock file {reason} it; run @godot//:pin",
                )
                render_unpinned(args, "stale", root)
                build = (root / "BUILD.bazel").read_text()
                self.assertIn(
                    'load("@@autoload_rules_godot+//godot/engine/private:pin.bzl"', build
                )
                for target in [*targets, "pinned"]:
                    self.assertIn(f"godot_unpinned_recipe(name = {target!r}", build)
                self.assertEqual(
                    build.count("godot_unpinned_recipe(name"), len(targets) + 1
                )
                self.assertIn("the lock file pins other sources, patches", build)
            render_unpinned(args, "missing", root)
            self.assertIn(
                "the lock file has no pin for it", (root / "BUILD.bazel").read_text()
            )

    def test_configuration_reads_stand_ins_for_the_host_probes(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ):
            root = Path(directory)
            (root / "tools").mkdir()
            stand_in_host(root, "linuxbsd", root / "tools")
            # Godot's detect.py finds the stand-ins on PATH: pkg-config knows no package.
            for command, code in [
                (["pkg-config", "--version"], 0),
                (["pkg-config", "--exists", "x11"], 1),
                (["wayland-scanner", "-v"], 1),
            ]:
                result = subprocess.run(command, capture_output=True, check=False)
                self.assertEqual(result.returncode, code, command)
            self.assertTrue(os.environ["PATH"].startswith(str(root / "tools")))
            (root / "platform/android").mkdir(parents=True)
            (root / "platform/android/detect.py").write_text(
                'def get_ndk_version():\n    return "29.0.1"\n'
            )
            stand_in_host(root, "android", root / "tools")
            self.assertEqual(os.environ["ANDROID_HOME"], str(root / "tools/android_sdk"))
            self.assertTrue((root / "tools/android_sdk/ndk/29.0.1").is_dir())

    def test_pin_actions_extract_the_archive_below_its_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "godot-4.7.2-stable/core").mkdir(parents=True)
            (root / "godot-4.7.2-stable/core/a.h").write_text("a")
            with tarfile.open(root / "source.tar.gz", "w:gz") as archive:
                archive.add(root / "godot-4.7.2-stable", arcname="godot-4.7.2-stable")
            extract(root / "source.tar.gz", "godot-4.7.2-stable", root / "out")
            self.assertEqual((root / "out/core/a.h").read_text(), "a")
            with zipfile.ZipFile(root / "source.zip", "w") as archive:
                archive.write(
                    root / "godot-4.7.2-stable/core/a.h", "godot-4.7.2-stable/core/a.h"
                )
            extract(root / "source.zip", "godot-4.7.2-stable", root / "zip")
            self.assertEqual((root / "zip/core/a.h").read_text(), "a")

    def test_digest_covers_the_recipe_and_the_capture_tools_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scons = root / "scons"
            (scons / "SCons").mkdir(parents=True)
            (scons / "SCons/__init__.py").write_text('__version__ = "4.10.1"')
            patch = root / "fix.patch"
            patch.write_text("one")
            module = root / "source/_custom_modules/probe"
            module.mkdir(parents=True)
            for name in ["config.py", "SCsub", "probe.cpp"]:
                (module / name).write_text(name)

            def digest(**changes: object) -> str:
                values: dict[str, Any] = {
                    "source_sha256": "1" * 64,
                    "patch": [patch],
                    "patch_strip": 1,
                    "build_profile_digest": "",
                    "custom_modules_root": module.parent,
                    "platform": "linuxbsd",
                    "cpu": "x86_64",
                    "build_target": "editor",
                    "modules": ["gdscript", "probe"],
                    "default_modules": False,
                    "options": ["vulkan=no"],
                    "build_name": "custom",
                } | changes
                return pin_digest(argparse.Namespace(**values), scons)

            first = digest()
            self.assertRegex(first, "^sha256:[0-9a-f]{64}$")
            self.assertEqual(digest(), first)
            for change in [
                {"source_sha256": "2" * 64},
                {"patch_strip": 2},
                {"cpu": "arm64"},
                {"build_target": "template_release"},
                {"modules": ["gdscript"]},
                {"default_modules": True},
                {"options": ["vulkan=yes"]},
                {"build_name": "fork"},
                {"build_profile_digest": "sha256:1"},
            ]:
                self.assertNotEqual(digest(**change), first, change)
            # Editing a module's code keeps the pin; its build scripts and file set do not.
            (module / "probe.cpp").write_text("edited")
            self.assertEqual(digest(), first)
            (module / "SCsub").write_text("edited")
            second = digest()
            self.assertNotEqual(second, first)
            (module / "extra.cpp").write_text("new")
            self.assertNotEqual(digest(), second)
            third = digest()
            patch.write_text("two")
            self.assertNotEqual(digest(), third)
            fourth = digest()
            (scons / "SCons/__init__.py").write_text('__version__ = "4.11.0"')
            self.assertNotEqual(digest(), fourth)

    def test_digest_covers_the_capture_but_not_the_rendering(self) -> None:
        # Changing how a graph renders keeps every pin; changing the capture does not.
        args = argparse.Namespace(
            source_sha256="",
            patch=[],
            patch_strip=1,
            build_profile_digest="",
            custom_modules_root=None,
            platform="linuxbsd",
            cpu="x86_64",
            build_target="editor",
            modules=[],
            default_modules=False,
            options=[],
            build_name="custom",
        )
        with mock.patch("tools.engine.configure.file_digest", return_value="") as digest:
            pin_digest(args, Path("scons"))
        self.assertEqual(
            {Path(call.args[0]).name for call in digest.call_args_list},
            {
                "configure.py",
                "module_graph.py",
                "source_tree.py",
                # The build profile's helpers leave a pinned graph's class list out.
                "build_profile.py",
                "__init__.py",
            },
        )

    def test_a_lock_entry_counts_only_for_its_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "engine.lock.json"
            self.assertEqual(
                pinned_graph(read_lock(lock), "linux_x86_64_editor", "sha256:a"),
                ("missing", None),
            )
            lock.write_text("")
            self.assertEqual(
                pinned_graph(read_lock(lock), "linux_x86_64_editor", "sha256:a"),
                ("missing", None),
            )
            graph = {"version": "4.7.2.stable", "generators": "sha256:g"}
            lock.write_text(
                json.dumps(
                    {
                        "generators": {"sha256:g": [{"spec": {}, "dependencies": []}]},
                        "recipes": {
                            "linux_x86_64_editor": {"digest": "sha256:a", "graph": graph}
                        },
                    }
                )
            )
            self.assertEqual(
                pinned_graph(read_lock(lock), "linux_x86_64_editor", "sha256:a"),
                ("pinned", graph | {"generators": [{"spec": {}, "dependencies": []}]}),
            )
            self.assertEqual(
                pinned_graph(read_lock(lock), "linux_x86_64_editor", "sha256:b"),
                ("stale", None),
            )
            self.assertEqual(
                pinned_graph(read_lock(lock), "macos_arm64_editor", "sha256:a"),
                ("missing", None),
            )

    def test_custom_modules_are_copied_without_package_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = root / "workspace/modules/probe"
            (module / "__pycache__").mkdir(parents=True)
            for name in ["config.py", "SCsub", "BUILD.bazel", "__pycache__/config.pyc"]:
                (module / name).write_text(name)
            self.assertEqual(
                prepare_custom_modules(root / "source", [f"probe={module}"]), ["probe"]
            )
            self.assertEqual(
                sorted(
                    path.name
                    for path in (root / "source/_custom_modules/probe").iterdir()
                ),
                ["SCsub", "config.py"],
            )
            with self.assertRaisesRegex(ValueError, "Invalid custom module declaration"):
                prepare_custom_modules(root / "source", [f"1probe={module}"])

    def test_pin_actions_copy_their_declared_tree_and_merge_sorted_recipes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "repo/core").mkdir(parents=True)
            (root / "repo/core/a.h").write_text("a")
            copy_tree(root / "repo", [str(root / "repo/core/a.h")], root / "copy")
            self.assertEqual((root / "copy/core/a.h").read_text(), "a")
            keys = ["macos_arm64_editor", "linux_x86_64_editor"]
            for key in keys:
                # SCons Value mappings keep their order, which upstream builders depend on.
                spec = {"function": "f", "sources": [{"value": {"z": 1, "a": 2}}]}
                pin = {"digest": key, "graph": {"generators": [{"spec": spec}]}}
                (root / f"{key}.json").write_text(json.dumps(pin))
            merge(
                argparse.Namespace(
                    output=str(root / "engine.lock.json"),
                    recipe=[f"{key}={root / key}.json" for key in keys],
                    variant=[],
                )
            )
            text = (root / "engine.lock.json").read_text()
            lock = json.loads(text)
            self.assertLess(
                text.index('"linux_x86_64_editor"'), text.index('"macos_arm64_editor"')
            )
            self.assertEqual(
                lock["recipes"]["linux_x86_64_editor"]["digest"], "linux_x86_64_editor"
            )
            # Both recipes refer to one stored generator list.
            (reference,) = lock["generators"]
            for key in keys:
                self.assertEqual(lock["recipes"][key]["graph"]["generators"], reference)
                status, graph = pinned_graph(
                    read_lock(root / "engine.lock.json"), key, key
                )
                self.assertEqual(status, "pinned")
                assert graph is not None
                (generator,) = graph["generators"]
                self.assertEqual(list(generator["spec"]), ["function", "sources"])
                self.assertEqual(
                    list(generator["spec"]["sources"][0]["value"]), ["z", "a"]
                )

    def test_runtime_variants_pin_beside_their_recipe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = {"function": "f", "sources": []}
            for name, digest in [("recipe", "sha256:r"), ("variant", "sha256:v")]:
                pin = {"digest": digest, "graph": {"generators": [{"spec": spec}]}}
                (root / f"{name}.json").write_text(json.dumps(pin))
            merge(
                argparse.Namespace(
                    output=str(root / "engine.lock.json"),
                    recipe=[f"macos_arm64_template_release={root}/recipe.json"],
                    variant=[
                        [
                            "macos_arm64_template_release",
                            "@@//app:runtime.gdbuild",
                            f"{root}/variant.json",
                        ]
                    ],
                )
            )
            lock = root / "engine.lock.json"
            key = "macos_arm64_template_release"
            self.assertEqual(pinned_graph(read_lock(lock), key, "sha256:r")[0], "pinned")
            self.assertEqual(
                pinned_graph(read_lock(lock), key, "sha256:v", "@@//app:runtime.gdbuild")[
                    0
                ],
                "pinned",
            )
            self.assertEqual(
                pinned_graph(read_lock(lock), key, "sha256:r", "@@//app:runtime.gdbuild")[
                    0
                ],
                "stale",
            )
            self.assertEqual(
                pinned_graph(read_lock(lock), key, "sha256:v", "@@//app:other.gdbuild")[
                    0
                ],
                "missing",
            )

    def test_a_partial_pin_updates_its_recipes_and_keeps_the_others(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = root / "engine.lock.json"
            old = {"function": "old", "sources": []}
            new = {"function": "new", "sources": []}
            lock.write_text(
                json.dumps(
                    {
                        "generators": {"sha256:old": [{"spec": old}], "sha256:gone": []},
                        "recipes": {
                            "linux_x86_64_editor": {
                                "digest": "l",
                                "graph": {"generators": "sha256:old"},
                            },
                            "macos_arm64_editor": {
                                "digest": "m1",
                                "graph": {"generators": "sha256:gone"},
                            },
                        },
                        "variants": {
                            "linux_x86_64_template_release": {
                                "@@//a:p.gdbuild": {
                                    "digest": "v",
                                    "graph": {"generators": "sha256:old"},
                                }
                            }
                        },
                    }
                )
            )
            partial = root / "partial.json"
            partial.write_text(
                json.dumps(
                    {
                        "generators": {"sha256:new": [{"spec": new}]},
                        "recipes": {
                            "macos_arm64_editor": {
                                "digest": "m2",
                                "graph": {"generators": "sha256:new"},
                            }
                        },
                    }
                )
            )
            update(lock, partial)
            result = json.loads(lock.read_text())
            self.assertEqual(result["recipes"]["macos_arm64_editor"]["digest"], "m2")
            self.assertEqual(result["recipes"]["linux_x86_64_editor"]["digest"], "l")
            self.assertIn("linux_x86_64_template_release", result["variants"])
            # Generator lists no pin refers to any longer leave the lock.
            self.assertEqual(sorted(result["generators"]), ["sha256:new", "sha256:old"])
            # Without a lock file, the partial pin is the lock.
            lock.unlink()
            update(lock, partial)
            self.assertEqual(
                sorted(json.loads(lock.read_text())["recipes"]), ["macos_arm64_editor"]
            )


if __name__ == "__main__":
    unittest.main()
