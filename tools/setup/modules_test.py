"""The setup checks find the checkout's modules and their declarations alike."""

import tempfile
import textwrap
import unittest
from pathlib import Path

from tools.setup.modules import bazelrc_options, declarations, module_paths


class ModulePathsTest(unittest.TestCase):
    def test_the_root_and_the_ignored_directories_that_hold_a_module(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".bazelignore").write_text("examples\n.godot-editor\n# note\nother\n")
            for module in (".", "examples", "other", "unlisted"):
                (root / module).mkdir(exist_ok=True)
                (root / module / "MODULE.bazel").write_text("")
            (root / ".godot-editor").mkdir()
            self.assertEqual((".", "examples", "other"), module_paths(root))

    def test_each_add_on_module(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".bazelignore").write_text("addons\n")
            for module in (".", "addons/b", "addons/a", "addons/selftest"):
                (root / module).mkdir(parents=True, exist_ok=True)
                (root / module / "MODULE.bazel").write_text("")
            (root / "addons/d").mkdir()
            self.assertEqual((".", "addons/a", "addons/b"), module_paths(root))


class DeclarationsTest(unittest.TestCase):
    def test_tags_are_named_by_extension_and_rules_by_repository_rule(self) -> None:
        source = textwrap.dedent("""
            bazel_dep(name = "rules_android", version = "0.8.0")
            sdk = use_extension("@rules_android//rules:rule.bzl", "android_sdk")
            sdk.configure(api_level = 35)
            toolchains = use_extension("//godot:extensions.bzl", "godot_android_toolchains")
            toolchains.configure(ndk_api_level = 24)
            archive = use_repo_rule("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")
            archive(name = "gdunit4", sha256 = "abc")
            use_repo(sdk, "androidsdk")
            "x".format()
        """)
        self.assertEqual(
            [
                ("bazel_dep", ["name", "version"]),
                ("android_sdk.configure", ["api_level"]),
                ("godot_android_toolchains.configure", ["ndk_api_level"]),
                ("http_archive", ["name", "sha256"]),
                ("use_repo", []),
            ],
            [
                (declaration.kind, sorted(declaration.keywords))
                for declaration in declarations(source)
                if declaration.kind not in ("use_extension", "use_repo_rule")
            ],
        )


class BazelrcOptionsTest(unittest.TestCase):
    def test_imports_are_followed_from_the_module_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            (root / "tests/.bazelrc").write_text(
                "build --a\n"
                "import %workspace%/../shared.bazelrc\n"
                "try-import %workspace%/../user.bazelrc\n"
            )
            (root / "shared.bazelrc").write_text("build:x --b=1 # note\n")
            (root / "user.bazelrc").write_text("build --personal\n")
            self.assertEqual(
                [("tests/.bazelrc:1", "--a"), ("shared.bazelrc:1", "--b=1")],
                [
                    (location, option)
                    for location, option in bazelrc_options(root, "tests")
                    if option.startswith("--")
                ],
            )


if __name__ == "__main__":
    unittest.main()
