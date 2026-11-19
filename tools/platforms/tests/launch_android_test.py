"""Tests of the Android launcher against a simulated adb and Android SDK."""

import base64
import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from collections.abc import Sequence
from pathlib import Path
from unittest import mock

import launch_android
import launch_common
from launch_common import LaunchError, Options, parse_options

PACKAGE = "org.example.game"


def _options(*argv: str) -> Options:
    return parse_options(list(argv), "android", launch_android.OPTIONS)


class FakeAdb:
    """Answers adb commands from a list of devices and the installed packages."""

    def __init__(self) -> None:
        self.devices = [("emulator-5554", "device")]
        self.installed = False
        self.install_failures: list[str] = []
        self.calls: list[list[str]] = []

    def __call__(
        self, command: Sequence[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        args = list(command[1:])
        if args[:1] == ["-s"]:
            args = args[2:]
        self.calls.append(args)
        return subprocess.CompletedProcess(command, 0, self.answer(args))

    def answer(self, args: list[str]) -> str:
        if args == ["devices", "-l"]:
            lines = [f"{serial} {state} model:Pixel" for serial, state in self.devices]
            return "List of devices attached\n" + "\n".join(lines)
        if args[:2] == ["emu", "avd"]:
            return "medium_phone\nOK"
        if args[:1] == ["install"]:
            if self.install_failures:
                return f"adb: failed to install x.apk: Failure [{self.install_failures.pop(0)}: reason]"
            self.installed = True
            return "Performing Streamed Install\nSuccess"
        if args[:1] == ["uninstall"]:
            self.installed = False
            return "Success"
        if args[:1] == ["shell"]:
            words = shlex.split(args[1])
            if words[:2] == ["pm", "path"]:
                return f"package:/data/app/{PACKAGE}/base.apk" if self.installed else ""
            if words[:2] == ["getprop", "sys.boot_completed"]:
                return "1"
            if words[:2] == ["getprop", "ro.product.cpu.abi"]:
                return "x86_64"
            if words[:3] == ["cmd", "package", "resolve-activity"]:
                return f"priority=0 preferredOrder=0\n{PACKAGE}/com.godot.game.GodotAppLauncher"
            if words[:2] == ["am", "start"]:
                return "Starting: Intent\nStatus: ok"
            if words[:1] == ["pidof"]:
                return "4242"
        return ""

    def installs(self) -> list[list[str]]:
        return [call for call in self.calls if call[:1] == ["install"]]


class AndroidLaunchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.adb = FakeAdb()
        patcher = mock.patch.object(launch_common, "run", self.adb)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.device = launch_android.Adb("adb", "emulator-5554")

    def select(self, *argv: str) -> str:
        with (
            mock.patch.dict(os.environ, {"ANDROID_SERIAL": ""}),
            mock.patch.object(launch_android, "host_tool", return_value="emulator"),
        ):
            return launch_android.select_device(
                _options(*argv), launch_android.Adb("adb"), None
            )

    def install(self, *argv: str) -> None:
        launch_android.install(self.device, "app.apk", PACKAGE, _options(*argv))

    def test_the_only_running_device_is_chosen(self) -> None:
        self.assertEqual(self.select(), "emulator-5554")

    def test_several_devices_need_a_choice(self) -> None:
        self.adb.devices.append(("R58M123", "device"))
        with self.assertRaisesRegex(LaunchError, "several devices run"):
            self.select()
        self.assertEqual(self.select("--device=R58M123"), "R58M123")

    def test_a_running_emulator_is_found_by_its_avd(self) -> None:
        self.assertEqual(self.select("--device=medium_phone"), "emulator-5554")

    def test_an_unauthorized_device_says_what_to_do(self) -> None:
        self.adb.devices = [("R58M123", "unauthorized")]
        with self.assertRaisesRegex(LaunchError, "USB debugging"):
            self.select()

    def test_without_devices_an_avd_starts(self) -> None:
        self.adb.devices = []
        with (
            mock.patch.object(launch_android, "choose_avd", return_value="medium_phone"),
            mock.patch.object(
                launch_android, "start_emulator", return_value="emulator-5554"
            ) as start,
        ):
            self.assertEqual(self.select("--headless"), "emulator-5554")
        self.assertEqual(start.call_args.args[2], "medium_phone")

    def test_a_downgrade_installs_with_d_and_keeps_the_data(self) -> None:
        self.install()
        self.assertEqual(self.adb.installs()[0][:-1], ["install", "-r", "-t", "-d"])

    def test_another_signature_uninstalls_by_default(self) -> None:
        self.adb.installed = True
        self.adb.install_failures = ["INSTALL_FAILED_UPDATE_INCOMPATIBLE"]
        self.install()
        self.assertIn(["uninstall", PACKAGE], self.adb.calls)
        self.assertTrue(self.adb.installed)

    def test_full_storage_with_an_old_copy_uninstalls_it(self) -> None:
        self.adb.installed = True
        self.adb.install_failures = ["INSTALL_FAILED_INSUFFICIENT_STORAGE"]
        self.install()
        self.assertIn(["uninstall", PACKAGE], self.adb.calls)

    def test_failures_without_a_conflict_explain_themselves(self) -> None:
        self.adb.install_failures = ["INSTALL_FAILED_NO_MATCHING_ABIS"]
        with self.assertRaisesRegex(LaunchError, "NO_MATCHING_ABIS.*CPU x86_64"):
            self.install()
        self.assertNotIn(["uninstall", PACKAGE], self.adb.calls)

    def test_grant_permissions_adds_g(self) -> None:
        self.install("--grant-permissions")
        self.assertEqual(self.adb.installs()[0][:-1], ["install", "-r", "-t", "-d", "-g"])

    def test_godot_arguments_reach_the_plugin_through_run_as(self) -> None:
        arguments = ["--verbose", "--name=a,b", "two words"]
        pid = launch_android.start(self.device, PACKAGE, True, arguments)
        self.assertEqual(pid, "4242")
        shells = [shlex.split(call[1]) for call in self.adb.calls if call[0] == "shell"]
        run_as = next(words for words in shells if words[0] == "run-as")
        self.assertEqual(run_as[:4], ["run-as", PACKAGE, "sh", "-c"])
        data = base64.b64encode("\0".join(arguments).encode()).decode()
        self.assertIn(
            f"echo {data} | base64 -d > files/rules_godot_launch_arguments", run_as[4]
        )
        start = next(words for words in shells if words[:2] == ["am", "start"])
        self.assertEqual(
            start,
            ["am", "start", "-W", "-n", f"{PACKAGE}/com.godot.game.GodotAppLauncher"],
        )
        self.assertLess(shells.index(run_as), shells.index(start))

    def test_a_launch_without_arguments_removes_stale_ones(self) -> None:
        launch_android.start(self.device, PACKAGE, True, [])
        self.assertIn(
            ["run-as", PACKAGE, "sh", "-c", "rm -f files/rules_godot_launch_arguments"],
            [shlex.split(call[1]) for call in self.adb.calls if call[0] == "shell"],
        )

    def test_a_booting_emulator_is_waited_for(self) -> None:
        self.adb.devices = [("emulator-5554", "offline")]
        with mock.patch.object(launch_android, "_wait_for_boot") as wait:
            self.assertEqual(self.select(), "emulator-5554")
        wait.assert_called_once()

    def test_android_takes_its_options_and_no_environment(self) -> None:
        _options("--logcat=all", "--grant-permissions", "--emulator-arg=-no-snapshot")
        with self.assertRaisesRegex(LaunchError, "--os does not apply to android"):
            _options("--os=26.4")
        with self.assertRaisesRegex(LaunchError, "--env does not apply to android"):
            _options("--env", "A=1")

    def test_release_builds_refuse_godot_arguments(self) -> None:
        manifest = {
            "platform": "android",
            "application_id": PACKAGE,
            "launch_arguments": False,
            "apk": "app.apk",
        }
        with self.assertRaisesRegex(LaunchError, "-c opt"):
            launch_android.launch(
                manifest, _options("--", "--verbose"), lambda path: path
            )


class AvdTest(unittest.TestCase):
    def setUp(self) -> None:
        self.sdk = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.sdk, True)
        patcher = mock.patch.dict(
            os.environ,
            {
                "ANDROID_SDK_ROOT": str(self.sdk),
                "ANDROID_AVD_HOME": str(self.sdk / "avd"),
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.apk = self.sdk / "app.apk"
        with zipfile.ZipFile(self.apk, "w") as archive:
            archive.writestr(f"lib/{launch_android.host_abi()}/libgodot_android.so", "")
        self.commands: list[list[str]] = []
        patcher = mock.patch.object(launch_common, "run", self.run_tool)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_tool(
        self, command: Sequence[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        self.commands.append(list(command))
        output = ""
        if command[-1] == "-list-avds":
            output = "\n".join(
                sorted(
                    p.name.removesuffix(".avd") for p in (self.sdk / "avd").glob("*.avd")
                )
            )
        if "badging" in command:
            output = "sdkVersion:'24'\ntargetSdkVersion:'36'"
        return subprocess.CompletedProcess(command, 0, output)

    def avd(self, name: str, abi: str) -> None:
        directory = self.sdk / "avd" / (name + ".avd")
        directory.mkdir(parents=True)
        (directory / "config.ini").write_text(f"abi.type={abi}\n")

    def image(self, api: str, tag: str = "google_apis_playstore") -> None:
        (
            self.sdk
            / "system-images"
            / f"android-{api}"
            / tag
            / launch_android.host_abi()
        ).mkdir(parents=True)

    def tools(self) -> None:
        (self.sdk / "build-tools" / "36.1.0").mkdir(parents=True)
        (self.sdk / "build-tools" / "36.1.0" / "aapt2").write_text("")
        bin_directory = self.sdk / "cmdline-tools" / "latest" / "bin"
        bin_directory.mkdir(parents=True)
        (bin_directory / "avdmanager").write_text("")
        (bin_directory / "avdmanager").chmod(0o755)

    def test_medium_phone_is_preferred(self) -> None:
        self.avd("medium_phone", launch_android.host_abi())
        self.avd("tablet", launch_android.host_abi())
        self.assertEqual(
            launch_android.choose_avd("emulator", str(self.apk)), "medium_phone"
        )

    def test_avds_of_another_abi_do_not_suit(self) -> None:
        self.avd("other", "armeabi-v7a")
        self.avd("phone", launch_android.host_abi())
        self.assertEqual(launch_android.choose_avd("emulator", str(self.apk)), "phone")

    def test_without_a_suitable_avd_medium_phone_is_created_from_the_target_api(
        self,
    ) -> None:
        self.tools()
        self.image("35")
        self.image("36", "google_apis")
        self.image("36")
        self.image("36.1")
        self.assertEqual(
            launch_android.choose_avd("emulator", str(self.apk)), "medium_phone"
        )
        create = next(c for c in self.commands if "create" in c)
        self.assertIn(
            f"system-images;android-36;google_apis_playstore;{launch_android.host_abi()}",
            create,
        )
        self.assertEqual(create[create.index("--name") + 1], "medium_phone")

    def test_without_a_system_image_the_error_names_sdkmanager(self) -> None:
        self.tools()
        with self.assertRaisesRegex(
            LaunchError, r'sdkmanager "system-images;android-36;google_apis_playstore;'
        ):
            launch_android.choose_avd("emulator", str(self.apk))
        self.assertFalse([c for c in self.commands if "create" in c])


if __name__ == "__main__":
    unittest.main()
