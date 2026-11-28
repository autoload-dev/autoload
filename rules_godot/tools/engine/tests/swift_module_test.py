import tempfile
import unittest
from pathlib import Path

from tools.engine.compile_options import merge_swift_module_options, swift_module_options


class SwiftModuleTest(unittest.TestCase):
    def test_beta_swift_module_keeps_the_platform_bridge_and_interop_header(
        self,
    ) -> None:
        options = swift_module_options(
            [
                "-wmo",
                "-warnings-as-errors",
                "-cxx-interoperability-mode=default",
                "-emit-object",
                "-emit-objc-header-path",
                "/source/platform/ios/godot_swift_module-Swift.gen.h",
                "-target",
                "arm64-apple-ios15.0-simulator",
                "-sdk",
                "/Applications/Xcode.app/SDK",
                "-import-objc-header",
                "/source/platform/ios/bridging_header_ios.h",
                "-swift-version",
                "6",
                "-parse-as-library",
                "-module-name",
                "godot_swift_module",
                "-I./",
                "-Onone",
                "-g",
            ],
            Path("/source"),
        )
        self.assertEqual(options["bridging_header"], "platform/ios/bridging_header_ios.h")
        self.assertEqual(
            options["generated_header"], "platform/ios/godot_swift_module-Swift.gen.h"
        )
        self.assertEqual(options["module_name"], "godot_swift_module")
        self.assertEqual(
            options["copts"],
            [
                "-warnings-as-errors",
                "-cxx-interoperability-mode=default",
                "-swift-version",
                "6",
                "-parse-as-library",
            ],
        )

    def test_unknown_swift_options_and_undeclared_header_paths_fail(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "Unsupported upstream Swift compiler option"
        ):
            swift_module_options(["-new-upstream-feature"], Path("/source"))
        with self.assertRaisesRegex(ValueError, "outside engine source"):
            swift_module_options(
                ["-import-objc-header", "/host/undeclared.h"], Path("/source")
            )

    def test_overlapping_swift_declarations_require_a_shared_bridge_superset(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "shared.h").write_text("")
            (root / "ios.h").write_text('#import "shared.h"\n')
            (root / "unrelated.h").write_text("")
            base = {
                "module_name": "godot_swift_module",
                "copts": ["-swift-version", "6"],
                "generated_header": None,
            }
            shared = dict(base, bridging_header="shared.h")
            ios = dict(base, bridging_header="ios.h")
            self.assertEqual(merge_swift_module_options(shared, ios, root), ios)
            self.assertEqual(merge_swift_module_options(ios, shared, root), ios)
            with self.assertRaisesRegex(ValueError, "no common declared superset"):
                merge_swift_module_options(
                    ios, dict(base, bridging_header="unrelated.h"), root
                )
            with self.assertRaisesRegex(
                ValueError, "Incompatible upstream Swift modules"
            ):
                merge_swift_module_options(
                    ios, dict(shared, module_name="different"), root
                )

    def test_merging_swift_declarations_preserves_required_generated_headers(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bridge.h").write_text("")
            base = {
                "module_name": "Godot",
                "copts": [],
                "bridging_header": "bridge.h",
                "generated_header": None,
            }
            emitted = dict(base, generated_header="Godot-Swift.h")
            self.assertEqual(merge_swift_module_options(base, emitted, root), emitted)
            self.assertEqual(merge_swift_module_options(emitted, base, root), emitted)
            with self.assertRaisesRegex(
                ValueError, "Incompatible upstream Swift generated header names"
            ):
                merge_swift_module_options(
                    emitted, dict(base, generated_header="Different-Swift.h"), root
                )


if __name__ == "__main__":
    unittest.main()
