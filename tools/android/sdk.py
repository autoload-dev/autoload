"""Reuse an Android SDK and install only missing pinned SDK packages."""

import argparse
import json
import os
import platform
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path

# The same requirements configure the Aspect CLI's environment (.aspect/config.axl) and the
# CI cache.
CONFIG = Path(__file__).absolute().parent / "sdk.json"
REQUIREMENTS = json.loads(CONFIG.read_text())
SDK_APIS = tuple(REQUIREMENTS["api_levels"])
BUILD_TOOLS = REQUIREMENTS["build_tools"]
NDK_VERSION = REQUIREMENTS["ndk"]
# The pinned sdkmanager (//:multitool.lock.json), which Bazel downloads only when run.
MANAGED_SDKMANAGER = ["bazel", "run", "@multitool//tools/sdkmanager:cwd", "--"]


def read_properties(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    return {
        key.strip(): value.strip()
        for line in path.read_text().splitlines()
        if "=" in line and not line.lstrip().startswith("#")
        for key, value in [line.split("=", 1)]
    }


def missing_packages(
    root: Path,
    api_levels: Iterable[str] = SDK_APIS,
    ndk_root: Path | None = None,
) -> list[str]:
    ndk_root = ndk_root or root / "ndk" / NDK_VERSION
    host = "darwin-x86_64" if platform.system() == "Darwin" else "linux-x86_64"
    requirements = {
        **{
            "platforms;android-" + api: ["platforms/android-" + api + "/android.jar"]
            for api in api_levels
        },
        "build-tools;" + BUILD_TOOLS: [
            "build-tools/" + BUILD_TOOLS + "/aapt",
            "build-tools/" + BUILD_TOOLS + "/aapt2",
            "build-tools/" + BUILD_TOOLS + "/zipalign",
            "build-tools/" + BUILD_TOOLS + "/lib/apksigner.jar",
        ],
    }
    missing = [
        package
        for package, files in requirements.items()
        if not all((root / file).is_file() for file in files)
    ]
    if not (ndk_root / "toolchains/llvm/prebuilt" / host / "bin/clang").is_file():
        missing.append("ndk;" + NDK_VERSION)
    for package, directory, expected in [
        ("build-tools;" + BUILD_TOOLS, root / "build-tools" / BUILD_TOOLS, BUILD_TOOLS),
        ("ndk;" + NDK_VERSION, ndk_root, NDK_VERSION),
    ]:
        actual = read_properties(directory / "source.properties").get("Pkg.Revision")
        if actual != expected and package not in missing:
            missing.append(package)
    return missing


def find_sdkmanager(root: Path) -> str | None:
    candidates = [root / "cmdline-tools/latest/bin/sdkmanager"]
    candidates.extend(
        sorted((root / "cmdline-tools").glob("*/bin/sdkmanager"), reverse=True)
    )
    candidates.append(root / "tools/bin/sdkmanager")
    if manager := shutil.which("sdkmanager"):
        candidates.append(Path(manager))
    return next(
        (str(path) for path in candidates if path.is_file() and os.access(path, os.X_OK)),
        None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-paths",
        action="store_true",
        help="Print only missing SDK package directories for a cache restore; do not install",
    )
    args = parser.parse_args()
    sdk_root = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    if not sdk_root:
        raise SystemExit(
            "Run aspect work android:setup to select the Android environment."
        )
    root = Path(sdk_root)
    ndk = Path(os.environ.get("ANDROID_NDK_HOME") or root / "ndk" / NDK_VERSION)
    missing = missing_packages(root, ndk_root=ndk)
    if "ndk;" + NDK_VERSION in missing and ndk != root / "ndk" / NDK_VERSION:
        raise SystemExit(
            f"ANDROID_NDK_HOME selects an incomplete or incompatible NDK at {ndk}. "
            f"Install NDK {NDK_VERSION} there or unset ANDROID_NDK_HOME to install "
            "it inside the selected SDK."
        )
    if args.cache_paths:
        for package in missing:
            print(root / package.replace(";", "/"))
        return
    manager = find_sdkmanager(root)
    print(f"Android SDK: {root}")
    print(f"SDK {', '.join(SDK_APIS)}, build-tools {BUILD_TOOLS}, NDK {NDK_VERSION}")
    print(
        "Missing packages: "
        + (", ".join(missing) if missing else "none; reusing installed SDK packages")
    )
    print("Installed sdkmanager: " + (manager or "none"))
    if missing:
        # The pinned manager is downloaded only when no installed manager can supply
        # missing SDK packages.
        command = [manager] if manager else MANAGED_SDKMANAGER
        subprocess.run(
            [*command, "--sdk_root=" + str(root), "--install", *missing],
            input="y\n" * 100,
            text=True,
            check=True,
        )
        if remaining := missing_packages(root, ndk_root=ndk):
            raise SystemExit(
                "Android installation is incomplete: " + ", ".join(remaining)
            )


if __name__ == "__main__":
    main()
