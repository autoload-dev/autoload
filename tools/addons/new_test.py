"""The generator writes a module, or one add-on into a module, with derived names."""

from tools.addons.new import TOKEN, Names, generate
from tools.addons.test_support import RepositoryTestCase


class NamesTest(RepositoryTestCase):
    def test_an_add_on_named_like_its_module(self) -> None:
        tokens = Names("platform_paths", "platform_paths").tokens()
        self.assertEqual(tokens["module_name"], "autoload_platform_paths")
        self.assertEqual(tokens["extension"], "platform_paths_extension")
        self.assertEqual(tokens["class"], "PlatformPaths")
        self.assertEqual(tokens["title"], "Platform Paths")

    def test_an_add_on_of_a_module_with_several(self) -> None:
        tokens = Names("firebase", "core").tokens()
        self.assertEqual(tokens["extension"], "firebase_core")
        self.assertEqual(tokens["class"], "FirebaseCore")
        self.assertEqual(tokens["title"], "Firebase Core")

    def test_the_self_test_module_drops_its_dot(self) -> None:
        self.assertEqual(Names(".selftest", "selftest").tokens()["module"], "selftest")


class GenerateTest(RepositoryTestCase):
    def read(self, path: str) -> str:
        return (self.root / "addons" / path).read_text()

    def test_a_module_with_its_add_on_examples_and_settings(self) -> None:
        generate("widget", root=self.root)
        self.assertIn('name = "autoload_widget"', self.read("widget/MODULE.bazel"))
        self.assertEqual(self.read("widget/.bazelversion"), (self.root / ".bazelversion").read_text())
        build = self.read("widget/widget/BUILD.bazel")
        self.assertIn('name = "widget_extension"', build)
        self.assertIn("//widget/native/backends/android:plugin", build)
        self.assertIn("class Widget : public godot::Object", self.read("widget/widget/native/widget.h"))
        plugin = "widget/widget/native/backends/android/dev/autoload/widget/widget/WidgetPlugin.java"
        self.assertIn("package dev.autoload.widget.widget;", self.read(plugin))
        scene = self.read("widget/examples/projects/demo/main/demo.tscn")
        uid = self.read("widget/examples/projects/demo/main/demo.gd.uid").strip()
        self.assertRegex(uid, r"^uid://[a-z0-9]+$")
        self.assertIn(f'uid="{uid}" path="res://main/demo.gd"', scene)
        generated = [path for path in (self.root / "addons/widget").rglob("*") if path.is_file()]
        self.assertFalse([path for path in generated if TOKEN.search(path.read_text())])

    def test_an_add_on_joins_an_existing_module(self) -> None:
        generate("firebase", "core", root=self.root)
        module = self.read("firebase/MODULE.bazel")
        written = generate("firebase", "analytics", root=self.root)
        self.assertEqual(self.read("firebase/MODULE.bazel"), module)
        self.assertTrue(all("firebase/analytics/" in path.as_posix() for path in written))
        self.assertIn('name = "firebase_analytics"', self.read("firebase/analytics/BUILD.bazel"))

    def test_existing_add_ons_and_unusual_names_are_refused(self) -> None:
        generate("widget", root=self.root)
        with self.assertRaises(FileExistsError):
            generate("widget", root=self.root)
        for module, addon in (("Widget", None), ("widget", "core-api"), ("_w", None)):
            with self.subTest(module=module, addon=addon), self.assertRaises(ValueError):
                generate(module, addon, root=self.root)
