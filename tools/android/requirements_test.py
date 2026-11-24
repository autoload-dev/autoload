"""Keep Android SDK provisioning and Bazel requirements consistent."""

import shutil
import tempfile
import unittest
from pathlib import Path

from tools.android.requirements import (
    LINUX_TOOLCHAINS,
    PINS,
    application_modules,
    configuration_errors,
)
from tools.setup.modules import module_paths

ROOT = Path(__file__).resolve().parents[2]


class RequirementsTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for name in (PINS, ".bazelignore", "shared.bazelrc", "buildbuddy.bazelrc"):
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, self.root / name)
        # The settings the add-on modules' .bazelrc files import.
        (self.root / "addons").mkdir()
        for bazelrc in (ROOT / "addons").glob("*.bazelrc"):
            shutil.copyfile(bazelrc, self.root / "addons" / bazelrc.name)
        for module in module_paths(ROOT):
            target = self.root / module
            target.mkdir(parents=True, exist_ok=True)
            for name in ("MODULE.bazel", ".bazelrc", ".bazelignore", "addon.pkl"):
                if (ROOT / module / name).is_file():
                    shutil.copyfile(ROOT / module / name, target / name)
        (self.root / LINUX_TOOLCHAINS).parent.mkdir(parents=True)
        shutil.copyfile(ROOT / LINUX_TOOLCHAINS, self.root / LINUX_TOOLCHAINS)

    def replace(self, path: str, before: str, after: str) -> None:
        target = self.root / path
        source = target.read_text()
        self.assertIn(before, source)
        target.write_text(source.replace(before, after))

    def test_repository_requirements_are_provisioned(self) -> None:
        self.assertEqual(module_paths(ROOT), module_paths(self.root))
        self.assertLessEqual(
            {".", "rules_godot", "rules_godot/examples", "rules_godot/tests"},
            set(module_paths(self.root)),
        )
        self.assertEqual(configuration_errors(self.root), [])

    def test_detects_an_unprovisioned_development_api_of_the_root(self) -> None:
        self.replace("rules_godot/MODULE.bazel", "api_level = 35", "api_level = 999")
        errors = configuration_errors(self.root)
        self.assertEqual(len(errors), 1)
        self.assertIn("rules_godot/MODULE.bazel: Android api_level 999", errors[0])
        self.assertFalse(
            errors[0].startswith(("rules_godot/examples/", "rules_godot/tests/"))
        )

    def test_detects_an_unprovisioned_module_api(self) -> None:
        self.replace(
            "rules_godot/examples/MODULE.bazel", "api_level = 35", "api_level = 999"
        )
        errors = configuration_errors(self.root)
        self.assertEqual(len(errors), 1)
        self.assertIn(
            "rules_godot/examples/MODULE.bazel: Android api_level 999", errors[0]
        )

    def test_detects_a_build_tools_bump_missing_from_a_consumer(self) -> None:
        self.replace(
            PINS,
            '"build_tools": "35.0.0"',
            '"build_tools": "99.0.0"',
        )
        errors = configuration_errors(self.root)
        # Every module that builds applications, then the Linux toolchains.
        self.assertEqual(len(errors), len(application_modules(self.root)) + 1)
        self.assertTrue(all("build_tools_version '35.0.0'" in error for error in errors))
        self.assertTrue(errors[-1].startswith(f"{LINUX_TOOLCHAINS}: "))

    def test_detects_an_ndk_bump_missing_from_the_linux_toolchains(self) -> None:
        self.replace(
            PINS,
            '"ndk": "29.0.14206865"',
            '"ndk": "30.0.1"',
        )
        errors = configuration_errors(self.root)
        self.assertEqual(len(errors), 1)
        self.assertIn(f"{LINUX_TOOLCHAINS}: Linux NDK '29.0.14206865'", errors[0])

    def test_detects_an_api_level_missing_from_the_linux_sdk(self) -> None:
        self.replace(
            PINS, '"api_levels": ["35", "36"]', '"api_levels": ["35", "36", "37"]'
        )
        errors = configuration_errors(self.root)
        self.assertEqual(len(errors), 1)
        self.assertIn(f"{LINUX_TOOLCHAINS}: Linux api levels ['35', '36']", errors[0])

    def test_detects_an_unprovisioned_config_override(self) -> None:
        with (self.root / "rules_godot/tests/.bazelrc").open("a") as bazelrc:
            bazelrc.write("build:x --@androidsdk//:api_level=999\n")
        errors = configuration_errors(self.root)
        self.assertEqual(len(errors), 1)
        self.assertIn("rules_godot/tests/.bazelrc:", errors[0])
        self.assertIn("api_level '999'", errors[0])

    def test_detects_an_unprovisioned_override_in_an_imported_bazelrc(self) -> None:
        with (self.root / "shared.bazelrc").open("a") as shared:
            shared.write("build:x --@androidsdk//:api_level=999\n")
        errors = configuration_errors(self.root)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("shared.bazelrc:"), errors[0])
        self.assertIn("api_level '999'", errors[0])

    def test_finds_the_sdk_by_its_extension_under_any_proxy_name(self) -> None:
        self.replace("rules_godot/examples/MODULE.bazel", "android_sdk = ", "sdk = ")
        self.replace(
            "rules_godot/examples/MODULE.bazel",
            "android_sdk.configure(",
            "sdk.configure(",
        )
        self.replace(
            "rules_godot/examples/MODULE.bazel", "api_level = 35", "api_level = 999"
        )
        errors = configuration_errors(self.root)
        self.assertEqual(len(errors), 1)
        self.assertIn(
            "rules_godot/examples/MODULE.bazel: Android api_level 999", errors[0]
        )

    def test_does_not_silently_skip_a_computed_requirement(self) -> None:
        self.replace(
            "rules_godot/examples/MODULE.bazel",
            "api_level = 35",
            "api_level = selected_api",
        )
        errors = configuration_errors(self.root)
        self.assertEqual(len(errors), 1)
        self.assertIn("rules_godot/examples/MODULE.bazel:", errors[0])


if __name__ == "__main__":
    unittest.main()
