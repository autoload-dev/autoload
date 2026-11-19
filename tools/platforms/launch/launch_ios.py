"""
Install an iOS application on a Simulator or a device, launch it, stream its output.

rules_apple builds the bundle; this launcher installs it with simctl or devicectl.
rules_apple's own runner copies the bundle with the host's rsync, whose openrsync on
macOS ignores --chmod=u+w, so its copy stays read-only and `simctl install` fails with
NSPOSIXErrorDomain 13. This launcher makes its copy writable itself.
"""

from __future__ import annotations

import dataclasses
import fnmatch
import json
import os
import plistlib
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import launch_common
from launch_common import LaunchError, log

OPTIONS = frozenset(
    {
        "device",
        "list_devices",
        "start_device",
        "headless",
        "fresh",
        "on_conflict",
        "install_only",
        "no_install",
        "detach",
        "env",
        "simulator_type",
        "os_version",
    }
)

BOOT_TIMEOUT = 300
INSTALL_TIMEOUT = 600


@dataclasses.dataclass(frozen=True)
class Bundle:
    """The application's Info.plist keys the launcher needs, and where the build put it."""

    source: str
    bundle_id: str
    simulator: bool
    minimum_os: tuple[int, ...]
    family: str


def read_bundle(source: str) -> Bundle:
    """Read the Info.plist of an .app directory or of the application an .ipa holds."""
    source = os.path.realpath(source)
    if os.path.isdir(source):
        with open(os.path.join(source, "Info.plist"), "rb") as plist:
            info = plistlib.load(plist)
    else:
        with zipfile.ZipFile(source) as archive:
            names = fnmatch.filter(archive.namelist(), "Payload/*.app/Info.plist")
            if len(names) != 1:
                raise LaunchError(
                    f"{os.path.basename(source)} holds no single Payload/*.app"
                )
            info = plistlib.loads(archive.read(names[0]))
    return Bundle(
        source=source,
        bundle_id=info["CFBundleIdentifier"],
        simulator="iPhoneSimulator" in info.get("CFBundleSupportedPlatforms", []),
        minimum_os=version(info.get("MinimumOSVersion", "0")),
        family="iPhone" if 1 in info.get("UIDeviceFamily", [1]) else "iPad",
    )


def writable_copy(bundle: Bundle, directory: str) -> str:
    """
    Copy the application into a writable directory, unpacking an .ipa archive.

    simctl and devicectl fail on the read-only files of Bazel's output tree.
    """
    if not os.path.isdir(bundle.source):
        # Extracted files take default modes, which are writable.
        with zipfile.ZipFile(bundle.source) as archive:
            archive.extractall(directory)
            plist = fnmatch.filter(archive.namelist(), "Payload/*.app/Info.plist")[0]
        return os.path.join(directory, os.path.dirname(plist))
    path = os.path.join(directory, os.path.basename(bundle.source))
    # An APFS clone where the file system allows it.
    if launch_common.run(["cp", "-cR", bundle.source, path], check=False).returncode != 0:
        shutil.rmtree(path, ignore_errors=True)
        shutil.copytree(bundle.source, path, symlinks=True)
    launch_common.run(["chmod", "-R", "u+w", path])
    return path


def version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", text))


def xcrun(
    *args: str, check: bool = True, timeout: float | None = 120
) -> subprocess.CompletedProcess[str]:
    return launch_common.run(["xcrun", *args], check=check, timeout=timeout)


def _text(numbers: Sequence[int]) -> str:
    return ".".join(str(number) for number in numbers)


# Simulators.


@dataclasses.dataclass(frozen=True)
class Simulator:
    """A Simulator device of an iOS runtime."""

    udid: str
    name: str
    state: str
    runtime: tuple[int, ...]
    device_type: str

    @property
    def booted(self) -> bool:
        return self.state == "Booted"


