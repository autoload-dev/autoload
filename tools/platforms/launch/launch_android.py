"""
Install an APK or App Bundle on an Android device or emulator, launch it, stream its log.

The launcher uses the host's Android SDK tools, from ANDROID_SDK_ROOT, ANDROID_HOME or
PATH, because an adb client must match the adb server already serving the host's
devices.
"""

from __future__ import annotations

import base64
import dataclasses
import glob
import os
import platform
import re
import shlex
import shutil
import subprocess
import tempfile
import time
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
        "emulator_args",
        "grant_permissions",
        "logcat",
    }
)

BOOT_TIMEOUT = 300
INSTALL_TIMEOUT = 600

# The AVD the launcher creates when none suits the application.
DEFAULT_AVD = "medium_phone"

# The file of godot/platforms/private/android/LaunchArgumentsPlugin.java, below the
# application's files directory.
LAUNCH_ARGUMENTS_FILE = "rules_godot_launch_arguments"

# Install failures an installed copy of the application causes; uninstalling it, and
# its data, lets the install succeed.
_CONFLICTS = {
    "INSTALL_FAILED_UPDATE_INCOMPATIBLE": "it is signed with another key",
    "INSTALL_PARSE_FAILED_INCONSISTENT_CERTIFICATES": "it is signed with another key",
    "INSTALL_FAILED_VERSION_DOWNGRADE": "it has a newer version code",
    "INSTALL_FAILED_INSUFFICIENT_STORAGE": "the device has too little free storage",
}

_HINTS = {
    "INSTALL_FAILED_NO_MATCHING_ABIS": "the APK has no native libraries for the device's CPU {abi}; build for it with --platforms=@rules_godot//godot/platforms:android_<cpu>",
    "INSTALL_FAILED_OLDER_SDK": "the device's API level {sdk} is below the application's android_min_sdk_version",
    "INSTALL_FAILED_INSUFFICIENT_STORAGE": "free storage on the device",
    "INSTALL_FAILED_USER_RESTRICTED": "allow installs over USB in the device's developer options",
}

_FAILURE = re.compile(r"\b(INSTALL_[A-Z_]+|DELETE_FAILED_[A-Z_]+)")

# System image tags in the order the launcher prefers them for an AVD it creates.
_IMAGE_TAGS = ("google_apis_playstore", "google_apis", "default")


@dataclasses.dataclass(frozen=True)
class Device:
    """A device adb lists."""

    serial: str
    state: str
    description: str = ""

    @property
    def emulator(self) -> bool:
        return self.serial.startswith("emulator-")


def sdk_root() -> str | None:
    """The host's Android SDK, found as the repository's Android setup finds it."""
    for name in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        if os.environ.get(name):
            return os.environ[name]
    home = os.path.expanduser("~")
    default = os.path.join(
        home, "Library/Android/sdk" if platform.system() == "Darwin" else "Android/Sdk"
    )
    return default if os.path.isdir(default) else None


def host_tool(name: str, subdirectory: str) -> str:
    """
    Find an SDK tool of the host: in the SDK, else on PATH.

    Raises:
        LaunchError: Neither has it.
    """
    root = sdk_root()
    if root:
        candidate = os.path.join(root, subdirectory, name)
        if os.access(candidate, os.X_OK):
            return candidate
    found = shutil.which(name)
    if found:
        return found
    raise LaunchError(
        f"no {name} in the Android SDK ({root or 'not found'}) or on PATH; set "
        "ANDROID_HOME to the SDK, with its platform-tools, emulator and cmdline-tools"
    )


class Adb:
    """The host's adb, optionally for one device."""

    def __init__(self, path: str, serial: str | None = None) -> None:
        self.path = path
        self.serial = serial

    def device(self, serial: str) -> Adb:
        return Adb(self.path, serial)

    def command(self, *args: str) -> list[str]:
        return [self.path, *(["-s", self.serial] if self.serial else []), *args]

    def run(
        self, *args: str, check: bool = True, timeout: float | None = 60
    ) -> subprocess.CompletedProcess[str]:
        return launch_common.run(self.command(*args), check=check, timeout=timeout)

    def shell(self, *words: str, check: bool = True) -> str:
        """Run a command in the device's shell, which receives it as one string."""
        command = " ".join(shlex.quote(word) for word in words)
        return self.run("shell", command, check=check).stdout.strip()


def devices(adb: Adb) -> list[Device]:
    """The devices adb lists."""
    found = []
    for line in adb.run("devices", "-l").stdout.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 2 or line.startswith("*"):
            continue
        details = dict(field.split(":", 1) for field in fields[2:] if ":" in field)
        found.append(Device(fields[0], fields[1], details.get("model", "")))
    return found


