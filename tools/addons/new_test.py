"""The generator writes a module, or one add-on into a module, with derived names."""

import subprocess
from unittest import mock

from tools.addons.new import PIN_ATTEMPTS, TOKEN, Names, generate, pin
from tools.addons.test_support import RepositoryTestCase
from tools.addons.uids import is_uid


class NamesTest(RepositoryTestCase):
    def test_an_add_on_named_like_its_module(self) -> None:
        tokens = Names("platform_paths").tokens("9.3.0")
        self.assertEqual(tokens["module_name"], "autoload_platform_paths")
        self.assertEqual(tokens["extension"], "platform_paths_extension")
        self.assertEqual(tokens["class"], "PlatformPaths")
        self.assertEqual(tokens["title"], "Platform Paths")

    def test_an_add_on_of_a_module_with_several(self) -> None:
        tokens = Names("firebase", "core").tokens("9.3.0")
        self.assertEqual(tokens["extension"], "firebase_core")
        self.assertEqual(tokens["class"], "FirebaseCore")
        self.assertEqual(tokens["title"], "Firebase Core")

    def test_the_self_test_module_drops_its_dot(self) -> None:
        self.assertEqual(Names(".selftest").tokens("9.3.0")["module"], "selftest")

    def test_resource_uids_are_stable_and_godot_reads_them(self) -> None:
        first, again = Names("widget").tokens("9"), Names("widget").tokens("9")
        self.assertEqual(first["script_uid"], again["script_uid"])
        self.assertNotEqual(first["script_uid"], first["scene_uid"])
        self.assertTrue(is_uid(first["scene_uid"]))


class GenerateTest(RepositoryTestCase):
    def read(self, path: str) -> str:
        return (self.root / "addons" / path).read_text()

    def test_a_module_with_its_add_on_examples_and_settings(self) -> None:
        generate("widget", root=self.root)
        self.assertIn('name = "autoload_widget"', self.read("widget/MODULE.bazel"))
        self.assertEqual(
            self.read("widget/.bazelversion"), (self.root / ".bazelversion").read_text()
        )
        build = self.read("widget/widget/BUILD.bazel")
        self.assertIn('name = "widget_extension"', build)
        self.assertIn("//widget/native/backends/android:plugin", build)
        self.assertIn(
            "class Widget : public godot::Object",
            self.read("widget/widget/native/widget.h"),
        )
        plugin = "widget/widget/native/backends/android/dev/autoload/widget/widget/WidgetPlugin.java"
        self.assertIn("package dev.autoload.widget.widget;", self.read(plugin))
        scene = self.read("widget/examples/projects/demo/main/demo.tscn")
        uid = self.read("widget/examples/projects/demo/main/demo.gd.uid").strip()
        self.assertRegex(uid, r"^uid://[a-z0-9]+$")
        self.assertIn(f'uid="{uid}" path="res://main/demo.gd"', scene)
        source = (self.root / ".bcr/addons/widget/source.template.json").read_text()
        self.assertIn('"strip_prefix": "autoload_widget-{VERSION}"', source)
        self.assertIn(
            "@autoload_widget//...",
            (self.root / ".bcr/addons/widget/presubmit.yml").read_text(),
        )
        generated = [
            path
            for tree in ("addons/widget", ".bcr/addons/widget")
            for path in (self.root / tree).rglob("*")
            if path.is_file()
        ]
        self.assertFalse([path for path in generated if TOKEN.search(path.read_text())])

    def test_an_add_on_joins_an_existing_module(self) -> None:
        generate("firebase", "core", root=self.root)
        module = self.read("firebase/MODULE.bazel")
        written = generate("firebase", "analytics", root=self.root)
        self.assertEqual(self.read("firebase/MODULE.bazel"), module)
        self.assertTrue(all("firebase/analytics/" in path.as_posix() for path in written))
        self.assertIn(
            'name = "firebase_analytics"', self.read("firebase/analytics/BUILD.bazel")
        )

    def test_a_module_that_is_not_released_gets_no_registry_templates(self) -> None:
        generate("widget", root=self.root, release=False)
        self.assertFalse((self.root / ".bcr/addons").exists())

    def test_existing_add_ons_and_unusual_names_are_refused(self) -> None:
        generate("widget", root=self.root)
        with self.assertRaises(FileExistsError):
            generate("widget", root=self.root)
        for module, addon in (("Widget", None), ("widget", "core-api"), ("_w", None)):
            with self.subTest(module=module, addon=addon), self.assertRaises(ValueError):
                generate(module, addon, root=self.root)


class PinTest(RepositoryTestCase):
    def pin_with(self, returncodes: list[int]) -> tuple[mock.Mock, list[float]]:
        waits: list[float] = []
        codes = iter(returncodes)

        def fake_run(
            command: list[str], check: bool, **_: object
        ) -> subprocess.CompletedProcess[bytes]:
            result = subprocess.CompletedProcess(command, next(codes))
            if check:
                result.check_returncode()
            return result

        with mock.patch("tools.addons.new.subprocess.run", side_effect=fake_run) as run:
            pin("widget", root=self.root, wait=waits.append)
        return run, waits

    def test_the_examples_repin(self) -> None:
        run, waits = self.pin_with([0])
        self.assertEqual(waits, [])
        self.assertEqual(run.call_args.kwargs["env"]["REPIN"], "1")
        self.assertEqual(run.call_args.kwargs["cwd"].name, "examples")

    def test_a_failed_pin_runs_again_after_a_growing_wait(self) -> None:
        run, waits = self.pin_with([1, 1, 0])
        self.assertEqual(run.call_count, 3)
        self.assertEqual(waits, [20, 40])

    def test_a_pin_that_keeps_failing_fails_after_its_last_attempt(self) -> None:
        with self.assertRaises(subprocess.CalledProcessError) as raised:
            self.pin_with([3] * PIN_ATTEMPTS)
        self.assertEqual(raised.exception.returncode, 3)