@dataclasses.dataclass(frozen=True)
class Simulators:
    """The iOS Simulators, runtimes and device types simctl knows."""

    devices: list[Simulator]
    runtimes: list[dict]
    # Device types by identifier, with their position in simctl's list.
    types: dict[str, tuple[int, dict]]

    @classmethod
    def load(cls) -> Simulators:
        data = json.loads(xcrun("simctl", "list", "-j").stdout)
        runtimes = [
            r
            for r in data["runtimes"]
            if r.get("platform") == "iOS" and r.get("isAvailable")
        ]
        versions = {r["identifier"]: version(r["version"]) for r in runtimes}
        devices = [
            Simulator(
                d["udid"],
                d["name"],
                d["state"],
                versions[runtime],
                d["deviceTypeIdentifier"],
            )
            for runtime, entries in data["devices"].items()
            if runtime in versions
            for d in entries
            if d.get("isAvailable")
        ]
        types = {
            t["identifier"]: (index, t) for index, t in enumerate(data["devicetypes"])
        }
        return cls(devices, runtimes, types)

    def type(self, identifier: str) -> dict:
        return self.types.get(identifier, (-1, {}))[1]

    def newness(self, identifier: str) -> tuple[int, int]:
        index, entry = self.types.get(identifier, (-1, {}))
        return entry.get("minRuntimeVersion", 0), index


def _suits(
    runtime: tuple[int, ...],
    device_type: dict,
    bundle: Bundle,
    options: launch_common.Options,
) -> bool:
    """Whether a runtime and device type suit the application and the --os and --simulator-type options."""
    wanted_os = version(options.os_version or "")
    return (
        runtime >= bundle.minimum_os
        and runtime[: len(wanted_os)] == wanted_os
        and device_type.get("productFamily") == bundle.family
        and (
            not options.simulator_type
            or device_type.get("name") == options.simulator_type
        )
    )


def select_simulator(
    options: launch_common.Options, bundle: Bundle, simulators: Simulators
) -> Simulator:
    """
    Choose the Simulator: the one named, the only one booted, or one to boot or create.

    Raises:
        LaunchError: The choice is ambiguous or nothing matches.
    """
    wanted = options.device or os.environ.get("BAZEL_APPLE_DEVICE_UDID")
    if wanted:
        wanted_os = version(options.os_version or "")
        named = [
            s
            for s in simulators.devices
            if wanted in (s.udid, s.name)
            and s.runtime >= bundle.minimum_os
            and s.runtime[: len(wanted_os)] == wanted_os
        ]
        if not named:
            raise LaunchError(
                f"no Simulator {wanted} with iOS {_text(bundle.minimum_os)} or newer; --list-devices lists them"
            )
        return max(named, key=lambda s: (s.booted, s.runtime))
    booted = launch_common.single(
        [
            s
            for s in simulators.devices
            if s.booted
            and s.runtime >= bundle.minimum_os
            and (
                not (options.os_version or options.simulator_type)
                or _suits(s.runtime, simulators.type(s.device_type), bundle, options)
            )
        ],
        "Simulators",
        lambda s: f"{s.name} ({s.udid})",
        "BAZEL_APPLE_DEVICE_UDID",
    )
    if booted:
        return booted
    if not options.start_device:
        raise LaunchError("no Simulator runs")
    suitable = [
        s
        for s in simulators.devices
        if _suits(s.runtime, simulators.type(s.device_type), bundle, options)
    ]
    if suitable:
        # The newest runtime, then Simulators named after their device type over those
        # someone named for a purpose, then the newest device type.
        return max(
            suitable,
            key=lambda s: (
                s.runtime,
                s.name == simulators.type(s.device_type).get("name"),
                simulators.newness(s.device_type),
            ),
        )
    return create_simulator(options, bundle, simulators)