def avd_name(adb: Adb, serial: str) -> str | None:
    """The AVD a running emulator runs; its console answers before adbd does."""
    result = adb.device(serial).run("emu", "avd", "name", check=False, timeout=10)
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if result.returncode != 0 or not lines or lines[0] == "OK":
        return None
    return lines[0]


def avds(emulator: str) -> list[str]:
    """The AVDs the host's emulator can start."""
    result = launch_common.run([emulator, "-list-avds"], check=False, timeout=30)
    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip() and "|" not in line and " " not in line.strip()
    ]


def _avd_abi(name: str) -> str | None:
    """The ABI of an AVD's system image, from its config.ini, or None if unreadable."""
    home = os.environ.get("ANDROID_AVD_HOME") or os.path.join(
        os.path.expanduser("~"), ".android", "avd"
    )
    config = os.path.join(home, name + ".avd", "config.ini")
    try:
        with open(config, encoding="utf-8", errors="replace") as lines:
            for line in lines:
                key, _, value = line.partition("=")
                if key.strip() == "abi.type":
                    return value.strip()
    except OSError:
        return None
    return None


def host_abi() -> str:
    """The ABI an emulator runs natively on this host."""
    return "arm64-v8a" if platform.machine() in ("arm64", "aarch64") else "x86_64"


def target_abi(apk: str) -> str:
    """
    The host's ABI, which the APK must carry for an emulator on this host.

    Raises:
        LaunchError: The APK has native libraries for other ABIs only.
    """
    with zipfile.ZipFile(apk) as archive:
        abis = {
            name.split("/")[1]
            for name in archive.namelist()
            if name.startswith("lib/") and name.count("/") >= 2
        }
    abi = host_abi()
    if abis and abi not in abis:
        raise LaunchError(
            f"an emulator on this host runs {abi}, and the APK has libraries for "
            f"{', '.join(sorted(abis))} only; build for it with "
            f"--platforms=@rules_godot//godot/platforms:android_{'arm64' if abi.startswith('arm64') else 'x86_64'}"
        )
    return abi


def list_devices(adb: Adb, emulator: str | None) -> None:
    print("Running:")
    for device in devices(adb):
        kind = (
            f"emulator {avd_name(adb, device.serial)}"
            if device.emulator
            else device.description
        )
        print(f"  {device.serial}  {device.state}  {kind}".rstrip())
    if emulator:
        print("Startable AVDs:")
        for avd in avds(emulator):
            print("  " + avd)


def select_device(options: launch_common.Options, adb: Adb, apk: str | None) -> str:
    """
    Choose the device: the one named, the only one running, or an emulator to start.

    Raises:
        LaunchError: The choice is ambiguous or nothing matches.
    """
    wanted = options.device or os.environ.get("ANDROID_SERIAL")
    running = devices(adb)
    if wanted:
        # Serials first: an emulator's AVD name costs a console round trip.
        named = next((d for d in running if d.serial == wanted), None) or next(
            (d for d in running if d.emulator and avd_name(adb, d.serial) == wanted), None
        )
        if named:
            return _ready(adb, named)
        emulator = host_tool("emulator", "emulator")
        startable = avds(emulator)
        if options.start_device and wanted in startable:
            return start_emulator(adb, emulator, wanted, options)
        raise LaunchError(
            f"no device or AVD {wanted}; running: "
            f"{', '.join(d.serial for d in running) or 'none'}; AVDs: {', '.join(startable) or 'none'}"
        )
    device = launch_common.single(
        running,
        "devices",
        lambda d: f"{d.serial} ({d.description or d.state})",
        "ANDROID_SERIAL",
    )
    if device:
        return _ready(adb, device)
    if not options.start_device:
        raise LaunchError("no device runs; connect one or start an emulator")
    emulator = host_tool("emulator", "emulator")
    return start_emulator(adb, emulator, choose_avd(emulator, apk), options)


def _ready(adb: Adb, device: Device) -> str:
    """The device's serial once it can install; a booting emulator is waited for."""
    if device.emulator and device.state in ("device", "offline"):
        if device.state == "offline":
            log(f"waiting for {device.serial} to boot")
        _wait_for_boot(adb.device(device.serial), time.monotonic() + BOOT_TIMEOUT)
        return device.serial
    if device.state == "device":
        return device.serial
    if device.state == "unauthorized":
        raise LaunchError(
            f"{device.serial} has not authorized this host; accept the USB debugging prompt on the device"
        )
    raise LaunchError(f"{device.serial} is {device.state}")


