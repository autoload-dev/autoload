"""Exercise SDK reuse and missing-package fallback without network access."""

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.android import sdk as toolchain


class AndroidToolchainTest(unittest.TestCase):
    def setUp(self) -> None:
        environment = mock.patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        os.environ["ANDROID_HOME"] = str(self.root)
        self.patch = mock.patch.object(toolchain.platform, "system", return_value="Linux")
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def write(self, relative: str, content: str = "") -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def complete_sdk(self) -> None:
        self.write("platforms/android-35/android.jar")
        self.write("platforms/android-36/android.jar")
        for name in ["aapt", "aapt2", "zipalign", "lib/apksigner.jar"]:
            self.write("build-tools/35.0.0/" + name)
        self.write("build-tools/35.0.0/source.properties", "Pkg.Revision = 35.0.0\n")
        self.write("ndk/29.0.14206865/toolchains/llvm/prebuilt/linux-x86_64/bin/clang")
        self.write(
            "ndk/29.0.14206865/source.properties", "Pkg.Revision = 29.0.14206865\n"
        )

    def test_complete_preinstalled_sdk_needs_no_installs(self) -> None:
        self.complete_sdk()
        self.assertEqual(toolchain.missing_packages(self.root), [])

    def test_beta_sdk_is_checked_without_reinstalling_stable_packages(self) -> None:
        self.complete_sdk()
        (self.root / "platforms/android-36/android.jar").unlink()
        self.assertEqual(
            toolchain.missing_packages(self.root, ("35", "36")),
            ["platforms;android-36"],
        )
        self.write("platforms/android-36/android.jar")
        self.assertEqual(toolchain.missing_packages(self.root, ("35", "36")), [])

    def test_missing_ndk_keeps_existing_sdk_and_build_tools(self) -> None:
        self.complete_sdk()
        (self.root / "ndk/29.0.14206865/source.properties").unlink()
        self.assertEqual(toolchain.missing_packages(self.root), ["ndk;29.0.14206865"])

    def test_incorrect_revision_is_not_treated_as_installed(self) -> None:
        self.complete_sdk()
        self.write(
            "ndk/29.0.14206865/source.properties", "Pkg.Revision = 28.1.13356709\n"
        )
        self.assertEqual(toolchain.missing_packages(self.root), ["ndk;29.0.14206865"])

    def test_partial_build_tools_install_is_repaired(self) -> None:
        self.complete_sdk()
        (self.root / "build-tools/35.0.0/lib/apksigner.jar").unlink()
        self.assertEqual(toolchain.missing_packages(self.root), ["build-tools;35.0.0"])

    def test_existing_sdkmanager_reused_without_upgrading_cli(self) -> None:
        manager = self.write("cmdline-tools/12.0/bin/sdkmanager")
        manager.chmod(0o755)
        with mock.patch.object(toolchain.shutil, "which", return_value=None):
            self.assertEqual(toolchain.find_sdkmanager(self.root), str(manager))

    def test_missing_sdkmanager_can_trigger_bootstrap(self) -> None:
        with mock.patch.object(toolchain.shutil, "which", return_value=None):
            self.assertIsNone(toolchain.find_sdkmanager(self.root))
        self.assertEqual(len(toolchain.missing_packages(self.root)), 4)

    def test_installer_requests_only_the_missing_pinned_package(self) -> None:
        self.complete_sdk()
        (self.root / "ndk/29.0.14206865/source.properties").unlink()
        with (
            mock.patch.object(toolchain, "find_sdkmanager", return_value="/sdkmanager"),
            mock.patch("sys.argv", ["sdk.py"]),
            mock.patch.object(
                toolchain.subprocess,
                "run",
                side_effect=lambda *args, **kwargs: self.complete_sdk(),
            ) as run,
        ):
            toolchain.main()
        self.assertEqual(
            run.call_args.args[0],
            [
                "/sdkmanager",
                "--sdk_root=" + str(self.root),
                "--install",
                "ndk;29.0.14206865",
            ],
        )

    def test_repeated_bootstrap_does_not_install_existing_packages(self) -> None:
        self.complete_sdk()
        with (
            mock.patch.object(toolchain, "find_sdkmanager", return_value="/sdkmanager"),
            mock.patch("sys.argv", ["sdk.py"]),
            mock.patch.object(toolchain.subprocess, "run") as run,
        ):
            toolchain.main()
            toolchain.main()
        run.assert_not_called()

    def test_complete_sdk_does_not_need_a_manager_or_download_its_fallback(self) -> None:
        self.complete_sdk()
        with (
            mock.patch.object(toolchain, "find_sdkmanager", return_value=None),
            mock.patch("sys.argv", ["sdk.py"]),
            mock.patch.object(toolchain.subprocess, "run") as run,
        ):
            toolchain.main()
        run.assert_not_called()

    def test_fresh_sdk_installs_stable_beta_build_tools_and_ndk(self) -> None:
        def install(*args: object, **kwargs: object) -> None:
            self.complete_sdk()
            self.write("platforms/android-36/android.jar")

        with (
            mock.patch.object(toolchain, "find_sdkmanager", return_value="/sdkmanager"),
            mock.patch("sys.argv", ["sdk.py"]),
            mock.patch.object(toolchain.subprocess, "run", side_effect=install) as run,
        ):
            toolchain.main()
        self.assertEqual(
            run.call_args.args[0],
            [
                "/sdkmanager",
                "--sdk_root=" + str(self.root),
                "--install",
                "platforms;android-35",
                "platforms;android-36",
                "build-tools;35.0.0",
                "ndk;29.0.14206865",
            ],
        )

    def test_missing_manager_downloads_the_pinned_fallback_only_when_needed(self) -> None:
        self.complete_sdk()
        (self.root / "ndk/29.0.14206865/source.properties").unlink()
        with (
            mock.patch.object(toolchain, "find_sdkmanager", return_value=None),
            mock.patch("sys.argv", ["sdk.py"]),
            mock.patch.object(
                toolchain.subprocess,
                "run",
                side_effect=lambda *args, **kwargs: self.complete_sdk(),
            ) as run,
        ):
            toolchain.main()
        self.assertEqual(
            run.call_args.args[0],
            [
                "mise",
                "exec",
                "http:android-commandlinetools",
                "--",
                "sdkmanager",
                "--sdk_root=" + str(self.root),
                "--install",
                "ndk;29.0.14206865",
            ],
        )

    def test_separately_installed_ndk_is_reused(self) -> None:
        self.complete_sdk()
        ndk = self.root / "separate_ndk"
        (self.root / "ndk/29.0.14206865").rename(ndk)
        with (
            mock.patch.dict(os.environ, {"ANDROID_NDK_HOME": str(ndk)}),
            mock.patch("sys.argv", ["sdk.py"]),
            mock.patch.object(toolchain.subprocess, "run") as run,
        ):
            toolchain.main()
        run.assert_not_called()

    def test_incompatible_external_ndk_fails_without_installing_elsewhere(self) -> None:
        self.complete_sdk()
        with (
            mock.patch.dict(
                os.environ, {"ANDROID_NDK_HOME": str(self.root / "wrong_ndk")}
            ),
            mock.patch("sys.argv", ["sdk.py"]),
            mock.patch.object(toolchain.subprocess, "run") as run,
            self.assertRaisesRegex(SystemExit, "ANDROID_NDK_HOME selects"),
        ):
            toolchain.main()
        run.assert_not_called()

    def test_cache_restore_only_requests_missing_packages(self) -> None:
        self.complete_sdk()
        (self.root / "ndk/29.0.14206865/source.properties").unlink()
        output = io.StringIO()
        with (
            mock.patch("sys.argv", ["sdk.py", "--cache-paths"]),
            mock.patch.object(toolchain.subprocess, "run") as run,
            contextlib.redirect_stdout(output),
        ):
            toolchain.main()
        self.assertEqual(
            output.getvalue().splitlines(), [str(self.root / "ndk/29.0.14206865")]
        )
        run.assert_not_called()
        self.complete_sdk()  # Model a cache hit restoring the required package.
        output = io.StringIO()
        with (
            mock.patch("sys.argv", ["sdk.py", "--cache-paths"]),
            contextlib.redirect_stdout(output),
        ):
            toolchain.main()
        self.assertEqual(output.getvalue(), "")

    def test_failed_installation_is_not_reported_as_ready(self) -> None:
        with (
            mock.patch("sys.argv", ["sdk.py"]),
            mock.patch.object(toolchain, "find_sdkmanager", return_value="/sdkmanager"),
            mock.patch.object(toolchain.subprocess, "run"),
            self.assertRaisesRegex(SystemExit, "installation is incomplete"),
        ):
            toolchain.main()

    def test_existing_sdk_manager_is_preferred_over_the_managed_fallback(self) -> None:
        installed = self.write("cmdline-tools/latest/bin/sdkmanager")
        managed = self.write("mise/bin/sdkmanager")
        installed.chmod(0o755)
        managed.chmod(0o755)
        with mock.patch.object(toolchain.shutil, "which", return_value=str(managed)):
            self.assertEqual(toolchain.find_sdkmanager(self.root), str(installed))


if __name__ == "__main__":
    unittest.main()
