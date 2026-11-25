"""The generator writes a module, or one add-on into a module, with derived names."""

from tools.addons.declarations import SEGMENT
from tools.addons.new import TOKEN, Names, generate
from tools.addons.test_support import RepositoryTestCase
from tools.addons.uids import is_uid
from tools.setup.modules import SELFTEST, addon_modules


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
        examples = self.root / "examples/addons/widget"
        scene = (examples / "main/demo.tscn").read_text()
        uid = (examples / "main/demo.gd.uid").read_text().strip()
        self.assertRegex(uid, r"^uid://[a-z0-9]+$")
        self.assertIn(f'uid="{uid}" path="res://main/demo.gd"', scene)
        source = (self.root / ".bcr/addons/widget/source.template.json").read_text()
        self.assertIn('"strip_prefix": "autoload_widget-{VERSION}"', source)
        self.assertIn(
            "@autoload_widget//...",
            (self.root / ".bcr/addons/widget/presubmit.yml").read_text(),
        )
        self.assertIn(
            "//examples/addons/widget/main",
            (examples / "BUILD.bazel").read_text(),
        )
        self.assertFalse((self.root / "addons/widget/examples").exists())
        generated = [
            path
            for tree in ("addons/widget", ".bcr/addons/widget", "examples/addons/widget")
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


class DeclarationTest(RepositoryTestCase):
    def test_a_new_module_is_declared_in_the_root_s_segment(self) -> None:
        generate("widget", root=self.root)
        generate("gadget", root=self.root)
        text = (self.root / SEGMENT).read_text()
        self.assertLess(
            text.index('module_name = "autoload_gadget"'),
            text.index('module_name = "autoload_widget"'),
        )
        self.assertIn('    path = "addons/widget",\n', text)
        generate("widget", "extra", root=self.root)
        self.assertEqual((self.root / SEGMENT).read_text(), text)

    def test_the_self_test_module_is_no_add_on_module(self) -> None:
        generate(SELFTEST, root=self.root, release=False)
        self.assertTrue((self.root / "examples/addons/selftest/project.godot").is_file())
        self.assertNotIn(f"addons/{SELFTEST}", addon_modules(self.root))
        self.assertNotIn("autoload_selftest", (self.root / SEGMENT).read_text())
