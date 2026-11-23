"""Delivered binaries must distinguish CPU coverage from the Apple SDK they are built for."""

import struct
import tempfile
import unittest
from pathlib import Path

from tools.platforms import check_engine_version, native_symbols
from tools.platforms.native_fixtures import archive, elf, macho, universal


class ArtifactValidationTest(unittest.TestCase):
    def test_same_cpu_distinguishes_device_and_simulator(self) -> None:
        self.assertEqual(
            {"arm64": "ios_device"},
            native_symbols.native_slices(macho(sdk="ios_device")),
        )
        self.assertEqual(
            {"arm64": "ios_simulator"},
            native_symbols.native_slices(macho(sdk="ios_simulator")),
        )

    def test_rejects_wrong_sdk_and_extra_cpu(self) -> None:
        with self.assertRaisesRegex(ValueError, "SDK"):
            native_symbols.require_slices(
                macho(sdk="ios_device"), {"arm64"}, "ios_simulator", "engine"
            )
        with self.assertRaisesRegex(ValueError, "CPU"):
            native_symbols.require_slices(
                macho(cpu="x86_64", sdk="ios_simulator"),
                {"arm64"},
                "ios_simulator",
                "engine",
            )

    def test_rejects_truncated_native_headers(self) -> None:
        with self.assertRaisesRegex(ValueError, "Truncated"):
            native_symbols.native_slices(b"\xcf\xfa\xed\xfe")

    def test_desktop_runtime_is_thinned_to_requested_cpu(self) -> None:
        arm = macho(sdk="macos")
        x86 = macho(cpu="x86_64", sdk="macos")
        self.assertEqual(
            arm, native_symbols.desktop_runtime(universal(arm, x86), "arm64", "macos")
        )
        with self.assertRaisesRegex(ValueError, "CPU"):
            native_symbols.desktop_runtime(x86, "arm64", "macos")

    def test_elf_machine_identifies_cpu(self) -> None:
        self.assertEqual({"arm64": "elf"}, native_symbols.native_slices(elf()))
        self.assertEqual(
            {"x86_64": "elf"}, native_symbols.native_slices(elf(cpu="x86_64"))
        )

    def test_32_bit_elf_machine_identifies_cpu(self) -> None:
        # Godot's Linux templates for arm32 and x86_32 are 32-bit ELF files.
        for machine, cpu in [(40, "arm32"), (3, "x86_32")]:
            header = (
                b"\x7fELF" + bytes([1, 1, 1]) + bytes(9) + struct.pack("<HH", 2, machine)
            )
            self.assertEqual(
                {cpu: "elf"}, native_symbols.native_slices(header + bytes(32))
            )

    def test_static_library_has_the_slices_of_its_objects(self) -> None:
        # Godot 4.7.2's Simulator library, which its XCFramework lists as arm64 too.
        simulator = macho(cpu="x86_64", sdk="ios_simulator")
        self.assertEqual(
            {"x86_64": "ios_simulator"},
            native_symbols.native_slices(archive(simulator, simulator)),
        )
        device = archive(macho(sdk="ios_device"))
        self.assertEqual(
            {"arm64": "ios_device", "x86_64": "ios_simulator"},
            native_symbols.native_slices(universal(device, archive(simulator))),
        )
        with self.assertRaisesRegex(ValueError, "SDK"):
            native_symbols.native_slices(
                archive(macho(sdk="ios_device"), macho(sdk="ios_simulator"))
            )
        with self.assertRaisesRegex(ValueError, "Truncated"):
            native_symbols.native_slices(archive(simulator)[:-4])

    def test_ios_engine_without_requested_slice_names_alternatives(self) -> None:
        simulator = archive(macho(cpu="x86_64", sdk="ios_simulator"))
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory, "libgodot.a")
            library.write_bytes(simulator)
            check_engine_version.require_ios_platform_slice(
                library, "x86_64", "ios_simulator"
            )
            with self.assertRaisesRegex(
                SystemExit,
                r"libgodot\.a has no arm64 Simulator slice; it has x86_64 Simulator\. "
                r".*@autoload_rules_godot//godot/platforms:ios_sim_x86_64.*source-built engine",
            ):
                check_engine_version.require_ios_platform_slice(
                    library, "arm64", "ios_simulator"
                )
            with self.assertRaisesRegex(SystemExit, "no arm64 device slice"):
                check_engine_version.require_ios_platform_slice(
                    library, "arm64", "ios_device"
                )
            # Without native objects, such as for LLVM bitcode, nothing is decided.
            library.write_bytes(archive(b"BC\xc0\xde"))
            check_engine_version.require_ios_platform_slice(
                library, "arm64", "ios_simulator"
            )


if __name__ == "__main__":
    unittest.main()