def create_simulator(
    options: launch_common.Options, bundle: Bundle, simulators: Simulators
) -> Simulator:
    """Create a Simulator of the newest suitable runtime and device type."""
    pairs = [
        (version(runtime["version"]), runtime, simulators.type(supported["identifier"]))
        for runtime in simulators.runtimes
        for supported in runtime.get("supportedDeviceTypes", [])
        if _suits(
            version(runtime["version"]),
            simulators.type(supported["identifier"]),
            bundle,
            options,
        )
    ]
    if not pairs:
        raise LaunchError(
            f"no iOS Simulator runtime and device type suit iOS {_text(bundle.minimum_os)} or newer "
            f"{options.simulator_type or bundle.family} {options.os_version or ''}; install a runtime in "
            "Xcode's Components settings"
        )
    _, runtime, device_type = max(
        pairs, key=lambda pair: (pair[0], simulators.newness(pair[2]["identifier"]))
    )
    log(f"creating Simulator {device_type['name']} with iOS {runtime['version']}")
    udid = xcrun(
        "simctl",
        "create",
        device_type["name"],
        device_type["identifier"],
        runtime["identifier"],
    ).stdout.strip()
    return Simulator(
        udid,
        device_type["name"],
        "Shutdown",
        version(runtime["version"]),
        device_type["identifier"],
    )


def boot(simulator: Simulator, options: launch_common.Options) -> None:
    """Boot the Simulator unless it runs, show it unless --headless, and leave it running."""
    if not simulator.booted:
        log(f"booting Simulator {simulator.name} ({simulator.udid})")
        xcrun("simctl", "bootstatus", simulator.udid, "-b", timeout=BOOT_TIMEOUT)
    if not options.headless:
        _show(simulator)


def _show(simulator: Simulator) -> None:
    root = launch_common.run(["xcode-select", "-p"], check=False).stdout.strip()
    simulator_app = os.path.join(root, "Applications", "Simulator.app")
    # Xcode 27 replaces Simulator.app with DeviceHub, which shows the booted Simulators.
    device_hub = os.path.join(os.path.dirname(root), "Applications", "DeviceHub.app")
    if os.path.isdir(simulator_app):
        command = [
            "open",
            "-a",
            simulator_app,
            "--args",
            "-CurrentDeviceUDID",
            simulator.udid,
        ]
    elif os.path.isdir(device_hub):
        command = ["open", "-a", device_hub]
    else:
        return
    launch_common.run(command, check=False)


def install_on_simulator(
    simulator: Simulator, bundle: Bundle, path: str, options: launch_common.Options
) -> None:
    udid = simulator.udid

    def install() -> str | None:
        result = xcrun(
            "simctl", "install", udid, path, check=False, timeout=INSTALL_TIMEOUT
        )
        return (
            result.stdout.strip() or "simctl install failed"
            if result.returncode
            else None
        )

    launch_common.install_resolving_conflicts(
        bundle.bundle_id,
        simulator.name,
        options,
        install=install,
        uninstall=lambda: xcrun(
            "simctl", "uninstall", udid, bundle.bundle_id, check=False
        ),
        installed=lambda: (
            xcrun(
                "simctl", "get_app_container", udid, bundle.bundle_id, check=False
            ).returncode
            == 0
        ),
        # A Simulator checks no signature or version; a failing install over an
        # installed copy is the copy's.
        conflict=_conflict,
    )


def _child_environment(prefix: str, options: launch_common.Options) -> dict[str, str]:
    """The launcher's environment with the application's, under simctl's or devicectl's prefix."""
    # Godot logs through os_log on iOS; this mode mirrors os_log to stderr, as Xcode does.
    application = {"OS_ACTIVITY_DT_MODE": "enable"} | dict(options.env)
    return dict(os.environ) | {
        prefix + name: value for name, value in application.items()
    }


def launch_on_simulator(
    simulator: Simulator, bundle: Bundle, options: launch_common.Options
) -> int:
    env = _child_environment("SIMCTL_CHILD_", options)
    command = ["xcrun", "simctl", "launch", "--terminate-running-process"]
    target = [simulator.udid, bundle.bundle_id, *options.godot_args]
    if options.detach:
        output = launch_common.run([*command, *target], env=env).stdout.strip()
        log(f"started {output}")
        return 0
    log(f"starting {bundle.bundle_id} on {simulator.name}")
    # --console-pty prints the application's output line by line until it exits.
    return launch_common.foreground(
        [*command, "--console-pty", *target],
        env=env,
        stop=lambda: xcrun(
            "simctl", "terminate", simulator.udid, bundle.bundle_id, check=False
        ),
    )


