"""Tests of the iOS launcher: bundles, device listing, Simulator and device choice, installs."""

import dataclasses
import io
import os
import plistlib
import shutil
import stat
import subprocess
import tempfile
import unittest
import zipfile
from collections.abc import Sequence
from pathlib import Path
from unittest import mock

import launch_ios
from launch_common import LaunchError, Options, parse_options


def _options(*argv: str) -> Options:
    return parse_options(list(argv), "ios", launch_ios.OPTIONS)


def _bundle(directory: Path, platform: str = "iPhoneSimulator") -> Path:
    app = directory / "app.app"
    app.mkdir()
    with open(app / "Info.plist", "wb") as plist:
        plistlib.dump(
            {
                "CFBundleIdentifier": "org.example.game",
                "CFBundleSupportedPlatforms": [platform],
                "MinimumOSVersion": "15.0",
                "UIDeviceFamily": [1, 2],
            },
            plist,
        )
    (app / "app").write_text("binary")
    for path in (app / "Info.plist", app / "app", app):
        path.chmod(stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)
    return app


def _make_writable(directory: Path) -> None:
    for path in [directory, *directory.rglob("*")]:
        path.chmod(0o755)


class BundleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.addCleanup(_make_writable, self.directory)
        (self.directory / "source").mkdir()
        (self.directory / "copy").mkdir()

    def test_the_copy_of_a_read_only_bundle_is_writable(self) -> None:
        bundle = launch_ios.read_bundle(str(_bundle(self.directory / "source")))
        self.assertEqual(bundle.bundle_id, "org.example.game")
        self.assertTrue(bundle.simulator)
        self.assertEqual((bundle.minimum_os, bundle.family), ((15, 0), "iPhone"))
        path = Path(launch_ios.writable_copy(bundle, str(self.directory / "copy")))
        for entry in [path, *path.rglob("*")]:
            self.assertTrue(os.access(entry, os.W_OK), entry)

    def test_an_ipa_is_read_in_place_and_unpacked_to_install(self) -> None:
        app = _bundle(self.directory / "source", "iPhoneOS")
        ipa = self.directory / "app.ipa"
        with zipfile.ZipFile(ipa, "w") as archive:
            for path in [app, *app.rglob("*")]:
                archive.write(
                    path, "Payload/" + str(path.relative_to(self.directory / "source"))
                )
        bundle = launch_ios.read_bundle(str(ipa))
        self.assertFalse(bundle.simulator)
        path = launch_ios.writable_copy(bundle, str(self.directory / "copy"))
        self.assertEqual(path, str(self.directory / "copy" / "Payload" / "app.app"))


_TYPES: list[dict] = [
    {
        "identifier": "type.iPhone-17",
        "name": "iPhone 17",
        "productFamily": "iPhone",
        "minRuntimeVersion": 1,
    },
    {
        "identifier": "type.iPhone-18-Pro",
        "name": "iPhone 18 Pro",
        "productFamily": "iPhone",
        "minRuntimeVersion": 2,
    },
    {
        "identifier": "type.iPad",
        "name": "iPad Pro",
        "productFamily": "iPad",
        "minRuntimeVersion": 2,
    },
]
_RUNTIMES = [
    {"identifier": "runtime.26", "version": "26.4", "supportedDeviceTypes": _TYPES},
    {"identifier": "runtime.27", "version": "27.0", "supportedDeviceTypes": _TYPES},
]
_BUNDLE = launch_ios.Bundle("app.app", "org.example.game", True, (15, 0), "iPhone")


def _simulators(*devices: launch_ios.Simulator) -> launch_ios.Simulators:
    types = {t["identifier"]: (index, t) for index, t in enumerate(_TYPES)}
    return launch_ios.Simulators(list(devices), _RUNTIMES, types)


def _sim(
    udid: str,
    name: str,
    state: str = "Shutdown",
    runtime: Sequence[int] = (27, 0),
    kind: str = "type.iPhone-17",
) -> launch_ios.Simulator:
    return launch_ios.Simulator(udid, name, state, tuple(runtime), kind)