def choose_avd(emulator: str, apk: str | None) -> str:
    """
    The AVD to start: medium_phone or the only AVD whose ABI suits the APK, else a new one.

    Raises:
        LaunchError: Several AVDs suit, or none does and none can be created.
    """
    abi = target_abi(apk) if apk else None
    names = avds(emulator)
    suitable = [name for name in names if abi is None or _avd_abi(name) in (None, abi)]
    if DEFAULT_AVD in suitable:
        return DEFAULT_AVD
    if len(suitable) == 1:
        return suitable[0]
    if suitable:
        raise LaunchError(
            f"no device runs and several AVDs exist: {', '.join(suitable)}; choose one with --device=<AVD>"
        )
    if DEFAULT_AVD in names:
        raise LaunchError(
            f"AVD {DEFAULT_AVD} runs {_avd_abi(DEFAULT_AVD)}, and the APK needs {abi}; choose an AVD with --device=<AVD>"
        )
    return create_avd(abi or host_abi(), apk)


def _images(abi: str) -> list[tuple[tuple[int, ...], str, str]]:
    """The installed system images of an ABI: version, API directory and tag."""
    root = sdk_root() or ""
    images = []
    for path in glob.glob(os.path.join(root, "system-images", "android-*", "*", abi)):
        api_directory, tag = path.split(os.sep)[-3:-1]
        version = tuple(
            int(part)
            for part in re.findall(r"\d+", api_directory.removeprefix("android-"))
        )
        if version and tag in _IMAGE_TAGS:
            images.append((version, api_directory, tag))
    return images


def _aapt2() -> str | None:
    """The newest aapt2 of the host SDK's build tools."""
    tools = glob.glob(os.path.join(sdk_root() or "", "build-tools", "*", "aapt2"))
    return max(tools, key=_version_of_path) if tools else None


def _version_of_path(path: str) -> tuple[int, ...]:
    return tuple(
        int(part) for part in re.findall(r"\d+", os.path.basename(os.path.dirname(path)))
    )


def _sdk_versions(apk: str | None) -> tuple[int | None, int | None]:
    """The APK's minimum and target API levels, as aapt2 reads them."""
    aapt2 = _aapt2()
    if not apk or not aapt2:
        return None, None
    badging = launch_common.run(
        [aapt2, "dump", "badging", apk], check=False, timeout=60
    ).stdout
    minimum = re.search(r"sdkVersion:'(\d+)'", badging)
    target = re.search(r"targetSdkVersion:'(\d+)'", badging)
    return (
        int(minimum.group(1)) if minimum else None,
        int(target.group(1)) if target else None,
    )


def create_avd(abi: str, apk: str | None) -> str:
    """
    Create medium_phone from the installed system image that suits the APK best.

    It downloads nothing and accepts no license: without an image it names the
    sdkmanager command that installs one.

    Raises:
        LaunchError: No suitable system image is installed.
    """
    minimum, target = _sdk_versions(apk)
    images = [
        image for image in _images(abi) if minimum is None or image[0] >= (minimum,)
    ]
    if not images:
        root = sdk_root()
        sdkmanager = (
            os.path.join(root, "cmdline-tools", "latest", "bin", "sdkmanager")
            if root
            else "sdkmanager"
        )
        api = target or 36
        raise LaunchError(
            f"no device runs, no AVD suits the application, and the Android SDK has no {abi} system "
            f"image{f' for API {minimum} or newer' if minimum else ''} to create one from; install one with:\n"
            f'  {sdkmanager} "system-images;android-{api};google_apis_playstore;{abi}"'
        )
    _, api_directory, tag = max(
        # The target API itself, then its minor releases, then the newest.
        images,
        key=lambda image: (
            image[0] == (target,),
            image[0][:1] == (target,),
            image[0],
            -_IMAGE_TAGS.index(image[2]),
        ),
    )
    package = f"system-images;{api_directory};{tag};{abi}"
    avdmanager = host_tool("avdmanager", os.path.join("cmdline-tools", "latest", "bin"))
    log(f"creating AVD {DEFAULT_AVD} from {package}")
    launch_common.run(
        [
            avdmanager,
            "create",
            "avd",
            "--name",
            DEFAULT_AVD,
            "--package",
            package,
            "--device",
            DEFAULT_AVD,
        ],
        stdin="no\n",
        timeout=120,
    )
    return DEFAULT_AVD