# Devices.


@dataclasses.dataclass(frozen=True)
class Device:
    """A physical device devicectl knows."""

    identifier: str
    name: str
    udid: str
    paired: bool
    developer_mode: str
    connected: bool


def _devicectl_json(*args: str, check: bool = True) -> dict | None:
    """Run devicectl and return its JSON result, or None when it failed unchecked."""
    with tempfile.TemporaryDirectory(prefix="rules_godot_devicectl_") as directory:
        path = os.path.join(directory, "result.json")
        result = xcrun("devicectl", *args, "--quiet", "--json-output", path, check=check)
        if result.returncode != 0:
            return None
        with open(path, encoding="utf-8") as output:
            return json.load(output).get("result", {})


def devices() -> list[Device]:
    found = []
    for entry in (_devicectl_json("list", "devices") or {}).get("devices", []):
        hardware = entry.get("hardwareProperties", {})
        if hardware.get("reality") != "physical" or hardware.get("platform") != "iOS":
            continue
        connection = entry.get("connectionProperties", {})
        properties = entry.get("deviceProperties", {})
        found.append(
            Device(
                identifier=entry["identifier"],
                name=properties.get("name", ""),
                udid=hardware.get("udid", ""),
                paired=connection.get("pairingState") == "paired",
                developer_mode=properties.get("developerModeStatus", "unknown"),
                connected=connection.get("tunnelState") != "unavailable",
            )
        )
    return found


def select_device(options: launch_common.Options, found: Sequence[Device]) -> Device:
    """
    Choose the device and check that it can run a development build.

    Raises:
        LaunchError: The choice is ambiguous, nothing matches, or the device is not ready.
    """
    wanted = options.device or os.environ.get("BAZEL_APPLE_DEVICE_UDID")
    if wanted:
        device = next(
            (d for d in found if wanted in (d.identifier, d.udid, d.name)), None
        )
        if not device:
            raise LaunchError(f"no iOS device {wanted}; --list-devices lists them")
        if not device.connected:
            raise LaunchError(f"{device.name} is not connected; connect and unlock it")
    else:
        device = launch_common.single(
            [d for d in found if d.connected],
            "iOS devices",
            lambda d: f"{d.name} ({d.udid})",
            "BAZEL_APPLE_DEVICE_UDID",
        )
        if not device:
            raise LaunchError(
                "no iOS device is connected; connect and unlock one, or build for the Simulator "
                "with --platforms=@rules_godot//godot/platforms:ios_sim_arm64"
            )
    if not device.paired:
        raise LaunchError(
            f"{device.name} is not paired with this Mac; connect it and trust this computer on the device"
        )
    if device.developer_mode != "enabled":
        raise LaunchError(
            f"{device.name} has Developer Mode {device.developer_mode}; enable it in "
            "Settings > Privacy & Security and restart the device"
        )
    return device


def _conflict(output: str) -> str | None:
    """Why an install failure is one an installed copy causes, or None."""
    lowered = output.lower()
    if (
        "insufficient" in lowered
        or "enough space" in lowered
        or "out of space" in lowered
    ):
        return "the device has too little free storage"
    if "mismatchedapplicationidentifierentitlement" in lowered or "upgrade" in lowered:
        return "it is signed by another team or with other entitlements"
    return None


def _device_hint(output: str) -> str:
    """What to fix for an install failure that uninstalling cannot resolve, or ''."""
    lowered = output.lower()
    if "locked" in lowered:
        return "unlock the device and keep it unlocked while installing"
    if "profile" in lowered or "applicationverificationfailed" in lowered:
        return "the provisioning profile must name this device and the bundle ID, and the device must trust its developer"
    return ""


