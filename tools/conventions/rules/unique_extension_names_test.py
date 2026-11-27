"""unique-extension-names: no two add-on modules' extensions share a name."""

import unittest

from tools.conventions.rules.unique_extension_names import UniqueExtensionNames
from tools.conventions.test_support import AddonModuleTest


class UniqueExtensionNamesTest(AddonModuleTest):
    rule = UniqueExtensionNames()

    def test_extension_names_are_unique_across_modules(self) -> None:
        self.module("widget")
        self.module("gadget")
        build = "addons/gadget/gadget/BUILD.bazel"
        self.write(
            build,
            (self.root / build)
            .read_text()
            .replace("gadget_extension", "widget_extension"),
        )
        findings = self.messages()
        self.assertEqual(len(findings), 1)
        self.assertIn("widget_extension is taken by", findings[0])

    def test_extension_names_are_read_from_calls_not_text(self) -> None:
        self.module("widget")
        self.module("gadget")
        build = "addons/gadget/gadget/BUILD.bazel"
        text = (self.root / build).read_text()
        # A comment declares no extension; a name after other arguments still counts.
        self.write(build, text + '# godot_cc_extension(name = "widget_extension")\n')
        self.assertEqual([], self.messages())
        moved = text.replace(
            'godot_cc_extension(\n    name = "gadget_extension",',
            'godot_cc_extension(\n    tags = [],\n    name = "widget_extension",',
        )
        self.assertNotEqual(moved, text)
        self.write(build, moved)
        findings = self.messages()
        self.assertEqual(len(findings), 1)
        self.assertIn("widget_extension is taken by", findings[0])


if __name__ == "__main__":
    unittest.main()
