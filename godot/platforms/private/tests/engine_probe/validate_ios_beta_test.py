"""Guard the iOS beta proof against mismatched slices and relaxed signing checks."""

import struct
import unittest

from godot.platforms.private.tests.engine_probe.validate_ios_beta import (
    BETA_COMMIT,
    check_bootstrap,
    check_mode,
    check_pack,
    check_sdk,
    engine_version,
)


def pack_files(files: dict[str, bytes]) -> bytes:
    paths = [(path.encode() + b"\0", payload) for path, payload in files.items()]
    offset = 44 + sum(4 + len(path) + struct.calcsize("<QQ16sI") for path, _ in paths)
    directory = struct.pack("<I", len(paths))
    for path, payload in paths:
        directory += (
            struct.pack("<I", len(path))
            + path
            + struct.pack("<QQ16sI", offset, len(payload), bytes(16), 0)
        )
        offset += len(payload)
    return (
        struct.pack("<6IQQ", 0x43504447, 4, 4, 8, 0, 0, 0, 40)
        + directory
        + b"".join(payload for _, payload in paths)
    )


class IOSBetaTest(unittest.TestCase):
    def test_device_and_simulator_are_distinguished_by_macho_load_command(self) -> None:
        commands = "Load command 9\ncmd LC_BUILD_VERSION\nplatform 7\nminos 15.0\nLoad command 10\ncmd LC_MAIN\n"
        self.assertIn("platform 7", check_sdk(commands, "simulator"))
        with self.assertRaisesRegex(ValueError, "expected iOS device"):
            check_sdk(commands, "device")

    def test_source_or_simulator_cannot_silently_skip_package_checks(self) -> None:
        check_mode("official", "device", False)
        for kind, environment in [
            ("source", "device"),
            ("source", "simulator"),
            ("official", "simulator"),
        ]:
            with (
                self.subTest(kind=kind, environment=environment),
                self.assertRaisesRegex(ValueError, "restricted"),
            ):
                check_mode(kind, environment, False)

    def test_source_requires_custom_build_module_and_patch(self) -> None:
        # A source-built engine names its version hash in place of the upstream commit.
        data = b"4.8.beta.custom\0BazelProbe\0Godot Engine with Bazel patch"
        self.assertIn("4.8.beta.custom", engine_version(data, "source"))
        official = b"4.8.beta1.official\0" + BETA_COMMIT.encode()
        self.assertIn("4.8.beta1.official", engine_version(official, "official"))
        with self.assertRaisesRegex(ValueError, "selected Godot 4.8-beta1 commit"):
            engine_version(official.replace(BETA_COMMIT.encode(), b"0"), "official")
        with self.assertRaisesRegex(ValueError, "custom module and engine-name patch"):
            engine_version(
                data.replace(b"Godot Engine with Bazel patch", b"Godot Engine"),
                "source",
            )

    def test_bootstrap_needs_the_scene_manifest(self) -> None:
        check_bootstrap({"UIApplicationSceneManifest": {"UISceneConfigurations": {}}})
        with self.assertRaisesRegex(ValueError, "SwiftUI scene manifest"):
            check_bootstrap({})

    def test_pck_retains_static_descriptor_without_the_extension_library(self) -> None:
        descriptor = b"""[configuration]
entry_symbol = "example_library_init"
compatibility_minimum = "4.7.2"
[libraries]
ios.arm64 = "res://native/bin/ios.arm64/extension.a"
"""
        files = {"native/cpp_example.gdextension": descriptor}
        self.assertEqual(check_pack(pack_files(files))["file_count"], 1)
        files["native/bin/ios.arm64/extension.a"] = b"archive"
        with self.assertRaisesRegex(ValueError, "must exclude extension libraries"):
            check_pack(pack_files(files))


if __name__ == "__main__":
    unittest.main()