def install_on_device(
    device: Device, bundle: Bundle, path: str, options: launch_common.Options
) -> None:
    def install() -> str | None:
        result = xcrun(
            "devicectl",
            "device",
            "install",
            "app",
            "--device",
            device.identifier,
            path,
            check=False,
            timeout=INSTALL_TIMEOUT,
        )
        return (
            result.stdout.strip() or "devicectl install failed"
            if result.returncode
            else None
        )

    def installed() -> bool:
        apps = _devicectl_json(
            "device",
            "info",
            "apps",
            "--device",
            device.identifier,
            "--bundle-id",
            bundle.bundle_id,
            check=False,
        )
        return bool(apps and apps.get("apps"))

    def describe(failure: str) -> str:
        hint = _device_hint(failure)
        return f"{hint}:\n{failure}" if hint else failure

    launch_common.install_resolving_conflicts(
        bundle.bundle_id,
        device.name,
        options,
        install=install,
        uninstall=lambda: xcrun(
            "devicectl",
            "device",
            "uninstall",
            "app",
            "--device",
            device.identifier,
            bundle.bundle_id,
            check=False,
        ),
        installed=installed,
        conflict=_conflict,
        describe=describe,
    )


def launch_on_device(
    device: Device, bundle: Bundle, options: launch_common.Options
) -> int:
    env = _child_environment("DEVICECTL_CHILD_", options)
    command = [
        "xcrun",
        "devicectl",
        "device",
        "process",
        "launch",
        "--device",
        device.identifier,
        "--terminate-existing",
    ]
    # devicectl stops reading its own options at --, so Godot's options reach the application.
    target = [bundle.bundle_id, "--", *options.godot_args]
    if options.detach:
        launch_common.run([*command, *target], env=env, timeout=120)
        log(f"started {bundle.bundle_id} on {device.name}")
        return 0
    log(f"starting {bundle.bundle_id} on {device.name}")
    return launch_common.foreground(
        [*command, "--console", *target],
        env=env,
        stop=lambda: _terminate_on_device(device, bundle),
    )


def _terminate_on_device(device: Device, bundle: Bundle) -> None:
    """End the application's processes on the device, found by its bundle's path."""
    result = _devicectl_json(
        "device", "info", "processes", "--device", device.identifier, check=False
    )
    marker = (
        "/"
        + os.path.basename(bundle.source.rstrip("/"))
        .removesuffix(".ipa")
        .removesuffix(".app")
        + ".app/"
    )
    for process in (result or {}).get("runningProcesses", []):
        if marker in process.get("executable", ""):
            xcrun(
                "devicectl",
                "device",
                "process",
                "terminate",
                "--device",
                device.identifier,
                "--pid",
                str(process["processIdentifier"]),
                check=False,
            )


# Entry point.


def list_devices(simulator: bool) -> None:
    if simulator:
        simulators = Simulators.load()
        print("Simulators:")
        for s in sorted(
            simulators.devices, key=lambda s: (not s.booted, s.name, s.runtime)
        ):
            print(f"  {s.udid}  {s.state:<8}  {s.name}, iOS {_text(s.runtime)}")
        return
    print("Devices:")
    for d in devices():
        state = "connected" if d.connected else "not connected"
        print(
            f"  {d.udid or d.identifier}  {state}  {d.name}, Developer Mode {d.developer_mode}"
        )


def launch(
    manifest: Mapping[str, Any],
    options: launch_common.Options,
    runfile: Callable[[str], str],
) -> int:
    bundle = read_bundle(runfile(manifest["bundle"]))
    if options.list_devices:
        list_devices(bundle.simulator)
        return 0
    if bundle.simulator:
        simulator = select_simulator(options, bundle, Simulators.load())
        boot(simulator, options)
        if not options.no_install:
            log(f"installing {bundle.bundle_id} on {simulator.name}")
            with tempfile.TemporaryDirectory(prefix="rules_godot_ios_") as directory:
                install_on_simulator(
                    simulator, bundle, writable_copy(bundle, directory), options
                )
        return (
            0 if options.install_only else launch_on_simulator(simulator, bundle, options)
        )
    device = select_device(options, devices())
    if not options.no_install:
        log(f"installing {bundle.bundle_id} on {device.name}")
        with tempfile.TemporaryDirectory(prefix="rules_godot_ios_") as directory:
            install_on_device(device, bundle, writable_copy(bundle, directory), options)
    return 0 if options.install_only else launch_on_device(device, bundle, options)
