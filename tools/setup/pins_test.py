"""The shared pins of the root module and its consumer modules must agree."""

import tempfile
import textwrap
import unittest
from pathlib import Path

from tools.setup import checkout
from tools.setup.pins import drifts, module_pins

MODULE = textwrap.dedent("""
    module(name = "{name}")

    bazel_dep(name = "rules_android", version = "{android}")
    bazel_dep(name = "toolchains_buildbuddy", version = "0.0.4", dev_dependency = True)

    android_sdk = use_extension(
        "@rules_android//rules:rule.bzl", "android_sdk_repository_extension"
    )
    android_sdk.configure(api_level = 35, build_tools_version = "35.0.0")
    toolchains = use_extension("//godot:extensions.bzl", "godot_android_toolchains")
    toolchains.configure(ndk_api_level = 24)

    godot_engines = use_extension("//godot:extensions.bzl", "godot_engines")
    godot_engines.engine(name = "godot", default = True, version = "4.7.2")
    godot_engines.source(
        engine = "godot",
        sha256 = "abc",
        strip_prefix = "godot-4.7.2-stable",
        urls = ["https://example.com/godot.tar.gz"],
        version = "4.7.2",
    )

    http_archive = use_repo_rule("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")
    http_archive(name = "gdunit4", sha256 = "def", urls = ["https://example.com/gdunit.tar.gz"])

    maven = use_extension("@rules_jvm_external//:extensions.bzl", "maven")
    maven.install(
        name = "maven",
        artifacts = ["androidx.fragment:fragment:{fragment}", "org.example:only:1.0"],
    )
""")


class PinsTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / ".bazelignore").write_text("examples\ntests\n")
        for module in (".", "examples", "tests"):
            self.write(
                module, MODULE.format(fragment="1.8.6", name=module, android="0.8.0")
            )

    def write(self, module: str, text: str, version: str = "9.3.0") -> None:
        path = self.root / module
        path.mkdir(parents=True, exist_ok=True)
        (path / "MODULE.bazel").write_text(text)
        (path / ".bazelversion").write_text(version + "\n")

    def run_check(self) -> tuple[int, str]:
        """The check's status and its lines, as a failing test reports them."""
        lines = drifts(self.root)
        return (1 if lines else 0), "".join(f"{line}\n" for line in lines)

    def test_equal_pins_pass_silently(self) -> None:
        self.assertEqual((0, ""), self.run_check())

    def test_a_drift_names_the_module_the_pin_and_both_values(self) -> None:
        self.write(
            "tests", MODULE.format(fragment="1.8.6", name="tests", android="0.8.1")
        )
        self.assertEqual(
            (
                1,
                (
                    "tests/MODULE.bazel: bazel_dep:rules_android is 0.8.1, "
                    "examples/MODULE.bazel has 0.8.0\n"
                ),
            ),
            self.run_check(),
        )

    def test_maven_artifact_versions_are_shared_pins(self) -> None:
        self.write(
            "tests",
            MODULE.format(fragment="1.8.5", name="tests", android="0.8.0").replace(
                '"org.example:only:1.0"', '"org.example:only:2.0"'
            ),
        )
        self.write(
            "examples",
            MODULE.format(fragment="1.8.6", name="examples", android="0.8.0").replace(
                '"org.example:only:1.0"', '"org.example:other:1.0"'
            ),
        )
        self.write(
            ".",
            MODULE.format(fragment="1.8.6", name=".", android="0.8.0").replace(
                ', "org.example:only:1.0"', ""
            ),
        )
        self.assertEqual(
            (
                1,
                (
                    "tests/MODULE.bazel: maven.install:maven:androidx.fragment:fragment is 1.8.5, "
                    "examples/MODULE.bazel has 1.8.6\n"
                ),
            ),
            self.run_check(),
        )

    def lock(self, module: str, name: str, content: str) -> None:
        """Declare a Maven installation with a lock file of the given content."""
        path = self.root / module
        (path / "third_party").mkdir(exist_ok=True)
        (path / "third_party" / f"{name}.json").write_text(content)
        source = (path / "MODULE.bazel").read_text()
        (path / "MODULE.bazel").write_text(
            source
            + f'maven.install(name = "{name}", lock_file = "//third_party:{name}.json")\n'
        )

    def test_the_shared_tool_lock_files_must_be_equal(self) -> None:
        self.lock(".", "bazel_worker_maven", "{}")
        self.lock("examples", "bazel_worker_maven", "{}")
        self.lock("tests", "bazel_worker_maven", '{"drifted": true}')
        status, output = self.run_check()
        self.assertEqual(1, status)
        self.assertIn(
            "tests/third_party/bazel_worker_maven.json: "
            "maven.install:bazel_worker_maven.lock_file is ",
            output,
        )

    def test_other_lock_files_may_differ(self) -> None:
        self.lock(".", "maven", "{}")
        self.lock("examples", "maven", '{"other": true}')
        self.assertEqual((0, ""), self.run_check())

    def test_bazel_versions_are_shared_pins(self) -> None:
        self.write(
            "examples",
            MODULE.format(fragment="1.8.6", name="examples", android="0.8.0"),
            "9.4.0",
        )
        status, output = self.run_check()
        self.assertEqual(1, status)
        self.assertIn("examples/.bazelversion: bazelversion is 9.4.0", output)

    def test_pins_of_one_module_only_are_not_compared(self) -> None:
        self.write(
            "tests",
            MODULE.format(fragment="1.8.6", name="tests", android="0.8.0")
            + 'godot_engines.engine(name = "beta", version = "4.8.0-beta1")\n'
            + 'http_file(name = "bundletool", sha256 = "x", urls = ["https://b"])\n',
        )
        self.assertEqual((0, ""), self.run_check())

    def test_every_module_the_root_ignores_is_compared(self) -> None:
        (self.root / ".bazelignore").write_text("examples\ntests\nconsumer\n")
        self.write(
            "consumer",
            MODULE.format(fragment="1.8.6", name="consumer", android="0.9.0"),
        )
        status, output = self.run_check()
        self.assertEqual(1, status)
        self.assertIn("consumer/MODULE.bazel: bazel_dep:rules_android is 0.9.0", output)

    def test_the_ruleset_version_is_no_pin(self) -> None:
        dependency = 'bazel_dep(name = "autoload_rules_godot", version = "{}")\n'
        for module, version in (("examples", "0.0.0"), ("tests", "0.1.1")):
            self.write(
                module,
                MODULE.format(fragment="1.8.6", name=module, android="0.8.0")
                + dependency.format(version),
            )
        self.assertEqual((0, ""), self.run_check())

    def test_tags_of_other_extensions_are_no_pins(self) -> None:
        other = (
            'other = use_extension("//other:extensions.bzl", "other")\n'
            "other.configure(api_level = {level})\n"
        )
        for module, level in (("examples", 1), ("tests", 2)):
            self.write(
                module,
                MODULE.format(fragment="1.8.6", name=module, android="0.8.0")
                + other.format(level=level),
            )
        self.assertEqual((0, ""), self.run_check())

    def test_every_kind_of_pin_is_read(self) -> None:
        self.assertEqual(
            {
                "bazel_dep:rules_android": "0.8.0",
                "bazel_dep:toolchains_buildbuddy": "0.0.4",
                "android_sdk_repository_extension.configure:api_level": 35,
                "android_sdk_repository_extension.configure:build_tools_version": "35.0.0",
                "godot_android_toolchains.configure:ndk_api_level": 24,
                "godot_engines.engine:godot.version": "4.7.2",
                "godot_engines.source:godot.sha256": "abc",
                "godot_engines.source:godot.strip_prefix": "godot-4.7.2-stable",
                "godot_engines.source:godot.urls": ["https://example.com/godot.tar.gz"],
                "godot_engines.source:godot.version": "4.7.2",
                "http_archive:gdunit4.sha256": "def",
                "http_archive:gdunit4.urls": ["https://example.com/gdunit.tar.gz"],
                "maven.install:maven:androidx.fragment:fragment": "1.8.6",
                "maven.install:maven:org.example:only": "1.0",
            },
            module_pins(MODULE.format(fragment="1.8.6", name="root", android="0.8.0")),
        )


class CheckoutTest(unittest.TestCase):
    def test_the_modules_of_the_checkout_share_their_pins(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual([], drifts(checkout.copy(Path(directory))))


if __name__ == "__main__":
    unittest.main()
