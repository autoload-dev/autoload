"""Failure cases that prevent a stable or mismatched engine passing the Beta proof."""

import struct
import unittest

from godot.platforms.private.tests.engine_probe.validate_android_beta import (
    check_engine,
    check_pack,
    check_symbols,
)
from tools.platforms.native_fixtures import elf


def pack(descriptor: str, engine: tuple[int, int, int] = (4, 8, 0)) -> bytes:
    path = b"native/cpp_example.gdextension\0"
    payload = descriptor.encode()
    directory = struct.pack("<II", 1, len(path)) + path
    offset = 40 + len(directory) + struct.calcsize("<QQ16sI")
    directory += struct.pack("<QQ16sI", offset, len(payload), bytes(16), 0)
    return struct.pack("<6IQQ", 0x43504447, 4, *engine, 0, 0, 40) + directory + payload


DESCRIPTOR = """[configuration]
entry_symbol = "example_library_init"
compatibility_minimum = "4.7.2"
[libraries]
android.arm64 = "res://native/bin/android.arm64/libexample_native.so"
"""


class AndroidBetaTest(unittest.TestCase):
    def test_stable_pck_and_raised_extension_minimum_cannot_pass(self) -> None:
        self.assertEqual(
            check_pack(pack(DESCRIPTOR))[1], "lib/arm64-v8a/libexample_native.so"
        )
        with self.assertRaisesRegex(ValueError, "Godot 4.8.0 PCK"):
            check_pack(pack(DESCRIPTOR, engine=(4, 7, 2)))
        with self.assertRaisesRegex(ValueError, "4.7.2 extension compatibility minimum"):
            check_pack(pack(DESCRIPTOR.replace('"4.7.2"', '"4.8.0"')))

    def test_source_built_engine_must_match_engine_aar_and_compiled_library(self) -> None:
        source = elf(b"\x01\x02") + (
            b"4.8.beta.custom\0BazelProbe\0Godot Engine with Bazel patch\0native"
        )
        # A stripped package keeps the compiled library's build ID.
        stripped = source + b"stripped"
        self.assertTrue(
            check_engine(stripped, stripped, "source", source)[
                "matches_compiled_source_library"
            ]
        )
        other_build = source.replace(elf(b"\x01\x02"), elf(b"\x03\x04"))
        for aar, compiled in [
            (source + b"different", source),
            (source, other_build),
        ]:
            with (
                self.subTest(aar=aar, compiled=compiled),
                self.assertRaisesRegex(ValueError, "differs"),
            ):
                check_engine(source, aar, "source", compiled)
        with self.assertRaisesRegex(ValueError, "compiled engine library"):
            check_engine(source, source, "source")
        with self.assertRaisesRegex(ValueError, "4.8.beta1.official"):
            check_engine(b"4.7.2.stable.official", b"4.7.2.stable.official", "official")
        unpatched = source.replace(b"Godot Engine with Bazel patch", b"Godot Engine")
        with self.assertRaisesRegex(ValueError, "engine-name patch"):
            check_engine(unpatched, unpatched, "source", unpatched)

    def test_undefined_extension_entry_is_not_evidence_of_linkage(self) -> None:
        check_symbols(
            "  4: 1234 456 FUNC GLOBAL DEFAULT 11 example_library_init",
            "example_library_init",
        )
        with self.assertRaisesRegex(ValueError, "does not export"):
            check_symbols(
                "  4: 0000 000 FUNC GLOBAL DEFAULT UND example_library_init",
                "example_library_init",
            )


if __name__ == "__main__":
    unittest.main()