def start_emulator(
    adb: Adb, emulator: str, avd: str, options: launch_common.Options
) -> str:
    """Start an AVD, wait until Android has booted, and leave it running."""
    log_path = os.path.join(tempfile.gettempdir(), f"rules_godot_emulator_{avd}.log")
    command = [
        emulator,
        "-avd",
        avd,
        *(["-no-window"] if options.headless else []),
        *options.emulator_args,
    ]
    log(f"starting emulator {avd}; its output goes to {log_path}")
    before = {device.serial for device in devices(adb)}
    with open(log_path, "w", encoding="utf-8") as output:
        # Its own session, so the emulator outlives this run and Ctrl-C.
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    deadline = time.monotonic() + BOOT_TIMEOUT
    serial = None
    while serial is None:
        _check_emulator(process, avd, log_path, deadline)
        time.sleep(1)
        serial = next(
            (d.serial for d in devices(adb) if d.emulator and d.serial not in before),
            None,
        )
    _wait_for_boot(
        adb.device(serial),
        deadline,
        lambda: _check_emulator(process, avd, log_path, deadline),
    )
    log(f"emulator {avd} runs as {serial}")
    return serial


def _wait_for_boot(
    device: Adb, deadline: float, check: Callable[[], None] | None = None
) -> None:
    """Wait until Android has booted on the device, then dismiss its keyguard."""
    while device.shell("getprop", "sys.boot_completed", check=False) != "1":
        if check:
            check()
        if time.monotonic() > deadline:
            raise LaunchError(
                f"{device.serial} did not boot within {BOOT_TIMEOUT} seconds"
            )
        time.sleep(1)
    device.shell("wm", "dismiss-keyguard", check=False)


def _check_emulator(
    process: subprocess.Popen, avd: str, log_path: str, deadline: float
) -> None:
    if process.poll() is not None:
        with open(log_path, encoding="utf-8", errors="replace") as output:
            tail = "".join(output.readlines()[-15:])
        raise LaunchError(
            f"the emulator of {avd} exited with code {process.returncode}:\n{tail}"
        )
    if time.monotonic() > deadline:
        raise LaunchError(
            f"the emulator of {avd} did not boot within {BOOT_TIMEOUT} seconds; see {log_path}"
        )


def install(device: Adb, apk: str, package: str, options: launch_common.Options) -> None:
    """
    Install the APK, resolving the conflicts an installed copy causes as --on-conflict says.

    Raises:
        LaunchError: The install failed.
    """
    # -d lets a debuggable application downgrade and keep its data.
    flags = ["-r", "-t", "-d", *(["-g"] if options.grant_permissions else [])]

    def install_once() -> str | None:
        # adb can exit 0 when an install fails.
        result = device.run("install", *flags, apk, check=False, timeout=INSTALL_TIMEOUT)
        if result.returncode == 0 and "Success" in result.stdout:
            return None
        match = _FAILURE.search(result.stdout)
        return (
            match.group(1)
            if match
            else (result.stdout.strip() or f"exit code {result.returncode}")
        )

    def describe(failure: str) -> str:
        hint = _HINTS.get(failure)
        if not hint:
            return failure
        return f"{failure}; " + hint.format(
            abi=device.shell("getprop", "ro.product.cpu.abi", check=False),
            sdk=device.shell("getprop", "ro.build.version.sdk", check=False),
        )

    launch_common.install_resolving_conflicts(
        package,
        device.serial or "",
        options,
        install=install_once,
        uninstall=lambda: device.run("uninstall", package, check=False),
        installed=lambda: "package:" in device.shell("pm", "path", package, check=False),
        conflict=_CONFLICTS.get,
        describe=describe,
    )


def write_launch_arguments(device: Adb, package: str, godot_args: Sequence[str]) -> None:
    """
    Hand Godot arguments to the launch arguments plugin of a debuggable application.

    run-as writes them into the application's private files, which no other
    application can write, unlike an intent extra; no arguments remove stale ones.
    """
    path = "files/" + LAUNCH_ARGUMENTS_FILE
    if godot_args:
        data = base64.b64encode("\0".join(godot_args).encode("utf-8")).decode("ascii")
        script = f"mkdir -p files && echo {data} | base64 -d > {path}"
    else:
        script = f"rm -f {path}"
    output = device.shell("run-as", package, "sh", "-c", script, check=False)
    if godot_args and output:
        raise LaunchError(f"passing Godot arguments to {package} failed: {output}")