class SimulatorChoiceTest(unittest.TestCase):
    def choose(
        self, simulators: launch_ios.Simulators, *argv: str
    ) -> launch_ios.Simulator:
        with mock.patch.dict(os.environ, {"BAZEL_APPLE_DEVICE_UDID": ""}):
            return launch_ios.select_simulator(_options(*argv), _BUNDLE, simulators)

    def test_the_only_booted_simulator_is_chosen(self) -> None:
        chosen = self.choose(
            _simulators(_sim("A", "iPhone 17"), _sim("B", "iPhone 17", "Booted", (26, 4)))
        )
        self.assertEqual(chosen.udid, "B")

    def test_several_booted_simulators_need_a_choice(self) -> None:
        simulators = _simulators(
            _sim("A", "iPhone 17", "Booted"), _sim("B", "iPhone 17", "Booted")
        )
        with self.assertRaisesRegex(LaunchError, "several Simulators run"):
            self.choose(simulators)
        self.assertEqual(self.choose(simulators, "--device=B").udid, "B")

    def test_a_name_prefers_the_booted_then_the_newest(self) -> None:
        simulators = _simulators(
            _sim("A", "iPhone 17", runtime=(26, 4)), _sim("B", "iPhone 17")
        )
        self.assertEqual(self.choose(simulators, "--device=iPhone 17").udid, "B")
        self.assertEqual(
            self.choose(simulators, "--device=iPhone 17", "--os=26").udid, "A"
        )

    def test_without_a_booted_simulator_the_newest_plain_one_boots(self) -> None:
        simulators = _simulators(
            _sim("A", "iPhone 17", runtime=(26, 4)),
            _sim("B", "Team devices", kind="type.iPhone-18-Pro"),
            _sim("C", "iPhone 17"),
            _sim("D", "iPad Pro", kind="type.iPad"),
        )
        self.assertEqual(self.choose(simulators).udid, "C")
        self.assertEqual(
            self.choose(simulators, "--simulator-type=iPhone 18 Pro").udid, "B"
        )

    def test_without_a_suitable_simulator_one_is_created(self) -> None:
        created = subprocess.CompletedProcess([], 0, "NEW\n")
        with mock.patch.object(launch_ios, "xcrun", return_value=created) as xcrun:
            chosen = self.choose(_simulators())
        self.assertEqual(chosen.udid, "NEW")
        xcrun.assert_called_once_with(
            "simctl", "create", "iPhone 18 Pro", "type.iPhone-18-Pro", "runtime.27"
        )

    def test_simulator_type_and_os_choose_what_is_created(self) -> None:
        created = subprocess.CompletedProcess([], 0, "NEW\n")
        with mock.patch.object(launch_ios, "xcrun", return_value=created) as xcrun:
            self.choose(_simulators(), "--simulator-type=iPhone 17", "--os=26")
        xcrun.assert_called_once_with(
            "simctl", "create", "iPhone 17", "type.iPhone-17", "runtime.26"
        )

    def test_os_and_type_pass_over_an_unsuitable_booted_simulator(self) -> None:
        simulators = _simulators(
            _sim("A", "iPhone 17", "Booted"), _sim("B", "iPhone 17", runtime=(26, 4))
        )
        self.assertEqual(self.choose(simulators).udid, "A")
        self.assertEqual(self.choose(simulators, "--os=26.4").udid, "B")

    def test_no_start_device_needs_a_booted_simulator(self) -> None:
        with self.assertRaisesRegex(LaunchError, "no Simulator runs"):
            self.choose(_simulators(_sim("A", "iPhone 17")), "--no-start-device")

    def test_a_name_without_a_suitable_simulator_fails(self) -> None:
        simulators = _simulators(_sim("A", "iPhone 17", runtime=(14, 0)))
        with self.assertRaisesRegex(
            LaunchError, r"no Simulator iPhone 17 with iOS 15\.0 or newer"
        ):
            self.choose(simulators, "--device=iPhone 17")


class DeviceChoiceTest(unittest.TestCase):
    def device(self, **changes: object) -> launch_ios.Device:
        device = launch_ios.Device("ID", "Phone", "UDID", True, "enabled", True)
        return dataclasses.replace(device, **changes)

    def choose(
        self, devices: Sequence[launch_ios.Device], *argv: str
    ) -> launch_ios.Device:
        with mock.patch.dict(os.environ, {"BAZEL_APPLE_DEVICE_UDID": ""}):
            return launch_ios.select_device(_options(*argv), devices)

    def test_the_connected_device_is_chosen(self) -> None:
        devices = [self.device(), self.device(identifier="X", connected=False)]
        self.assertEqual(self.choose(devices).identifier, "ID")

    def test_a_named_device_must_be_connected(self) -> None:
        with self.assertRaisesRegex(LaunchError, "not connected"):
            self.choose([self.device(connected=False)], "--device=UDID")
        with self.assertRaisesRegex(LaunchError, "no iOS device Tablet; --list-devices"):
            self.choose([self.device()], "--device=Tablet")
        self.assertEqual(self.choose([self.device()], "--device=Phone").identifier, "ID")

    def test_preflight_names_what_to_fix(self) -> None:
        with self.assertRaisesRegex(LaunchError, "Developer Mode disabled"):
            self.choose([self.device(developer_mode="disabled")])
        with self.assertRaisesRegex(LaunchError, "not paired"):
            self.choose([self.device(paired=False)])
        with self.assertRaisesRegex(LaunchError, "no iOS device is connected"):
            self.choose([self.device(connected=False)])


class InstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.failure = (
            "An error was encountered\nMismatchedApplicationIdentifierEntitlement"
        )
        patcher = mock.patch.object(launch_ios, "xcrun", self.xcrun)
        patcher.start()
        self.addCleanup(patcher.stop)

    def xcrun(self, *args: str, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        if "install" in args[:4] and self.failure:
            failure, self.failure = self.failure, ""
            return subprocess.CompletedProcess(args, 1, failure)
        return subprocess.CompletedProcess(args, 0, "")

    def test_a_failing_install_over_a_simulator_copy_uninstalls_it(self) -> None:
        launch_ios.install_on_simulator(
            _sim("A", "iPhone 17"), _BUNDLE, "copy.app", _options()
        )
        self.assertIn(("simctl", "uninstall", "A", "org.example.game"), self.calls)

    def test_on_conflict_fail_keeps_the_installed_copy(self) -> None:
        with self.assertRaisesRegex(LaunchError, "--on-conflict=uninstall"):
            launch_ios.install_on_simulator(
                _sim("A", "iPhone 17"),
                _BUNDLE,
                "copy.app",
                _options("--on-conflict=fail"),
            )
        self.assertNotIn(("simctl", "uninstall", "A", "org.example.game"), self.calls)

    def test_other_failures_keep_the_installed_copy(self) -> None:
        self.failure = "An error was encountered\nThe bundle is invalid"
        with self.assertRaisesRegex(LaunchError, "bundle is invalid"):
            launch_ios.install_on_simulator(
                _sim("A", "iPhone 17"), _BUNDLE, "copy.app", _options()
            )
        self.assertFalse([call for call in self.calls if "uninstall" in call])

    def test_storage_and_signing_failures_are_conflicts(self) -> None:
        for output in ["Insufficient storage", "not enough space", "Out of space"]:
            self.assertEqual(
                launch_ios._conflict(output), "the device has too little free storage"
            )
        self.assertEqual(
            launch_ios._conflict("Upgrade failed"),
            "it is signed by another team or with other entitlements",
        )
        self.assertIsNone(launch_ios._conflict("The bundle is invalid"))

    def test_a_locked_device_is_not_uninstalled_from(self) -> None:
        self.failure = "The device is locked."
        device = launch_ios.Device("ID", "Phone", "UDID", True, "enabled", True)
        with self.assertRaisesRegex(LaunchError, "unlock the device"):
            launch_ios.install_on_device(device, _BUNDLE, "copy.app", _options())
        self.assertFalse([call for call in self.calls if "uninstall" in call])


class ListingTest(unittest.TestCase):
    def test_simulators_are_listed_booted_first(self) -> None:
        simulators = _simulators(
            _sim("A", "iPhone 17"), _sim("B", "iPhone 17", "Booted", (26, 4))
        )
        with (
            mock.patch.object(launch_ios.Simulators, "load", return_value=simulators),
            mock.patch("sys.stdout", new_callable=io.StringIO) as output,
        ):
            launch_ios.list_devices(simulator=True)
        self.assertEqual(
            output.getvalue(),
            "Simulators:\n"
            "  B  Booted    iPhone 17, iOS 26.4\n"
            "  A  Shutdown  iPhone 17, iOS 27.0\n",
        )

    def test_devices_are_listed_with_their_state(self) -> None:
        found = [
            launch_ios.Device("ID", "Phone", "UDID", True, "enabled", True),
            launch_ios.Device("ID2", "Pad", "", True, "disabled", False),
        ]
        with (
            mock.patch.object(launch_ios, "devices", return_value=found),
            mock.patch("sys.stdout", new_callable=io.StringIO) as output,
        ):
            launch_ios.list_devices(simulator=False)
        self.assertEqual(
            output.getvalue(),
            "Devices:\n"
            "  UDID  connected  Phone, Developer Mode enabled\n"
            "  ID2  not connected  Pad, Developer Mode disabled\n",
        )


class EnvironmentTest(unittest.TestCase):
    def test_ios_takes_its_options(self) -> None:
        _options("--simulator-type=iPhone 17 Pro", "--os=26.4", "--env", "A=1")
        with self.assertRaisesRegex(LaunchError, "--logcat does not apply to ios"):
            _options("--logcat=all")

    def test_the_application_environment_takes_the_tool_prefix(self) -> None:
        env = launch_ios._child_environment("SIMCTL_CHILD_", _options("--env", "LEVEL=3"))
        self.assertEqual(env["SIMCTL_CHILD_LEVEL"], "3")
        self.assertEqual(env["SIMCTL_CHILD_OS_ACTIVITY_DT_MODE"], "enable")


if __name__ == "__main__":
    unittest.main()
