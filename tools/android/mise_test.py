"""Check the repository's Android environment through the real mise runtime."""

import json
import os
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class MiseEnvironmentTest(unittest.TestCase):
    def test_host_commands_work_before_sdk_installation(self) -> None:
        mise = shutil.which("mise")
        self.assertIsNotNone(mise, "Run this test with mise run test:setup")
        with tempfile.TemporaryDirectory(prefix="rules-godot-mise-") as directory:
            root = Path(directory)
            for name in ("mise.toml", "mise.lock"):
                shutil.copyfile(ROOT / name, root / name)
            (root / "global.toml").write_text("")
            sdk = root / "sdk"
            requirements = tomllib.loads((root / "mise.toml").read_text())["vars"]
            api = requirements["android_api_levels"].split(",")[0]
            env = {
                key: value
                for key, value in os.environ.items()
                if not key.startswith(("__MISE_", "_MISE_", "ANDROID_"))
                and key not in ("JAVA_HOME", "MISE_CONFIG_FILE", "MISE_ENV")
            }
            env.update(
                MISE_GLOBAL_CONFIG_FILE=str(root / "global.toml"),
                MISE_CONFIG_DIR=str(root / "config"),
                MISE_YES="1",
            )
            subprocess.run(
                [str(mise), "trust", str(root / "mise.toml")],
                env=env,
                capture_output=True,
                check=True,
            )
            selections = [
                {"ANDROID_HOME": str(sdk)},
                {"ANDROID_SDK_ROOT": str(sdk)},
                {
                    "ANDROID_SDK_ROOT": str(sdk),
                    "ANDROID_NDK_HOME": "",
                    "ANDROID_NDK_ROOT": "",
                },
                {
                    "ANDROID_SDK_ROOT": str(sdk),
                    "ANDROID_NDK_HOME": str(root / "external-ndk"),
                },
            ]
            for selection in selections:
                with self.subTest(environment=selection):
                    platform = sdk / f"platforms/android-{api}/android.jar"
                    for installed in (False, True):
                        if installed:
                            platform.parent.mkdir(parents=True, exist_ok=True)
                            platform.touch()
                        else:
                            platform.unlink(missing_ok=True)
                            (sdk / "platforms").mkdir(parents=True, exist_ok=True)
                        result = subprocess.run(
                            [
                                str(mise),
                                "exec",
                                "--",
                                "python3",
                                "-c",
                                (
                                    "import json, os; print(json.dumps({key: os.environ.get(key) "
                                    "for key in ('ANDROID_HOME', 'ANDROID_SDK_ROOT', "
                                    "'ANDROID_NDK_HOME', 'ANDROID_NDK_ROOT')}))"
                                ),
                            ],
                            cwd=root,
                            env={**env, **selection},
                            capture_output=True,
                            text=True,
                            check=True,
                        )
                        selected = json.loads(result.stdout)
                        self.assertEqual(
                            selected["ANDROID_HOME"], str(sdk) if installed else ""
                        )
                        self.assertEqual(selected["ANDROID_SDK_ROOT"], str(sdk))
                        expected_ndk = selection.get("ANDROID_NDK_HOME") or str(
                            sdk / "ndk" / requirements["android_ndk_version"]
                        )
                        self.assertEqual(selected["ANDROID_NDK_HOME"], expected_ndk)
                        self.assertEqual(selected["ANDROID_NDK_ROOT"], expected_ndk)


if __name__ == "__main__":
    unittest.main()