def start(
    device: Adb, package: str, launch_arguments: bool, godot_args: Sequence[str]
) -> str:
    """Start the application's launcher activity anew; return its process ID."""
    device.shell("am", "force-stop", package)
    if launch_arguments:
        write_launch_arguments(device, package, godot_args)
    resolved = device.shell(
        "cmd",
        "package",
        "resolve-activity",
        "--brief",
        "-a",
        "android.intent.action.MAIN",
        "-c",
        "android.intent.category.LAUNCHER",
        package,
    ).splitlines()
    component = resolved[-1].strip() if resolved else ""
    if "/" not in component:
        raise LaunchError(
            f"{package} has no launcher activity on {device.serial}: {' '.join(resolved)}"
        )
    output = device.shell("am", "start", "-W", "-n", component)
    if "Error" in output or "Exception" in output:
        raise LaunchError(f"starting {component} failed:\n{output}")
    for _ in range(20):
        pid = device.shell("pidof", package, check=False).split(" ")[0]
        if pid:
            return pid
        time.sleep(0.5)
    raise LaunchError(
        f"{package} started but no process of it runs; it may have crashed at start"
    )


def stream(device: Adb, package: str, pid: str, options: launch_common.Options) -> int:
    """Print the application's log until its process ends; Ctrl-C stops it."""
    command = device.command("logcat", "-v", "brief")
    if options.logcat == "all":
        command += ["-T", "1"]
    else:
        command += [f"--pid={pid}", *(options.logcat.split() if options.logcat else [])]
    logcat = subprocess.Popen(command, stdin=subprocess.DEVNULL)
    # One device shell that returns when the process ends, instead of polling with adb.
    watcher = subprocess.Popen(
        device.command("shell", f"while [ -d /proc/{pid} ]; do sleep 1; done"),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
    )
    try:
        while watcher.poll() is None and logcat.poll() is None:
            time.sleep(0.2)
        if watcher.returncode != 0:
            raise LaunchError(f"the connection to {device.serial} ended")
        # The log's last lines arrive after the process ended.
        time.sleep(0.5)
        log(f"{package} ended")
        return 0
    except KeyboardInterrupt:
        device.shell("am", "force-stop", package, check=False)
        return launch_common.INTERRUPTED
    finally:
        launch_common.end(logcat)
        launch_common.end(watcher)


def universal_apk(
    manifest: Mapping[str, Any], runfile: Callable[[str], str], directory: str
) -> str:
    """The one APK bundletool derives from the bundle for every device, signed for debugging."""
    java_home = os.environ.get("JAVA_HOME")
    java = os.path.join(java_home, "bin", "java") if java_home else shutil.which("java")
    if not java or not os.access(java, os.X_OK):
        raise LaunchError(
            "installing an App Bundle runs bundletool, which needs java; set JAVA_HOME or put java on PATH"
        )
    # rules_android's bundletool carries no aapt2 of its own.
    aapt2 = _aapt2()
    if not aapt2:
        raise LaunchError(
            "installing an App Bundle runs bundletool, which needs aapt2 of the Android SDK's build-tools"
        )
    apks = os.path.join(directory, "app.apks")
    log("building the universal APK of the App Bundle")
    launch_common.run(
        [
            java,
            "-jar",
            runfile(manifest["bundletool"]),
            "build-apks",
            "--bundle=" + runfile(manifest["bundle"]),
            "--output=" + apks,
            "--mode=universal",
            "--ks=" + runfile(manifest["keystore"]),
            "--ks-pass=pass:android",
            "--ks-key-alias=androiddebugkey",
            "--key-pass=pass:android",
            "--aapt2=" + aapt2,
        ],
        timeout=INSTALL_TIMEOUT,
    )
    with zipfile.ZipFile(apks) as archive:
        return archive.extract("universal.apk", directory)


def launch(
    manifest: Mapping[str, Any],
    options: launch_common.Options,
    runfile: Callable[[str], str],
) -> int:
    package = manifest["application_id"]
    if options.godot_args and not manifest["launch_arguments"]:
        raise LaunchError(
            "Godot arguments reach debuggable Android applications only, which every build but -c opt makes"
        )
    adb = Adb(host_tool("adb", "platform-tools"))
    if options.list_devices:
        try:
            emulator = host_tool("emulator", "emulator")
        except LaunchError:
            emulator = None
        list_devices(adb, emulator)
        return 0
    with tempfile.TemporaryDirectory(prefix="rules_godot_android_") as directory:
        apk = None
        if not options.no_install:
            apk = (
                runfile(manifest["apk"])
                if "apk" in manifest
                else universal_apk(manifest, runfile, directory)
            )
        device = adb.device(select_device(options, adb, apk))
        if apk:
            log(f"installing {package} on {device.serial}")
            install(device, apk, package, options)
    if options.install_only:
        return 0
    pid = start(device, package, manifest["launch_arguments"], options.godot_args)
    log(f"started {package} on {device.serial}, process {pid}")
    if options.detach:
        return 0
    return stream(device, package, pid, options)
